"""Phase-0 BLOCKING test 4: agreement metrics must never return NaN/inf. Empty-union
returns the sentinel; a single empty mask returns a real 0.0 (union > 0).
"""
import math

import numpy as np

from bh_score.scoring.agreement import NO_OVERLAP_SENTINEL, agreementMetrics


def test_both_empty_returns_sentinel():
    z = np.zeros((10, 10), dtype=bool)
    m = agreementMetrics(z, z)
    assert m["iou"] == NO_OVERLAP_SENTINEL
    assert m["dice"] == NO_OVERLAP_SENTINEL
    assert m["area_delta_px"] == 0


def test_one_empty_is_zero_not_nan():
    onnx = np.zeros((10, 10), dtype=bool)
    rule = np.zeros((10, 10), dtype=bool)
    rule[:5, :5] = True  # 25 px
    m = agreementMetrics(onnx, rule)
    assert m["iou"] == 0.0 and not math.isnan(m["iou"])
    assert m["dice"] == 0.0
    assert m["area_delta_px"] == -25


def test_identical_masks():
    a = np.zeros((10, 10), dtype=bool)
    a[2:8, 2:8] = True
    m = agreementMetrics(a, a.copy())
    assert abs(m["iou"] - 1.0) < 1e-9 and abs(m["dice"] - 1.0) < 1e-9


def test_partial_overlap_known_iou():
    a = np.zeros((1, 10), dtype=bool); a[0, :6] = True   # 6
    b = np.zeros((1, 10), dtype=bool); b[0, 3:9] = True  # 6, overlap idx 3,4,5 = 3
    m = agreementMetrics(a, b)
    assert m["inter_px"] == 3 and m["union_px"] == 9
    assert abs(m["iou"] - (3 / 9)) < 1e-9
    assert abs(m["dice"] - (2 * 3 / 12)) < 1e-9


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
