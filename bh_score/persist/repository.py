"""ScoreRepository — the single DuckDB writer for the pipeline process.

Owns the write side of captures + scores (PLAN §5). The dashboard never writes;
it opens the same file read_only through AggregationQueries. One repository instance
owns one duckdb connection for its lifetime; callers must close() it. Writes are
upserts keyed on the table's primary key so re-running the pipeline replaces rows in
place rather than duplicating them.
"""
from __future__ import annotations

import os

import duckdb

from bh_score.ingest.types import CaptureGroup
from bh_score.scoring.result import ScoreResult

_SCHEMA_FILENAME = "schema.sql"


class ScoreRepository:
    def __init__(self, dbPath):
        self.mDbPath = dbPath
        self.mConnection = duckdb.connect(dbPath)

    def initSchema(self):
        """Apply schema.sql (read from disk relative to this module). Idempotent:
        schema.sql uses CREATE TABLE IF NOT EXISTS."""
        tSchemaPath = os.path.join(os.path.dirname(__file__), _SCHEMA_FILENAME)
        with open(tSchemaPath, "r", encoding="utf-8") as tFile:
            tSql = tFile.read()
        self.mConnection.execute(tSql)

    def writeCapture(self, capture, maskPath=None, agreement=None):
        """Upsert one captures row by capture_id. maskPath points at the npz mask
        bundle for the hero; agreement is the agreementMetrics dict (iou/dice may be
        the NO_OVERLAP sentinel string, stored as NULL)."""
        tIou, tDice, tAreaDelta = self._agreementColumns(agreement)
        self.mConnection.execute(
            "DELETE FROM captures WHERE capture_id = ?", [capture.capture_id]
        )
        self.mConnection.execute(
            """
            INSERT INTO captures (
              capture_id, device_id, meat, cut, menu,
              capture_date, capture_index, band_count, frame_dir,
              mask_path, iou, dice, area_delta_px
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                capture.capture_id,
                capture.device_id,
                capture.meat,
                capture.cut,
                capture.menu,
                capture.capture_date,
                capture.capture_index,
                capture.band_count,
                capture.frame_dir,
                maskPath,
                tIou,
                tDice,
                tAreaDelta,
            ],
        )

    @staticmethod
    def _agreementColumns(agreement):
        """Extract (iou, dice, area_delta_px) for storage; a string sentinel iou/dice
        (no overlapping ROI) becomes NULL so the column stays numeric."""
        if not agreement:
            return None, None, None
        tIou = agreement.get("iou")
        tDice = agreement.get("dice")
        tArea = agreement.get("area_delta_px")
        tIouNum = tIou if isinstance(tIou, (int, float)) else None
        tDiceNum = tDice if isinstance(tDice, (int, float)) else None
        return tIouNum, tDiceNum, tArea

    def writeScore(self, result, capture):
        """Upsert one scores row by (capture_id, method). menu/capture_date are
        denormalized from the capture; overlay_path/mono_path come off the result."""
        self.mConnection.execute(
            "DELETE FROM scores WHERE capture_id = ? AND method = ?",
            [capture.capture_id, result.method],
        )
        self.mConnection.execute(
            """
            INSERT INTO scores (
              capture_id, method, menu, capture_date,
              pixels_roi, pixels_not_done, pixels_proper,
              pixels_slightly_burnt, pixels_burnt,
              pct_proper, pct_slightly_burnt, pct_burnt,
              pct_burnt_raw, pct_not_done,
              cooking_score, maillard_score,
              grade, grade_label, instance_count,
              overlay_path, mono_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                capture.capture_id,
                result.method,
                capture.menu,
                capture.capture_date,
                result.pixels_roi,
                result.pixels_not_done,
                result.pixels_proper,
                result.pixels_slightly_burnt,
                result.pixels_burnt,
                result.pct_proper,
                result.pct_slightly_burnt,
                result.pct_burnt,
                result.pct_burnt_raw,
                result.pct_not_done,
                result.cooking_score,
                result.maillard_score,
                result.grade,
                result.grade_label,
                result.instance_count,
                result.overlay_path,
                result.mono_path,
            ],
        )

    def writeInstances(self, captureId, method, instances):
        """Optional AI per-instance drilldown (P2). Replaces all rows for
        (capture_id, method) then inserts the given InstanceResult list."""
        self.mConnection.execute(
            "DELETE FROM instances WHERE capture_id = ? AND method = ?",
            [captureId, method],
        )
        for tInstance in instances:
            tBbox = tInstance.bbox
            self.mConnection.execute(
                """
                INSERT INTO instances (
                  capture_id, method, instance_id, class_id, class_name,
                  pixel_count, bbox_x, bbox_y, bbox_w, bbox_h,
                  pct_proper, pct_slightly_burnt, pct_burnt, maillard_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    captureId,
                    method,
                    tInstance.instance_id,
                    tInstance.class_id,
                    tInstance.class_name,
                    tInstance.pixel_count,
                    int(tBbox[0]),
                    int(tBbox[1]),
                    int(tBbox[2]),
                    int(tBbox[3]),
                    tInstance.pct_proper,
                    tInstance.pct_slightly_burnt,
                    tInstance.pct_burnt,
                    tInstance.maillard_score,
                ],
            )

    def close(self):
        self.mConnection.close()
