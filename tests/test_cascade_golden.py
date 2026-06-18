"""Phase-0 BLOCKING test 1 (cascade half): golden doneness classification ported from
the live beef recognizer, exercising every branch plus the NOT_DONE buckets (gate-pass
no-branch AND gate-fail) and the out-of-ROI exclusion. Also asserts the missing-gate-
band guard (zero-fill is forbidden).
"""
import numpy as np

from bh_score.ingest.types import ArrayCube
from bh_score.scoring.cascade import MissingBandError, classifyDonenessBeef
from bh_score.scoring.result import BURNT, NOT_DONE, NOT_ROI, PROPER, SLIGHTLY_BURNT

# Per-pixel engineered band values (ledId -> [8 pixels]).
# idx: 0 burnt | 1 slightly | 2 proper-lean | 3 proper-fat | 4 not_done(gate ok) |
#      5 not_done(gate fail) | 6 not_roi(burnt bands) | 7 not_roi
_BANDS = {
    0:  [5, 5, 5, 5, 5, 200, 5, 5],        # 410
    1:  [50, 50, 50, 50, 50, 200, 50, 50],  # 440
    4:  [20, 20, 20, 20, 200, 20, 20, 20],  # 520
    5:  [20, 15, 22, 90, 200, 20, 20, 20],  # 585
    8:  [20, 35, 45, 60, 200, 20, 20, 20],  # 650
    10: [20, 50, 70, 80, 200, 20, 20, 20],  # 720
    14: [60, 60, 60, 80, 10, 60, 60, 60],   # 930
}
_EXPECTED = [BURNT, SLIGHTLY_BURNT, PROPER, PROPER, NOT_DONE, NOT_DONE, NOT_ROI, NOT_ROI]


def _cube(bands):
    return ArrayCube({led: np.array([vals], dtype=np.uint8) for led, vals in bands.items()})


def test_all_branches():
    roi = np.array([[True, True, True, True, True, True, False, False]])
    cm = classifyDonenessBeef(_cube(_BANDS), roi)
    assert cm.tolist()[0] == _EXPECTED, cm.tolist()


def test_missing_gate_band_raises():
    bands = dict(_BANDS)
    del bands[1]  # drop 440 — a gate band
    roi = np.ones((1, 8), dtype=bool)
    try:
        classifyDonenessBeef(_cube(bands), roi)
    except MissingBandError:
        return
    raise AssertionError("expected MissingBandError for absent gate band")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
