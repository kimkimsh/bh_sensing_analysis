"""Pipeline orchestrator (Phase 2 integration glue).

Scans a data root into CaptureGroups, runs the requested scorers (AI ROI and/or
rule ROI) over each capture sharing one MeatSegNet session, renders the cached
overlay PNGs (the ROI-diff hero from BOTH masks plus a per-method doneness mask
overlay), and writes captures + scores into the DuckDB the dashboard reads
read_only. Re-running is idempotent: ScoreRepository upserts by primary key.

Run order (DESIGN_SPEC §12): this is the first half of `bash run.sh`; the
dashboard is launched afterwards. Empty-AI captures (no beef instances) and
duplicate copy-tree captures are expected, not errors.
"""
from __future__ import annotations

import argparse
import os
import sys

import cv2
import numpy as np

from bh_score.ingest.cube import FRAME_HEIGHT, FRAME_WIDTH, LazySpectralCube
from bh_score.ingest.scanner import DatasetScanner
from bh_score.persist.repository import ScoreRepository
from bh_score.scoring.agreement import agreementMetrics
from bh_score.scoring.ai import AiScorer
from bh_score.scoring.conditional import ConditionalScorer
from bh_score.scoring.result import METHOD_AI, METHOD_CONDITIONAL
from bh_score.segment.meatsegnet import DEFAULT_MODEL_PATH, MeatSegNet
from bh_score.viz import overlay
from bh_score.viz.palette import MONO_BACKGROUND_LED

_METHOD_BOTH = "both"
_METHOD_CHOICES = (METHOD_AI, METHOD_CONDITIONAL, _METHOD_BOTH)

_DEFAULT_DATA_ROOT = "data"
_DEFAULT_DB = "scores.duckdb"

_OVERLAY_DIR = os.path.join("artifacts", "overlays")
_PNG_EXT = ".png"
_NPZ_EXT = ".npz"


def parseArgs(argv):
    parser = argparse.ArgumentParser(
        description="Scan captures, score (AI/rule ROI), cache overlays, write DuckDB."
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="Score only the first N captures (smoke runs). Default: all.")
    parser.add_argument("--methods", choices=_METHOD_CHOICES, default=_METHOD_BOTH,
                        help="Which scorer(s) to run. Default: both.")
    parser.add_argument("--data-root", default=_DEFAULT_DATA_ROOT,
                        help="Root directory to scan. Default: data.")
    parser.add_argument("--db", default=_DEFAULT_DB,
                        help="DuckDB output path. Default: scores.duckdb.")
    parser.add_argument("--model", default=DEFAULT_MODEL_PATH,
                        help="meatSegNet ONNX model path.")
    return parser.parse_args(argv)


def _wantsAi(methods):
    return methods in (METHOD_AI, _METHOD_BOTH)


def _wantsConditional(methods):
    return methods in (METHOD_CONDITIONAL, _METHOD_BOTH)


def _monoFor(cube, results):
    """Resolve the led10 grayscale background for overlay compositing. Prefer the
    cube band; fall back to any mono_bg a scorer already captured; finally a black
    frame so overlay rendering never crashes on a missing background."""
    tMono = cube.imageByLed(MONO_BACKGROUND_LED)
    if tMono is not None:
        return tMono
    for tResult in results:
        if tResult is not None and tResult.mono_bg is not None:
            return tResult.mono_bg
    return np.zeros((FRAME_HEIGHT, FRAME_WIDTH), dtype=np.uint8)


def _maskOf(result, shape):
    """Boolean ROI mask for a result, or an all-False mask of shape when the method
    was not run (so the hero still composites the one mask that exists)."""
    if result is not None and result.roi_mask is not None:
        return np.asarray(result.roi_mask).astype(bool)
    return np.zeros(shape, dtype=bool)


def _classMapOf(result, shape):
    """uint8 doneness class_map for a result, or all-NOT_ROI when the method was not
    run (so the per-panel overlay still renders the mono background)."""
    if result is not None and result.class_map is not None:
        return np.asarray(result.class_map).astype(np.uint8)
    return np.zeros(shape, dtype=np.uint8)


def _saveMaskBundle(captureId, mono, aiMask, condMask, aiClassMap, condClassMap):
    """Persist the per-capture npz the dashboard hero/per-panel render reads
    (compressed: bool masks are tiny). Returns the bundle path."""
    tPath = os.path.join(_OVERLAY_DIR, str(captureId) + _NPZ_EXT)
    np.savez_compressed(
        tPath,
        mono_bg=mono,
        onnx_mask=aiMask,
        rule_mask=condMask,
        onnx_class_map=aiClassMap,
        rule_class_map=condClassMap,
    )
    return tPath


def _saveRgb(path, rgbImage):
    """Persist an RGB uint8 overlay as PNG (cv2 writes BGR, so convert first)."""
    tBgr = cv2.cvtColor(rgbImage, cv2.COLOR_RGB2BGR)
    cv2.imwrite(path, tBgr)


def _renderOverlays(captureId, cube, aiResult, condResult):
    """Render and cache the per-capture artifacts: mono PNG, ROI-diff hero PNG,
    per-method mask-overlay PNGs, and the npz mask bundle the dashboard reads. Returns
    (monoPath, aiOverlayPath, condOverlayPath, maskPath, agreement). The hero is
    rendered once from BOTH ROI masks (a missing method degrades to an empty mask)."""
    os.makedirs(_OVERLAY_DIR, exist_ok=True)
    tMono = _monoFor(cube, (aiResult, condResult))
    tShape = tMono.shape[:2]

    tMonoPath = os.path.join(_OVERLAY_DIR, str(captureId) + "_mono" + _PNG_EXT)
    _saveRgb(tMonoPath, overlay.monoToRgb(tMono))

    tAiMask = _maskOf(aiResult, tShape)
    tCondMask = _maskOf(condResult, tShape)
    tAiClassMap = _classMapOf(aiResult, tShape)
    tCondClassMap = _classMapOf(condResult, tShape)

    tHero = overlay.renderRoiDiffHero(tMono, tAiMask, tCondMask)
    tHeroPath = os.path.join(_OVERLAY_DIR, str(captureId) + "_hero" + _PNG_EXT)
    _saveRgb(tHeroPath, tHero)

    tAiOverlayPath = None
    if aiResult is not None and aiResult.class_map is not None:
        tAiOverlayPath = os.path.join(_OVERLAY_DIR, str(captureId) + "_ai" + _PNG_EXT)
        _saveRgb(tAiOverlayPath, overlay.renderMaskOverlay(tMono, tAiMask, tAiClassMap))

    tCondOverlayPath = None
    if condResult is not None and condResult.class_map is not None:
        tCondOverlayPath = os.path.join(_OVERLAY_DIR, str(captureId) + "_conditional" + _PNG_EXT)
        _saveRgb(tCondOverlayPath, overlay.renderMaskOverlay(tMono, tCondMask, tCondClassMap))

    tMaskPath = _saveMaskBundle(captureId, tMono, tAiMask, tCondMask, tAiClassMap, tCondClassMap)
    tAgreement = agreementMetrics(tAiMask, tCondMask)
    return tMonoPath, tAiOverlayPath, tCondOverlayPath, tMaskPath, tAgreement


def _writeResult(repo, result, capture, overlayPath, monoPath):
    result.overlay_path = overlayPath
    result.mono_path = monoPath
    repo.writeScore(result, capture)
    if result.per_instance:
        repo.writeInstances(capture.capture_id, result.method, result.per_instance)


def _scoreCapture(capture, aiScorer, condScorer):
    """Run the requested scorers over one capture. A scorer that fails on this
    capture (e.g. a missing cascade band) is reported and skipped so one bad capture
    never aborts the whole run."""
    tCube = LazySpectralCube(capture)
    tAiResult = None
    tCondResult = None
    if aiScorer is not None:
        tAiResult = _runScorer(aiScorer, tCube, capture, METHOD_AI)
    if condScorer is not None:
        tCondResult = _runScorer(condScorer, tCube, capture, METHOD_CONDITIONAL)
    return tCube, tAiResult, tCondResult


def _runScorer(scorer, cube, capture, method):
    try:
        return scorer.score(cube, capture)
    except Exception as tError:
        print(
            "  ! "
            + method
            + " scorer failed for capture "
            + str(capture.capture_id)
            + ": "
            + repr(tError)
        )
        return None


def run(argv):
    args = parseArgs(argv)

    tScanner = DatasetScanner()
    tCaptures = tScanner.scan(args.data_root)
    if args.limit is not None:
        tCaptures = tCaptures[: args.limit]
    print("Scanned " + str(len(tCaptures)) + " capture(s) from " + args.data_root)

    tAiScorer = None
    if _wantsAi(args.methods):
        tAiScorer = AiScorer(MeatSegNet(args.model))
    tCondScorer = ConditionalScorer() if _wantsConditional(args.methods) else None

    tRepo = ScoreRepository(args.db)
    tRepo.initSchema()
    tWritten = 0
    try:
        for tIndex, tCapture in enumerate(tCaptures, start=1):
            print(
                str(tIndex)
                + "/"
                + str(len(tCaptures))
                + " capture "
                + str(tCapture.capture_id)
                + " "
                + tCapture.menu
                + " "
                + tCapture.capture_date.isoformat()
                + " (bands="
                + str(tCapture.band_count)
                + ")"
            )
            tCube, tAiResult, tCondResult = _scoreCapture(tCapture, tAiScorer, tCondScorer)
            tMonoPath, tAiOverlayPath, tCondOverlayPath, tMaskPath, tAgreement = _renderOverlays(
                tCapture.capture_id, tCube, tAiResult, tCondResult
            )
            tRepo.writeCapture(tCapture, tMaskPath, tAgreement)

            if tAiResult is not None:
                _writeResult(tRepo, tAiResult, tCapture, tAiOverlayPath, tMonoPath)
                tWritten += 1
                print(
                    "    ai  roi_px="
                    + str(tAiResult.pixels_roi)
                    + " pct_burnt="
                    + format(tAiResult.pct_burnt, ".2f")
                    + " instances="
                    + str(tAiResult.instance_count)
                )
            if tCondResult is not None:
                _writeResult(tRepo, tCondResult, tCapture, tCondOverlayPath, tMonoPath)
                tWritten += 1
                print(
                    "    rule roi_px="
                    + str(tCondResult.pixels_roi)
                    + " pct_burnt="
                    + format(tCondResult.pct_burnt, ".2f")
                )
    finally:
        tRepo.close()

    print("Wrote " + str(tWritten) + " score row(s) to " + args.db)
    return 0


def main():
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
