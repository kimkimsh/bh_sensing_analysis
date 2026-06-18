"""Phase-0 BLOCKING test 1 (kernel half): golden DonenessKernel percentages including
the NOT_DONE bucket and the single per-menu offset. Runnable directly or via pytest.
"""
import numpy as np

from bh_score.scoring.kernel import scoreFromClassMap
from bh_score.scoring.result import (
    BURNT, METHOD_CONDITIONAL, NOT_DONE, NOT_ROI, PROPER, SLIGHTLY_BURNT,
)


def _goldenMaps():
    # 120 cells: first 100 in ROI, last 20 out of ROI.
    roi = np.zeros((1, 120), dtype=bool)
    roi[0, :100] = True
    cm = np.full((1, 120), NOT_ROI, dtype=np.uint8)
    cm[0, 0:10] = PROPER            # 10
    cm[0, 10:16] = SLIGHTLY_BURNT   # 6
    cm[0, 16:24] = BURNT            # 8
    cm[0, 24:100] = NOT_DONE        # 76
    return roi, cm


def test_beef_offset_and_buckets():
    roi, cm = _goldenMaps()
    r = scoreFromClassMap(roi, cm, "beef/striploin", METHOD_CONDITIONAL, 1)
    assert r.pixels_roi == 100
    assert (r.pixels_proper, r.pixels_slightly_burnt, r.pixels_burnt, r.pixels_not_done) == (10, 6, 8, 76)
    # raw burnt 8% kept; post-offset proper/slightly/burnt are floored subtractions.
    assert abs(r.pct_burnt_raw - 8.0) < 1e-9
    assert abs(r.pct_not_done - 76.0) < 1e-9
    assert abs(r.pct_burnt - 5.0) < 1e-9       # 8 - 3
    assert abs(r.pct_slightly_burnt - 4.5) < 1e-9  # 6 - 1.5
    assert abs(r.pct_proper - 5.0) < 1e-9      # 10 - 5
    assert abs(r.cooking_score - 5.0) < 1e-9
    # maillard 5*0.7 + 4.5*1.5 + 5*3.0 = 25.25
    assert abs(r.maillard_score - 25.25) < 1e-9


def test_pork_offsets_burnt_only():
    roi, cm = _goldenMaps()
    r = scoreFromClassMap(roi, cm, "pork/belly", METHOD_CONDITIONAL, 1)
    assert abs(r.pct_burnt - 5.0) < 1e-9        # burnt offset applies
    assert abs(r.pct_slightly_burnt - 6.0) < 1e-9  # no slightly offset for pork
    assert abs(r.pct_proper - 10.0) < 1e-9      # no proper offset for pork
    # maillard 10*0.7 + 6*1.5 + 5*3.0 = 31.0
    assert abs(r.maillard_score - 31.0) < 1e-9


def test_empty_roi_no_nan():
    roi = np.zeros((1, 50), dtype=bool)
    cm = np.full((1, 50), NOT_ROI, dtype=np.uint8)
    r = scoreFromClassMap(roi, cm, "beef/striploin", METHOD_CONDITIONAL, 0)
    assert r.pixels_roi == 0
    for v in (r.pct_proper, r.pct_slightly_burnt, r.pct_burnt, r.pct_not_done,
              r.cooking_score, r.maillard_score):
        assert v == 0.0 and not np.isnan(v)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
