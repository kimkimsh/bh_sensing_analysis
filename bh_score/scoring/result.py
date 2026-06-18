"""Shared output contract (Phase-0 FROZEN). Both scorers emit ScoreResult so the
dashboard compares apples to apples; only the ROI source differs.
"""
from __future__ import annotations

import dataclasses
from typing import List, Optional

import numpy as np

# Doneness class indices written into class_map (uint8 [H, W]).
NOT_ROI = 0
NOT_DONE = 1
PROPER = 2
SLIGHTLY_BURNT = 3
BURNT = 4

# meatSegNet class encoding — taken from the live CODE (OnnxComponentRecognizer
# CLASS_NAMES + OnnxInferenceOutput beef-only global), not the contradictory header
# comments, and confirmed by real inference: a beef capture lights up only classId 0.
AI_CLASS_NAMES = ("BEEF", "CHICKEN", "LAMB", "PORK")
AI_BEEF_CLASS_ID = 0       # the only class summed into the beef-only global
AI_LABEL_OFFSET = 1        # label_map pixel value = class_id + AI_LABEL_OFFSET
AI_MIN_INSTANCE_PIXELS = 500

METHOD_AI = "ai"
METHOD_CONDITIONAL = "conditional"


@dataclasses.dataclass
class InstanceResult:
    """AI per-instance summary (optional drilldown, P2)."""
    instance_id: int
    class_id: int
    class_name: str
    pixel_count: int
    bbox: tuple
    pct_proper: float
    pct_slightly_burnt: float
    pct_burnt: float
    maillard_score: float


@dataclasses.dataclass
class ScoreResult:
    """One capture scored by one method. pct_* are post-offset (the reported scores);
    the raw pixel counts feed the honest 4-way stacked bar and the absolute-count
    honesty guard (DESIGN_SPEC §11). roi_mask / class_map / mono_bg are in-memory
    render inputs, not DB columns.
    """
    method: str
    menu: str
    pixels_roi: int
    pixels_not_done: int
    pixels_proper: int
    pixels_slightly_burnt: int
    pixels_burnt: int
    pct_proper: float            # post-offset
    pct_slightly_burnt: float    # post-offset
    pct_burnt: float             # post-offset
    pct_burnt_raw: float         # pre-offset burnt %
    pct_not_done: float          # raw gate-failed %
    cooking_score: float
    maillard_score: float
    grade: int
    grade_label: str
    instance_count: int
    roi_mask: Optional[np.ndarray] = None      # bool [H, W]
    class_map: Optional[np.ndarray] = None      # uint8 [H, W] in {0..4}
    mono_bg: Optional[np.ndarray] = None        # uint8 [H, W] (led10 background)
    per_instance: List[InstanceResult] = dataclasses.field(default_factory=list)
    overlay_path: Optional[str] = None
    mono_path: Optional[str] = None
