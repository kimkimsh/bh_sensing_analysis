"""Filesystem scanner (Stream A): walks a data root, parses the calibrated band
filenames, and groups frames into CaptureGroup records.

Grouping key is (device_id, meat, cut, date, posIdx). The capture_id is a
deterministic crc32 of that key's stable string so the same physical capture maps
to the same id across runs and across duplicated copy-trees. PNG wins over JPEG on
a band-key collision; the 999_999_999 sentinel band is dropped; "X (copy)" trees
collapse onto their original so a duplicated capture is counted exactly once.
"""
from __future__ import annotations

import datetime
import os
import re
import zlib

from bh_score.bands import SENTINEL_BAND
from bh_score.ingest.types import CaptureGroup

# ver2_charbroiler_calibrated_<meat>_<cut>_<YYMMDD>_<posIdx>_<wMin>_<wMax>_<wPeak>.<ext>
# meat/cut are NOT captured from the filename: cut names carry underscores
# (t_bone, Combo_belly_loin_Cut, galbi_marinated_charcoal), so an alphabetic group
# would drop those captures. They come from the directory layout instead; the
# filename only supplies the unambiguous trailing digit groups.
_FILENAME_RE = re.compile(
    r"^ver2_charbroiler_calibrated_.+_"
    r"(?P<date>\d{6})_"
    r"(?P<pos>\d+)_"
    r"(?P<wmin>\d+)_(?P<wmax>\d+)_(?P<wpeak>\d+)"
    r"\.(?P<ext>png|jpeg|jpg)$",
    re.IGNORECASE,
)

_COPY_SUFFIX = " (copy)"
_DATE_CENTURY_BASE = 2000
_PNG_EXT = "png"
# crc32 yields a 32-bit unsigned value, already inside BIGINT positive range.
_CAPTURE_ID_MASK = 0xFFFFFFFF


class _ParsedFrame:
    """One parsed band file. Valid only within DatasetScanner.scan()."""

    def __init__(self, deviceId, meat, cut, captureDate, posIdx, bandKey, ext, path):
        self.device_id = deviceId
        self.meat = meat
        self.cut = cut
        self.capture_date = captureDate
        self.pos_idx = posIdx
        self.band_key = bandKey
        self.ext = ext
        self.path = path


class DatasetScanner:
    """Walks a data root and returns one CaptureGroup per physical capture."""

    def scan(self, dataRoot):
        groups = {}
        for tDir, _subdirs, tFiles in os.walk(dataRoot):
            for tFileName in tFiles:
                tFrame = self._parseFrame(dataRoot, tDir, tFileName)
                if tFrame is None:
                    continue
                self._mergeFrame(groups, tFrame)
        return self._buildCaptureGroups(groups)

    def _parseFrame(self, dataRoot, fileDir, fileName):
        tMatch = _FILENAME_RE.match(fileName)
        if tMatch is None:
            return None

        tBandKey = (int(tMatch.group("wmin")), int(tMatch.group("wmax")), int(tMatch.group("wpeak")))
        if tBandKey == SENTINEL_BAND:
            return None

        tKey = self._keyFromPath(dataRoot, fileDir)
        if tKey is None:
            return None
        tDeviceId, tMeat, tCut = tKey

        tCaptureDate = self._parseDate(tMatch.group("date"))
        if tCaptureDate is None:
            return None

        tFrame = _ParsedFrame(
            tDeviceId,
            tMeat,
            tCut,
            tCaptureDate,
            int(tMatch.group("pos")),
            tBandKey,
            tMatch.group("ext").lower(),
            os.path.join(fileDir, fileName),
        )
        return tFrame

    def _keyFromPath(self, dataRoot, fileDir):
        """device_id, meat, cut from the directory layout
        <root>/<backup>/<deviceId>/<meat>/<cut>/<date>/<file>. meat/cut are taken from
        the path (authoritative — they may contain underscores) rather than the
        ambiguous filename middle. Relative to the file's <date> directory the segments
        are [..., deviceId, meat, cut, date]. Returns (deviceId, meat, cut) or None."""
        tNormalized = self._stripCopySegments(os.path.relpath(fileDir, dataRoot))
        tParts = [p for p in tNormalized.split(os.sep) if p not in ("", ".")]
        if len(tParts) < 4:
            return None
        tDeviceSegment = tParts[-4]
        if not tDeviceSegment.isdigit():
            return None
        return int(tDeviceSegment), tParts[-3].lower(), tParts[-2].lower()

    def _stripCopySegments(self, relPath):
        """Remove every " (copy)" suffix from path segments so a copy-tree collapses
        onto its original."""
        tParts = relPath.split(os.sep)
        tCleaned = [self._stripCopySuffix(p) for p in tParts]
        return os.sep.join(tCleaned)

    def _stripCopySuffix(self, segment):
        tCleaned = segment
        while tCleaned.endswith(_COPY_SUFFIX):
            tCleaned = tCleaned[: -len(_COPY_SUFFIX)]
        return tCleaned

    def _parseDate(self, yymmdd):
        """YYMMDD -> date (2000 + YY). Returns None for a calendar-invalid value so a
        single malformed filename skips its frame instead of aborting the whole scan."""
        try:
            return datetime.date(
                _DATE_CENTURY_BASE + int(yymmdd[0:2]),
                int(yymmdd[2:4]),
                int(yymmdd[4:6]),
            )
        except ValueError:
            return None

    def _groupKey(self, frame):
        return (
            frame.device_id,
            frame.meat,
            frame.cut,
            frame.capture_date,
            frame.pos_idx,
        )

    def _mergeFrame(self, groups, frame):
        tKey = self._groupKey(frame)
        tGroup = groups.get(tKey)
        if tGroup is None:
            tGroup = {}
            groups[tKey] = tGroup
        tExisting = tGroup.get(frame.band_key)
        if tExisting is None or self._preferReplacement(tExisting, frame):
            tGroup[frame.band_key] = frame

    def _preferReplacement(self, existing, candidate):
        """PNG wins over JPEG on the same band key. Same-extension collisions keep
        the first frame seen (copy-tree duplicates resolve to one path)."""
        return existing.ext != _PNG_EXT and candidate.ext == _PNG_EXT

    def _buildCaptureGroups(self, groups):
        tResult = []
        for tKey in sorted(groups.keys(), key=self._sortableKey):
            tFramesByBand = groups[tKey]
            tBandPaths = {band: frame.path for band, frame in tFramesByBand.items()}
            tSampleFrame = next(iter(tFramesByBand.values()))
            tCaptureId = self._captureId(tKey)
            tDeviceId, tMeat, tCut, tCaptureDate, tPosIdx = tKey
            tResult.append(
                CaptureGroup(
                    capture_id=tCaptureId,
                    device_id=tDeviceId,
                    meat=tMeat,
                    cut=tCut,
                    menu=tMeat + "/" + tCut,
                    capture_date=tCaptureDate,
                    capture_index=tPosIdx,
                    band_count=len(tBandPaths),
                    frame_dir=os.path.dirname(tSampleFrame.path),
                    band_paths=tBandPaths,
                )
            )
        return tResult

    def _sortableKey(self, key):
        tDeviceId, tMeat, tCut, tCaptureDate, tPosIdx = key
        return (tDeviceId, tMeat, tCut, tCaptureDate.isoformat(), tPosIdx)

    def _captureId(self, key):
        tDeviceId, tMeat, tCut, tCaptureDate, tPosIdx = key
        tStable = "|".join(
            [str(tDeviceId), tMeat, tCut, tCaptureDate.isoformat(), str(tPosIdx)]
        )
        return int(zlib.crc32(tStable.encode("utf-8")) & _CAPTURE_ID_MASK)
