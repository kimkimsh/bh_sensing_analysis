"""Offline Stream B test: meatSegNet segmentation + AiScorer.

Builds an in-memory ArrayCube directly from the fixture bands (no dependency on the
Stream A loader) by mapping each band-key triple in the filename to its ledId. Asserts
the model loads, the label map is non-zero and beef-dominant, the AiScorer produces a
sane beef ROI on the FIRES capture, and the DEAD capture yields an empty (but valid)
result with no crash.
"""
from __future__ import annotations

import datetime
import glob
import os
import re

import numpy as np
import cv2

from bh_score.bands import ledByBand
from bh_score.ingest.types import ArrayCube, CaptureGroup
from bh_score.scoring.ai import AiScorer
from bh_score.scoring.result import AI_BEEF_CLASS_ID, AI_LABEL_OFFSET, METHOD_AI
from bh_score.segment.meatsegnet import MeatSegNet

FIXTURE_ROOT = "tests/fixtures/260612_office_backup/206/beef/striploin"
FIRES_DATE = "250903"
DEAD_DATE = "251016"

BEEF_VALUE = AI_BEEF_CLASS_ID + AI_LABEL_OFFSET
PIXELS_ROI_MIN = 20000
PIXELS_ROI_MAX = 45000

# Filename tail: ..._<posIdx>_<wMin>_<wMax>_<wPeak>.<ext>
_BAND_RE = re.compile(r"_(\d+)_(\d+)_(\d+)_(\d+)\.(?:png|jpeg|jpg)$", re.IGNORECASE)


def _loadCube(dateDir):
    """Build an ArrayCube from every band file in dateDir, keyed by ledId."""
    images = {}
    for path in sorted(glob.glob(os.path.join(dateDir, "*"))):
        match = _BAND_RE.search(os.path.basename(path))
        if match is None:
            continue
        wMin = int(match.group(2))
        wMax = int(match.group(3))
        wPeak = int(match.group(4))
        led = ledByBand(wMin, wMax, wPeak)
        if led is None:
            continue
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        assert img is not None, f"failed to decode {path}"
        assert img.shape == (480, 640), f"unexpected shape {img.shape} for {path}"
        images[led] = img
    return ArrayCube(images)


def _capture(menu, captureDate):
    return CaptureGroup(
        capture_id=1,
        device_id=206,
        meat="beef",
        cut="striploin",
        menu=menu,
        capture_date=datetime.date(
            2000 + int(captureDate[:2]), int(captureDate[2:4]), int(captureDate[4:6])
        ),
        capture_index=1,
        band_count=10,
        frame_dir="",
        band_paths={},
    )


def testModelLoadsAndSegments():
    net = MeatSegNet("ai_model/meatSegNet_best.onnx")
    cube = _loadCube(os.path.join(FIXTURE_ROOT, FIRES_DATE))
    labelMap = net.segment(cube)

    assert labelMap.dtype == np.uint8
    assert labelMap.shape == (480, 640)
    assert int(labelMap.max()) <= 4
    nonzero = int(np.count_nonzero(labelMap))
    assert nonzero > 0, "label map is empty on the FIRES capture"

    values, counts = np.unique(labelMap[labelMap > 0], return_counts=True)
    dominant = int(values[int(counts.argmax())])
    assert dominant == BEEF_VALUE, f"dominant label {dominant} is not BEEF ({BEEF_VALUE})"
    print(f"PASS: model loads, label_map nonzero={nonzero}, dominant value={dominant} (BEEF)")


def testAiScorerOnFires():
    net = MeatSegNet("ai_model/meatSegNet_best.onnx")
    scorer = AiScorer(net)
    cube = _loadCube(os.path.join(FIXTURE_ROOT, FIRES_DATE))
    result = scorer.score(cube, _capture("beef/striploin", FIRES_DATE))

    assert result.method == METHOD_AI
    assert result.instance_count >= 1
    assert PIXELS_ROI_MIN <= result.pixels_roi <= PIXELS_ROI_MAX, (
        f"pixels_roi={result.pixels_roi} outside [{PIXELS_ROI_MIN}, {PIXELS_ROI_MAX}]"
    )
    for value in (
        result.pct_proper,
        result.pct_slightly_burnt,
        result.pct_burnt,
        result.pct_not_done,
        result.maillard_score,
        result.cooking_score,
    ):
        assert not np.isnan(value), "NaN in score fields"
    assert result.roi_mask is not None and result.roi_mask.dtype == bool
    assert result.class_map is not None
    assert int(np.count_nonzero(result.roi_mask)) == result.pixels_roi
    print(
        f"PASS: AiScorer FIRES pixels_roi={result.pixels_roi}, "
        f"instances={result.instance_count}, maillard={result.maillard_score:.2f}, "
        f"grade={result.grade}/{result.grade_label}, no NaN"
    )


def testAiScorerOnDead():
    net = MeatSegNet("ai_model/meatSegNet_best.onnx")
    scorer = AiScorer(net)
    cube = _loadCube(os.path.join(FIXTURE_ROOT, DEAD_DATE))
    result = scorer.score(cube, _capture("beef/striploin", DEAD_DATE))

    assert result.pixels_roi == 0, f"expected empty ROI, got {result.pixels_roi}"
    assert result.instance_count == 0
    assert result.roi_mask is not None and not result.roi_mask.any()
    for value in (result.pct_proper, result.maillard_score, result.cooking_score):
        assert not np.isnan(value)
    print(
        f"PASS: AiScorer DEAD (251016) pixels_roi=0, instances=0, no crash, no NaN"
    )


if __name__ == "__main__":
    testModelLoadsAndSegments()
    testAiScorerOnFires()
    testAiScorerOnDead()
    print("ALL STREAM B TESTS PASSED")
