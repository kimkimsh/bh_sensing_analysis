"""meatSegNet ONNX segmentation (Stream B). Produces a [480, 640] uint8 label map
where 0 is background and a positive value is (classId + AI_LABEL_OFFSET) for the
winning meat class at that pixel.

Postprocessing is a direct port of the live engine (OnnxROIRecognizer.h) and has been
verified against real inference on the curated beef capture (objmax ~0.93, only the
beef class lights up). Two sort orders are kept deliberately distinct: NMS sorts by
score DESCENDING (keep highest first), the label-map paint loop sorts ASCENDING so the
highest-scoring detection is painted last and overwrites lower ones.

The ONNX session is heavy (133 MB external-data weights) and stateless, so it is built
once and cached at module level. The single-thread intra-op setting mirrors the live
deployment and keeps inference deterministic.
"""
from __future__ import annotations

import numpy as np
import cv2
import onnxruntime as ort

from bh_score.bands import MEATSEGNET_INPUT_LEDS
from bh_score.scoring.result import AI_LABEL_OFFSET

INPUT_W = 640
INPUT_H = 480
CHANNELS = 5
NUM_CLASSES = 4
NUM_PROTOS = 32
CONF_THRESH = 0.3
NMS_THRESH = 0.4
MASK_THRESH = 0.35
STRIDES = (8, 16, 32)

PROTO_H = 120
PROTO_W = 160
PRED_BOX_DIM = 4
PRED_OBJ_IDX = 4
PRED_CLS_START = 5
PRED_CLS_END = 9
PRED_COEFF_START = 9
PRED_COEFF_END = 41
BOX_DELTA_CLIP = 10.0
MASK_BOX_PAD_PX = 10
MASK_BLUR_KERNEL = (5, 5)
MASK_MORPH_KERNEL = (5, 5)

INPUT_NAME = "input"
OUTPUT_NAMES = ("preds", "protos")
DEFAULT_MODEL_PATH = "ai_model/meatSegNet_best.onnx"
INTRA_OP_THREADS = 1

# Session cache keyed by model path: the weights are large and immutable, so every
# MeatSegNet instance for a given model shares one InferenceSession.
_SESSIONS = {}


def _buildSession(modelPath):
    options = ort.SessionOptions()
    options.intra_op_num_threads = INTRA_OP_THREADS
    return ort.InferenceSession(
        modelPath, sess_options=options, providers=["CPUExecutionProvider"]
    )


def _session(modelPath):
    session = _SESSIONS.get(modelPath)
    if session is None:
        session = _buildSession(modelPath)
        _SESSIONS[modelPath] = session
    return session


def _anchors():
    """Anchor (centerX, centerY, stride) per prediction row, Y-MAJOR within each
    stride and concatenated in STRIDES order. Total = 6300 for the 640x480 grid."""
    centersX = []
    centersY = []
    strides = []
    for s in STRIDES:
        rows = INPUT_H // s
        cols = INPUT_W // s
        for y in range(rows):
            for x in range(cols):
                centersX.append((x + 0.5) * s)
                centersY.append((y + 0.5) * s)
                strides.append(float(s))
    return (
        np.asarray(centersX, dtype=np.float32),
        np.asarray(centersY, dtype=np.float32),
        np.asarray(strides, dtype=np.float32),
    )


# Anchor grid is fixed by the strides + input size, so it is computed once.
_ANCHOR_CX, _ANCHOR_CY, _ANCHOR_STRIDE = _anchors()


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _softmaxRows(logits):
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


def _rectIou(boxA, boxB):
    """Rectangle IoU on (x, y, w, h) integer boxes."""
    ax1, ay1, aw, ah = boxA
    bx1, by1, bw, bh = boxB
    ax2 = ax1 + aw
    ay2 = ay1 + ah
    bx2 = bx1 + bw
    by2 = by1 + bh
    interX1 = max(ax1, bx1)
    interY1 = max(ay1, by1)
    interX2 = min(ax2, bx2)
    interY2 = min(ay2, by2)
    interW = max(0, interX2 - interX1)
    interH = max(0, interY2 - interY1)
    inter = interW * interH
    union = aw * ah + bw * bh - inter
    if union <= 0:
        return 0.0
    return inter / float(union)


class Detection:
    """One kept detection after confidence filtering. coeffs are the 32 mask
    coefficients (tanh-activated); box is integer (x, y, w, h) clipped to the frame."""

    def __init__(self, classId, score, box, coeffs):
        self.class_id = classId
        self.score = score
        self.box = box
        self.coeffs = coeffs


class MeatSegNet:
    """Singleton-session ONNX segmenter. segment(cube) -> uint8 [480, 640] label map.

    The InferenceSession is lazily built and module-cached, so constructing multiple
    MeatSegNet objects for the same model reuses one session.
    """

    def __init__(self, modelPath):
        self._modelPath = modelPath
        self._session = _session(modelPath)

    def _buildInput(self, cube):
        tensor = np.zeros((1, CHANNELS, INPUT_H, INPUT_W), dtype=np.float32)
        for ch, led in enumerate(MEATSEGNET_INPUT_LEDS):
            img = cube.imageByLed(led)
            if img is None:
                continue
            tensor[0, ch] = img.astype(np.float32) / 255.0
        return tensor

    def _decodeDetections(self, preds):
        """Confidence-filter every anchor, decode its box + mask coefficients, and
        return per-class detection lists (NMS not yet applied)."""
        obj = _sigmoid(preds[:, PRED_OBJ_IDX])
        keep = obj >= CONF_THRESH
        if not np.any(keep):
            return {}

        rows = np.nonzero(keep)[0]
        objKept = obj[keep]
        clsLogits = preds[keep, PRED_CLS_START:PRED_CLS_END]
        clsProb = _softmaxRows(clsLogits)
        bestClass = clsProb.argmax(axis=1)
        bestScore = clsProb.max(axis=1)
        final = objKept * bestScore

        finalKeep = final >= CONF_THRESH
        if not np.any(finalKeep):
            return {}

        rows = rows[finalKeep]
        bestClass = bestClass[finalKeep]
        final = final[finalKeep]

        dx = preds[rows, 0]
        dy = preds[rows, 1]
        dw = np.clip(preds[rows, 2], -BOX_DELTA_CLIP, BOX_DELTA_CLIP)
        dh = np.clip(preds[rows, 3], -BOX_DELTA_CLIP, BOX_DELTA_CLIP)
        cxA = _ANCHOR_CX[rows]
        cyA = _ANCHOR_CY[rows]
        stride = _ANCHOR_STRIDE[rows]

        cx = cxA + dx * stride
        cy = cyA + dy * stride
        w = np.exp(dw) * stride
        h = np.exp(dh) * stride
        x1 = np.clip(cx - w / 2.0, 0, INPUT_W)
        y1 = np.clip(cy - h / 2.0, 0, INPUT_H)
        wc = np.minimum(INPUT_W - x1, w)
        hc = np.minimum(INPUT_H - y1, h)

        coeffs = np.tanh(preds[rows, PRED_COEFF_START:PRED_COEFF_END])

        byClass = {}
        for i in range(rows.shape[0]):
            box = (int(x1[i]), int(y1[i]), int(wc[i]), int(hc[i]))
            det = Detection(int(bestClass[i]), float(final[i]), box, coeffs[i])
            byClass.setdefault(det.class_id, []).append(det)
        return byClass

    def _nmsPerClass(self, byClass):
        """Per-class greedy NMS: sort score DESCENDING, suppress overlaps above
        NMS_THRESH. Returns the flat list of survivors across all classes."""
        kept = []
        for classId in byClass:
            dets = sorted(byClass[classId], key=_detScoreDesc, reverse=True)
            survivors = []
            while dets:
                top = dets.pop(0)
                survivors.append(top)
                dets = [d for d in dets if _rectIou(top.box, d.box) <= NMS_THRESH]
            kept.extend(survivors)
        return kept

    def _paintLabelMap(self, kept, protos):
        """Paint kept detections into the label map. Sort score ASCENDING so the
        highest-scoring detection is painted last and overwrites the rest."""
        labelMap = np.zeros((INPUT_H, INPUT_W), dtype=np.uint8)
        protosFlat = protos.reshape(NUM_PROTOS, PROTO_H * PROTO_W)
        morphKernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, MASK_MORPH_KERNEL)

        ordered = sorted(kept, key=_detScoreAsc)
        for det in ordered:
            maskFlat = _sigmoid(det.coeffs @ protosFlat)
            mask = maskFlat.reshape(PROTO_H, PROTO_W)
            mask = cv2.resize(mask, (INPUT_W, INPUT_H), interpolation=cv2.INTER_LINEAR)

            bx, by, bw, bh = det.box
            rx1 = max(0, bx - MASK_BOX_PAD_PX)
            ry1 = max(0, by - MASK_BOX_PAD_PX)
            rx2 = min(INPUT_W, bx + bw + MASK_BOX_PAD_PX)
            ry2 = min(INPUT_H, by + bh + MASK_BOX_PAD_PX)
            if rx2 <= rx1 or ry2 <= ry1:
                continue

            roi = mask[ry1:ry2, rx1:rx2]
            roi = cv2.GaussianBlur(roi, MASK_BLUR_KERNEL, 0)
            binMask = (roi > MASK_THRESH).astype(np.uint8) * 255
            binMask = cv2.morphologyEx(binMask, cv2.MORPH_CLOSE, morphKernel)

            target = labelMap[ry1:ry2, rx1:rx2]
            target[binMask > 0] = det.class_id + AI_LABEL_OFFSET
        return labelMap

    def segment(self, cube):
        """Run inference + postprocessing, returning a uint8 [480, 640] label map in
        {0, 1, 2, 3, 4}. An empty/no-detection capture yields an all-zero map."""
        inputTensor = self._buildInput(cube)
        outputs = self._session.run(list(OUTPUT_NAMES), {INPUT_NAME: inputTensor})
        preds = outputs[0][0]
        protos = outputs[1][0]

        byClass = self._decodeDetections(preds)
        if not byClass:
            return np.zeros((INPUT_H, INPUT_W), dtype=np.uint8)

        kept = self._nmsPerClass(byClass)
        return self._paintLabelMap(kept, protos)


def _detScoreDesc(det):
    return det.score


def _detScoreAsc(det):
    return det.score
