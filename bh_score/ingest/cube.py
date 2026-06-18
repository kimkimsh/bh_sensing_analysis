"""Lazy spectral cube (Stream A): a SpectralCube backed by a CaptureGroup's on-disk
band files. Frames are decoded with cv2 on first access and cached, so a scorer that
touches only a handful of bands never pays to decode the rest.
"""
from __future__ import annotations

import cv2

from bh_score.bands import bandByLed
from bh_score.ingest.types import SpectralCube

# Live calibrated frames are grayscale 480x640; any off-size decode is resized to match
# so downstream array arithmetic against other bands stays aligned.
FRAME_HEIGHT = 480
FRAME_WIDTH = 640


class LazySpectralCube(SpectralCube):
    """SpectralCube reading one CaptureGroup's band files lazily via cv2.imread.

    Owns a per-ledId decode cache for the lifetime of the cube. None is returned (and
    cached) when the ledId maps to a band the capture does not contain."""

    def __init__(self, captureGroup):
        self._capture = captureGroup
        self._cache = {}

    def imageByLed(self, ledId):
        if ledId in self._cache:
            return self._cache[ledId]
        tImage = self._loadLed(ledId)
        self._cache[ledId] = tImage
        return tImage

    def _loadLed(self, ledId):
        tTriple = bandByLed(ledId)
        if tTriple is None:
            return None
        tPath = self._capture.band_paths.get(tTriple)
        if tPath is None:
            return None
        tImage = cv2.imread(tPath, cv2.IMREAD_GRAYSCALE)
        if tImage is None:
            return None
        return self._normalizeSize(tImage)

    def _normalizeSize(self, image):
        if image.shape[0] == FRAME_HEIGHT and image.shape[1] == FRAME_WIDTH:
            return image
        return cv2.resize(image, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_LINEAR)
