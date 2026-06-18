"""Ingest contracts (Phase-0 FROZEN): CaptureGroup metadata + the SpectralCube
interface every scorer reads. The concrete lazy cv2 loader lives in ingest/cube.py
(Stream A); ArrayCube is the in-memory implementation used by the Phase-0 golden
tests and any caller that already holds decoded band arrays.
"""
from __future__ import annotations

import abc
import dataclasses
import datetime


@dataclasses.dataclass
class CaptureGroup:
    """One physical capture = one (device, meat, cut, date, posIdx) group.

    capture_id is the deterministic group-key hash (set by the scanner). band_paths
    maps each (min, max, peak) band key to its on-disk file (PNG-preferred), with the
    999_999_999 sentinel already dropped. band_count is per-capture (8-16), never
    hardcoded.
    """
    capture_id: int
    device_id: int
    meat: str
    cut: str
    menu: str
    capture_date: datetime.date
    capture_index: int
    band_count: int
    frame_dir: str
    band_paths: dict


class SpectralCube(abc.ABC):
    """Wavelength-band accessor for one capture, indexed by ledId via the canonical
    LED<->(min, max, peak) map (bh_score.bands). Frames are grayscale uint8 [H, W].
    """

    @abc.abstractmethod
    def imageByLed(self, ledId):
        """Return the grayscale uint8 [H, W] frame for ledId, or None if absent."""

    def hasLed(self, ledId):
        return self.imageByLed(ledId) is not None


class ArrayCube(SpectralCube):
    """In-memory cube backed by {ledId: np.ndarray[H, W] uint8}. Used by the golden
    tests and by callers that already decoded the bands."""

    def __init__(self, ledImages):
        self._images = dict(ledImages)

    def imageByLed(self, ledId):
        return self._images.get(ledId)
