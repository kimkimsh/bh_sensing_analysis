"""Overlay renderers (Stream D). Pure functions over (mono background, masks,
class map) — never branch on scoring method, so the same code paints either ROI
source. All color comes from viz.palette (the three disjoint color spaces), so the
legend cannot drift between AI and Rule views.

  renderRoiDiffHero  — THE hero: a 3-region overlap-map in the ROI_DIFF palette.
                       doneness ramp must never appear here.
  renderMaskOverlay  — per-panel doneness overlay in the flat MASK palette
                       (readability port, not the live HSV hue ramp).
"""
from __future__ import annotations

import cv2
import numpy as np

from bh_score.scoring import result as scoreResult
from bh_score.viz import palette

# Hero legend strip geometry (drawn over a dark scrim so text stays >=3:1 on the
# variable grayscale meat background; WCAG 1.4.3/G145).
_LEGEND_HEIGHT_PX = 64
_LEGEND_SCRIM_RGBA_ALPHA = 0.55
_LEGEND_CHIP_SIZE_PX = 16
_LEGEND_CHIP_GAP_PX = 8
_LEGEND_MARGIN_PX = 12
_LEGEND_ROW_GAP_PX = 6
_LEGEND_FONT = cv2.FONT_HERSHEY_SIMPLEX
_LEGEND_FONT_SCALE = 0.42
_LEGEND_FONT_THICK = 1
_LEGEND_TEXT_RGB = (230, 234, 240)
_LEGEND_CAPTION = "Same doneness rules. Different ROI mask."

# Dashed-contour dash/gap run length in pixels (Rule-only border).
_DASH_RUN_PX = 8

# Diagonal hatch spacing/thickness for the Rule-only fill (redundant encoding so
# the region reads without relying on color alone; WCAG 1.4.1).
_HATCH_SPACING_PX = 10
_HATCH_THICKNESS_PX = 1


def _hexToRgb(hexStr):
    """'#RRGGBB' -> (R, G, B) ints for RGB output buffers."""
    tHex = hexStr.lstrip("#")
    tR = int(tHex[0:2], 16)
    tG = int(tHex[2:4], 16)
    tB = int(tHex[4:6], 16)
    return (tR, tG, tB)


def monoToRgb(monoBg):
    """Grayscale uint8 [H, W] (or already-RGB [H, W, 3]) -> contiguous RGB uint8
    [H, W, 3] base that the overlay compositing writes onto."""
    tMono = np.asarray(monoBg)
    if tMono.ndim == 3 and tMono.shape[2] == 3:
        return np.ascontiguousarray(tMono.astype(np.uint8))
    if tMono.ndim == 3 and tMono.shape[2] == 1:
        tMono = tMono[:, :, 0]
    tGray = tMono.astype(np.uint8)
    return np.ascontiguousarray(np.stack([tGray, tGray, tGray], axis=-1))


def _alphaFill(rgbImage, regionMask, rgbColor, alpha):
    """Alpha-blend a flat RGB color into rgbImage where regionMask is True (in place)."""
    if not regionMask.any():
        return
    tIdx = regionMask
    tColor = np.array(rgbColor, dtype=np.float32)
    tBase = rgbImage[tIdx].astype(np.float32)
    tBlended = tBase * (1.0 - alpha) + tColor * alpha
    rgbImage[tIdx] = np.clip(tBlended, 0, 255).astype(np.uint8)


def _hatchMask(regionMask):
    """Boolean diagonal-stripe mask intersected with regionMask, for the Rule-only
    hatched fill (redundant non-color encoding)."""
    tH, tW = regionMask.shape
    tYy, tXx = np.indices((tH, tW))
    tStripes = ((tXx + tYy) % _HATCH_SPACING_PX) < _HATCH_THICKNESS_PX
    return regionMask & tStripes


def _drawContoursSolid(rgbImage, regionMask, bgrColor, thicknessPx):
    """Draw crisp solid contours of regionMask onto rgbImage."""
    tContours, _ = cv2.findContours(
        regionMask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )
    cv2.drawContours(rgbImage, tContours, -1, bgrColor, thicknessPx)


def _drawContoursDashed(rgbImage, regionMask, bgrColor, thicknessPx):
    """Draw dashed contours of regionMask by walking each contour and stroking
    alternating runs (cv2 has no native dashed line)."""
    tContours, _ = cv2.findContours(
        regionMask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )
    for tContour in tContours:
        tPoints = tContour.reshape(-1, 2)
        tCount = len(tPoints)
        if tCount < 2:
            continue
        tIndex = 0
        while tIndex < tCount:
            tDraw = (tIndex // _DASH_RUN_PX) % 2 == 0
            tNext = (tIndex + 1) % tCount
            if tDraw:
                tP0 = (int(tPoints[tIndex][0]), int(tPoints[tIndex][1]))
                tP1 = (int(tPoints[tNext][0]), int(tPoints[tNext][1]))
                cv2.line(rgbImage, tP0, tP1, bgrColor, thicknessPx)
            tIndex += 1


def _putScrimText(rgbImage, text, originXy, scrimWidthPx):
    """Burn text over a dark scrim chip so it stays legible on any background."""
    tX, tY = originXy
    (tTextW, tTextH), tBaseline = cv2.getTextSize(
        text, _LEGEND_FONT, _LEGEND_FONT_SCALE, _LEGEND_FONT_THICK
    )
    tPad = 3
    tX0 = tX - tPad
    tY0 = tY - tTextH - tPad
    tX1 = tX + max(tTextW, scrimWidthPx) + tPad
    tY1 = tY + tBaseline + tPad
    tX0 = max(tX0, 0)
    tY0 = max(tY0, 0)
    tScrim = rgbImage[tY0:tY1, tX0:tX1].astype(np.float32)
    tScrim *= (1.0 - _LEGEND_SCRIM_RGBA_ALPHA)
    rgbImage[tY0:tY1, tX0:tX1] = np.clip(tScrim, 0, 255).astype(np.uint8)
    cv2.putText(
        rgbImage,
        text,
        (tX, tY),
        _LEGEND_FONT,
        _LEGEND_FONT_SCALE,
        _LEGEND_TEXT_RGB,
        _LEGEND_FONT_THICK,
        cv2.LINE_AA,
    )


def _burnLegend(rgbImage):
    """Burn a dark-scrim inline legend strip (3 chips + caption) along the bottom.

    The whole strip sits on a uniform dark scrim so the chip labels and caption keep
    >=3:1 contrast over the grayscale meat texture underneath.
    """
    tH, tW = rgbImage.shape[:2]
    tY0 = max(tH - _LEGEND_HEIGHT_PX, 0)
    tStrip = rgbImage[tY0:tH].astype(np.float32)
    tStrip *= (1.0 - _LEGEND_SCRIM_RGBA_ALPHA)
    rgbImage[tY0:tH] = np.clip(tStrip, 0, 255).astype(np.uint8)

    tChips = (
        ("Both", palette.ROI_DIFF["BOTH"]["hex"]),
        ("AI-only", palette.ROI_DIFF["ONNX_ONLY"]["hex"]),
        ("Rule-only", palette.ROI_DIFF["RULE_ONLY"]["hex"]),
    )
    tCursorX = _LEGEND_MARGIN_PX
    tChipY = tY0 + _LEGEND_MARGIN_PX
    for tLabel, tHex in tChips:
        tColor = _hexToRgb(tHex)
        rgbImage[
            tChipY:tChipY + _LEGEND_CHIP_SIZE_PX,
            tCursorX:tCursorX + _LEGEND_CHIP_SIZE_PX,
        ] = tColor
        tTextX = tCursorX + _LEGEND_CHIP_SIZE_PX + _LEGEND_CHIP_GAP_PX
        tTextY = tChipY + _LEGEND_CHIP_SIZE_PX - 2
        cv2.putText(
            rgbImage,
            tLabel,
            (tTextX, tTextY),
            _LEGEND_FONT,
            _LEGEND_FONT_SCALE,
            _LEGEND_TEXT_RGB,
            _LEGEND_FONT_THICK,
            cv2.LINE_AA,
        )
        (tLabelW, _), _ = cv2.getTextSize(
            tLabel, _LEGEND_FONT, _LEGEND_FONT_SCALE, _LEGEND_FONT_THICK
        )
        tCursorX = tTextX + tLabelW + _LEGEND_CHIP_SIZE_PX + _LEGEND_CHIP_GAP_PX

    tCaptionY = tY0 + _LEGEND_HEIGHT_PX - _LEGEND_ROW_GAP_PX
    cv2.putText(
        rgbImage,
        _LEGEND_CAPTION,
        (_LEGEND_MARGIN_PX, tCaptionY),
        _LEGEND_FONT,
        _LEGEND_FONT_SCALE,
        _LEGEND_TEXT_RGB,
        _LEGEND_FONT_THICK,
        cv2.LINE_AA,
    )


def renderRoiDiffHero(monoBg, onnxMask, ruleMask):
    """THE hero. Composite the ONNX/Rule ROI disagreement over the mono (led10)
    grayscale background as a 3-region overlap-map in the ROI_DIFF palette.

      both      = onnx & rule  -> neutral grey low-alpha fill, no contour.
      onnx_only = onnx & ~rule -> cyan fill + SOLID 2px contour.
      rule_only = rule & ~onnx -> vermilion hatched fill + DASHED 2px contour.

    Returns RGB uint8 [H, W, 3]. No doneness ramp ever appears here.
    """
    tImage = monoToRgb(monoBg)
    tOnnx = np.asarray(onnxMask).astype(bool)
    tRule = np.asarray(ruleMask).astype(bool)

    tBoth = tOnnx & tRule
    tOnnxOnly = tOnnx & ~tRule
    tRuleOnly = tRule & ~tOnnx

    tBothCfg = palette.ROI_DIFF["BOTH"]
    tOnnxCfg = palette.ROI_DIFF["ONNX_ONLY"]
    tRuleCfg = palette.ROI_DIFF["RULE_ONLY"]

    _alphaFill(tImage, tBoth, _hexToRgb(tBothCfg["hex"]), tBothCfg["alpha"])
    _alphaFill(tImage, tOnnxOnly, _hexToRgb(tOnnxCfg["hex"]), tOnnxCfg["alpha"])
    _alphaFill(tImage, tRuleOnly, _hexToRgb(tRuleCfg["hex"]), tRuleCfg["alpha"])
    _alphaFill(
        tImage, _hatchMask(tRuleOnly), _hexToRgb(tRuleCfg["hex"]), 1.0
    )

    tPx = palette.ROI_DIFF_CONTOUR_PX
    _drawContoursSolid(tImage, tOnnxOnly, _hexToRgb(tOnnxCfg["hex"]), tPx)
    _drawContoursDashed(tImage, tRuleOnly, _hexToRgb(tRuleCfg["hex"]), tPx)

    _burnLegend(tImage)
    return tImage


def renderMaskOverlay(monoBg, roiMask, classMap):
    """Per-panel doneness overlay over the mono background using the flat MASK
    doneness palette (NOT the live HSV ramp). Doneness pixel priority is
    burnt > slightly > proper; non-doneness ROI pixels keep the background. The
    BGR palette is converted to RGB for the output buffer.

    Returns RGB uint8 [H, W, 3].
    """
    tImage = monoToRgb(monoBg)
    tClass = np.asarray(classMap)

    tProper = tClass == scoreResult.PROPER
    tSlightly = tClass == scoreResult.SLIGHTLY_BURNT
    tBurnt = tClass == scoreResult.BURNT

    # Priority burnt > slightly > proper: paint proper first, then slightly, then
    # burnt so the higher-priority class always wins on overlapping writes.
    _alphaFill(
        tImage,
        tProper,
        _bgrToRgb(palette.MASK_DONENESS_BGR["PROPER"]),
        palette.MASK_DONENESS_ALPHA,
    )
    _alphaFill(
        tImage,
        tSlightly,
        _bgrToRgb(palette.MASK_DONENESS_BGR["SLIGHTLY_BURNT"]),
        palette.MASK_DONENESS_ALPHA,
    )
    _alphaFill(
        tImage,
        tBurnt,
        _bgrToRgb(palette.MASK_DONENESS_BGR["BURNT"]),
        palette.MASK_DONENESS_ALPHA,
    )
    return tImage


def _bgrToRgb(bgrTuple):
    return (int(bgrTuple[2]), int(bgrTuple[1]), int(bgrTuple[0]))
