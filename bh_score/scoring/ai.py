"""ONNX-ROI scorer (Stream B). The AI supplies only the ROI: meatSegNet segments the
frame, beef instances above the minimum pixel area are unioned into the ROI mask, and
the SHARED doneness cascade + DonenessKernel produce the ScoreResult. Doneness is rule
based and identical to the conditional scorer; only the ROI source differs, which is
what makes the dashboard's ROI-diff comparison apples-to-apples.

This reproduces the live OnnxInferenceOutput beef-only global: only class 0 (BEEF)
instances feed the global percentages, and the offset is applied once inside the kernel.

An empty capture (no beef instances) is a valid, expected state — the 251016 fixture is
exactly this. It returns an all-zero ScoreResult with an all-False roi_mask, never a
crash.
"""
from __future__ import annotations

import numpy as np
import cv2

from bh_score.ingest.types import CaptureGroup, SpectralCube
from bh_score.scoring import cascade
from bh_score.scoring import kernel
from bh_score.scoring import grades
from bh_score.scoring.base import Scorer
from bh_score.scoring.result import (
    AI_BEEF_CLASS_ID,
    AI_CLASS_NAMES,
    AI_LABEL_OFFSET,
    AI_MIN_INSTANCE_PIXELS,
    METHOD_AI,
    InstanceResult,
    ScoreResult,
)
from bh_score.segment.meatsegnet import INPUT_H, INPUT_W
from bh_score.viz.palette import MONO_BACKGROUND_LED

CC_CONNECTIVITY = 8
# connectedComponentsWithStats columns: label 0 is always the background component.
STATS_AREA_COL = cv2.CC_STAT_AREA
BACKGROUND_LABEL = 0


class AiScorer(Scorer):
    """Scorer whose ROI comes from meatSegNet beef instances. Shares the doneness
    cascade and kernel with the conditional scorer."""

    def __init__(self, meatSegNet):
        self._meatSegNet = meatSegNet

    def score(self, cube, capture):
        labelMap = self._meatSegNet.segment(cube)
        beefValue = AI_BEEF_CLASS_ID + AI_LABEL_OFFSET
        classMask = (labelMap == beefValue).astype(np.uint8)

        beefRoi, instanceCount, components = _beefInstances(classMask)
        monoBg = cube.imageByLed(MONO_BACKGROUND_LED)

        if instanceCount == 0:
            return _emptyResult(capture.menu, monoBg, beefRoi)

        classMap = cascade.classifyDonenessBeef(cube, beefRoi)
        result = kernel.scoreFromClassMap(
            beefRoi, classMap, capture.menu, METHOD_AI, instanceCount
        )

        scoreFields = {
            "maillard_score": result.maillard_score,
            "slightly_burnt": result.pct_slightly_burnt,
            "burnt_score": result.pct_burnt_raw,
        }
        grade, gradeLabel = grades.gradeFor(capture.menu, scoreFields)
        result.grade = grade
        result.grade_label = gradeLabel
        result.roi_mask = beefRoi
        result.class_map = classMap
        result.mono_bg = monoBg
        result.per_instance = _perInstance(
            components, classMap, beefRoi, capture.menu
        )
        return result


def _beefInstances(classMask):
    """Return (beef_roi bool[H, W], kept_count, components). components is a list of
    (label_id, area, bbox, mask bool[H, W]) for each kept connected component."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        classMask, CC_CONNECTIVITY
    )
    beefRoi = np.zeros(classMask.shape, dtype=bool)
    components = []
    for labelId in range(1, count):
        area = int(stats[labelId, STATS_AREA_COL])
        if area < AI_MIN_INSTANCE_PIXELS:
            continue
        mask = labels == labelId
        beefRoi |= mask
        bbox = (
            int(stats[labelId, cv2.CC_STAT_LEFT]),
            int(stats[labelId, cv2.CC_STAT_TOP]),
            int(stats[labelId, cv2.CC_STAT_WIDTH]),
            int(stats[labelId, cv2.CC_STAT_HEIGHT]),
        )
        components.append((labelId, area, bbox, mask))
    return beefRoi, len(components), components


def _perInstance(components, classMap, beefRoi, menu):
    """Per-instance doneness summary. Each instance's percentages come from the shared
    kernel over that instance's mask alone, so they match the global contract."""
    results = []
    beefName = AI_CLASS_NAMES[AI_BEEF_CLASS_ID]
    for instanceId, (labelId, area, bbox, mask) in enumerate(components):
        instanceClassMap = np.where(mask, classMap, 0).astype(np.uint8)
        sub = kernel.scoreFromClassMap(
            mask, instanceClassMap, menu, METHOD_AI, 1
        )
        results.append(
            InstanceResult(
                instance_id=instanceId,
                class_id=AI_BEEF_CLASS_ID,
                class_name=beefName,
                pixel_count=area,
                bbox=bbox,
                pct_proper=sub.pct_proper,
                pct_slightly_burnt=sub.pct_slightly_burnt,
                pct_burnt=sub.pct_burnt,
                maillard_score=sub.maillard_score,
            )
        )
    return results


def _emptyResult(menu, monoBg, beefRoi):
    """Valid all-zero result for a capture with no beef instances (251016 case).
    The grade ladder still runs over the zero scores (no fabricated COMPLETE)."""
    classMap = np.zeros((INPUT_H, INPUT_W), dtype=np.uint8)
    result = kernel.scoreFromClassMap(beefRoi, classMap, menu, METHOD_AI, 0)
    scoreFields = {
        "maillard_score": result.maillard_score,
        "slightly_burnt": result.pct_slightly_burnt,
        "burnt_score": result.pct_burnt_raw,
    }
    grade, gradeLabel = grades.gradeFor(menu, scoreFields)
    result.grade = grade
    result.grade_label = gradeLabel
    result.roi_mask = beefRoi
    result.class_map = classMap
    result.mono_bg = monoBg
    return result
