"""Phase-0 BLOCKING test 3: identical (roi_mask, class_map) fed through the global
kernel under both method labels must produce bit-identical percentages. Guards against
a fake delta sneaking into the comparison if the kernel ever grows method-specific
branches.
"""
import numpy as np

from bh_score.scoring.kernel import scoreFromClassMap
from bh_score.scoring.result import (
    BURNT, METHOD_AI, METHOD_CONDITIONAL, NOT_DONE, NOT_ROI, PROPER, SLIGHTLY_BURNT,
)

_NUMERIC_FIELDS = (
    "pixels_roi", "pixels_not_done", "pixels_proper", "pixels_slightly_burnt",
    "pixels_burnt", "pct_proper", "pct_slightly_burnt", "pct_burnt", "pct_burnt_raw",
    "pct_not_done", "cooking_score", "maillard_score",
)


def test_identical_inputs_bit_identical():
    rng = np.random.default_rng(7)
    cm = rng.integers(NOT_ROI, BURNT + 1, size=(48, 64)).astype(np.uint8)
    roi = cm != NOT_ROI
    ai = scoreFromClassMap(roi, cm, "beef/striploin", METHOD_AI, 3)
    cond = scoreFromClassMap(roi, cm, "beef/striploin", METHOD_CONDITIONAL, 1)
    for f in _NUMERIC_FIELDS:
        assert getattr(ai, f) == getattr(cond, f), f"fake delta in {f}"
    assert ai.method == METHOD_AI and cond.method == METHOD_CONDITIONAL


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
