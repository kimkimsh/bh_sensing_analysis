"""Stream A offline test: scanner dedup/PNG-preference + the rule-ROI conditional
scorer on the real 250903 beef capture. No network, no ONNX — pure filesystem + cv2.

Asserted contracts:
  * the 250903 beef/striploin capture is found with band_count == 10 (sentinel and
    JPEG/PNG collisions resolved);
  * the synth copy-tree seam collapses to EXACTLY one CaptureGroup and the 410 band
    resolves to the PNG (PNG-preferred), the 999 sentinel band dropped;
  * ConditionalScorer on the real cube yields pixels_roi in the validated band,
    NOT_DONE as the dominant bucket, and no NaN anywhere in the result.
"""
import math
import os

import numpy as np

from bh_score.ingest.cube import LazySpectralCube
from bh_score.ingest.scanner import DatasetScanner
from bh_score.scoring.conditional import ConditionalScorer
from bh_score.scoring.result import METHOD_CONDITIONAL

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_EXPECTED_BEEF_BAND_COUNT = 10
_ROI_PIXELS_MIN = 20000
_ROI_PIXELS_MAX = 45000
_PNG_410_BAND = (410, 420, 415)


def _scan():
    return DatasetScanner().scan(_FIXTURES)


def _captureFor(groups, meat, cut, isoDate):
    tMatches = [
        g for g in groups
        if g.meat == meat and g.cut == cut and g.capture_date.isoformat() == isoDate
    ]
    return tMatches


def test_beef_250903_found_with_ten_bands():
    tGroups = _scan()
    tBeef = _captureFor(tGroups, "beef", "striploin", "2025-09-03")
    assert len(tBeef) == 1, f"expected one 250903 beef capture, got {len(tBeef)}"
    tCapture = tBeef[0]
    assert tCapture.band_count == _EXPECTED_BEEF_BAND_COUNT, tCapture.band_count
    assert len(tCapture.band_paths) == _EXPECTED_BEEF_BAND_COUNT
    assert tCapture.device_id == 206
    assert tCapture.menu == "beef/striploin"
    assert tCapture.capture_index == 1


def test_synth_copytree_collapses_once_png_preferred():
    tGroups = _scan()
    tSynth = _captureFor(tGroups, "beef", "striploin", "2099-01-01")
    assert len(tSynth) == 1, f"copy-tree must collapse to one capture, got {len(tSynth)}"
    tCapture = tSynth[0]
    # 999_999_999 sentinel dropped; the 410 band collides PNG vs JPEG -> PNG wins.
    assert (999, 999, 999) not in tCapture.band_paths
    tPath410 = tCapture.band_paths[_PNG_410_BAND]
    assert tPath410.endswith(".png"), tPath410
    # Both copy-trees share the same deterministic id (collapse, not double count).
    tAllSynthIds = {g.capture_id for g in tGroups if g.capture_date.isoformat() == "2099-01-01"}
    assert len(tAllSynthIds) == 1


def test_capture_id_is_deterministic():
    tFirst = {g.capture_id: g.menu for g in _scan()}
    tSecond = {g.capture_id: g.menu for g in _scan()}
    assert tFirst == tSecond
    for tId in tFirst:
        assert tId > 0


def test_conditional_scorer_on_real_250903():
    tGroups = _scan()
    tCapture = _captureFor(tGroups, "beef", "striploin", "2025-09-03")[0]
    tCube = LazySpectralCube(tCapture)
    tResult = ConditionalScorer().score(tCube, tCapture)

    assert tResult.method == METHOD_CONDITIONAL
    assert _ROI_PIXELS_MIN <= tResult.pixels_roi <= _ROI_PIXELS_MAX, tResult.pixels_roi

    tBuckets = {
        "not_done": tResult.pixels_not_done,
        "proper": tResult.pixels_proper,
        "slightly_burnt": tResult.pixels_slightly_burnt,
        "burnt": tResult.pixels_burnt,
    }
    tDominant = max(tBuckets, key=tBuckets.get)
    assert tDominant == "not_done", tBuckets

    tFloats = [
        tResult.pct_proper, tResult.pct_slightly_burnt, tResult.pct_burnt,
        tResult.pct_burnt_raw, tResult.pct_not_done, tResult.cooking_score,
        tResult.maillard_score,
    ]
    for tValue in tFloats:
        assert not math.isnan(tValue), tFloats
        assert math.isfinite(tValue)

    assert tResult.roi_mask is not None and tResult.roi_mask.dtype == bool
    assert tResult.class_map is not None
    assert tResult.mono_bg is not None

    print(f"  pixels_roi={tResult.pixels_roi} pct_not_done={tResult.pct_not_done:.1f} "
          f"pct_proper={tResult.pct_proper:.1f} maillard={tResult.maillard_score:.2f} "
          f"grade={tResult.grade} ({tResult.grade_label})")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
