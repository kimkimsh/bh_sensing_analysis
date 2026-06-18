"""Scorer interface (Phase-0 FROZEN). Implementations differ only in how they
produce the ROI mask; both share the doneness cascade + DonenessKernel.
"""
from __future__ import annotations

import abc

from bh_score.ingest.types import CaptureGroup, SpectralCube
from bh_score.scoring.result import ScoreResult


class Scorer(abc.ABC):
    @abc.abstractmethod
    def score(self, cube: SpectralCube, capture: CaptureGroup) -> ScoreResult:
        """Score one capture into a ScoreResult."""
