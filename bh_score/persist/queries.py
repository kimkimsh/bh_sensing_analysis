"""AggregationQueries — the read_only side of the scores DuckDB (PLAN §5).

Opened by the Streamlit dashboard (wrap in @st.cache_resource at the call site).
Every query must survive a missing or empty database without raising, returning an
empty DataFrame instead, so the dashboard never crashes on first run (DESIGN_SPEC §8
FIRST_RUN state). This class never writes; the pipeline's ScoreRepository is the only
writer.
"""
from __future__ import annotations

import os

import duckdb
import numpy as np
import pandas as pd

from bh_score.scoring.result import METHOD_AI, METHOD_CONDITIONAL

# Whitelist mapping a 4-way doneness class name to its post-offset percentage column.
# Guards byDate against arbitrary column injection and keeps the public API stable.
_DONENESS_PCT_COLUMN = {
    "not_done": "pct_not_done",
    "proper": "pct_proper",
    "slightly_burnt": "pct_slightly_burnt",
    "burnt": "pct_burnt",
}
_DEFAULT_DONENESS_CLASS = "burnt"


class AggregationQueries:
    def __init__(self, dbPath):
        self.mDbPath = dbPath
        self.mConnection = None
        if os.path.exists(dbPath):
            self.mConnection = duckdb.connect(dbPath, read_only=True)

    def hasScores(self):
        """True only when the DB file exists AND holds at least one scores row.
        Any open/query failure (missing file, empty/locked DB) returns False so the
        dashboard can fall back to the FIRST_RUN message."""
        if self.mConnection is None:
            return False
        try:
            tCount = self.mConnection.execute(
                "SELECT count(*) FROM scores"
            ).fetchone()[0]
            return tCount > 0
        except Exception:
            return False

    def menusAndDates(self):
        """Per-menu catalog for the sidebar filters: capture count and min/max date."""
        if not self.hasScores():
            return pd.DataFrame(
                columns=["menu", "capture_count", "min_date", "max_date"]
            )
        return self.mConnection.execute(
            """
            SELECT menu,
                   count(DISTINCT capture_id) AS capture_count,
                   min(capture_date)          AS min_date,
                   max(capture_date)          AS max_date
            FROM scores
            GROUP BY menu
            ORDER BY menu
            """
        ).df()

    def byDate(self, menus, dateRange, doneness_class=_DEFAULT_DONENESS_CLASS):
        """Average post-offset % of one doneness class per (capture_date, method),
        filtered to the chosen menus and inclusive date range (F-D1). Emits both
        avg_pct and the chart-ready (class, pct_value) columns the trend builder reads."""
        tClass = doneness_class if doneness_class in _DONENESS_PCT_COLUMN else _DEFAULT_DONENESS_CLASS
        tColumn = _DONENESS_PCT_COLUMN[tClass]
        tChip = tClass.upper()
        tEmpty = pd.DataFrame(columns=["capture_date", "method", "avg_pct", "class", "pct_value"])
        if not self.hasScores():
            return tEmpty
        tWhere, tParams = self._buildFilter(menus, dateRange)
        tDf = self.mConnection.execute(
            """
            SELECT capture_date,
                   method,
                   avg({column}) AS avg_pct
            FROM scores
            {where}
            GROUP BY capture_date, method
            ORDER BY capture_date, method
            """.format(column=tColumn, where=tWhere),
            tParams,
        ).df()
        tDf["class"] = tChip
        tDf["pct_value"] = tDf["avg_pct"]
        return tDf

    def byMenu(self, menus, dateRange=None):
        """Average post-offset class % per (menu, method) for the grouped bar (F-D2).
        Includes a single 'value' column (default burnt %) for the bar builder."""
        tEmpty = pd.DataFrame(
            columns=[
                "menu", "method",
                "avg_pct_not_done", "avg_pct_proper",
                "avg_pct_slightly_burnt", "avg_pct_burnt",
                "avg_maillard_score", "capture_count", "value",
            ]
        )
        if not self.hasScores():
            return tEmpty
        tWhere, tParams = self._buildFilter(menus, dateRange)
        tDf = self.mConnection.execute(
            """
            SELECT menu,
                   method,
                   avg(pct_not_done)        AS avg_pct_not_done,
                   avg(pct_proper)          AS avg_pct_proper,
                   avg(pct_slightly_burnt)  AS avg_pct_slightly_burnt,
                   avg(pct_burnt)           AS avg_pct_burnt,
                   avg(maillard_score)      AS avg_maillard_score,
                   count(DISTINCT capture_id) AS capture_count
            FROM scores
            {where}
            GROUP BY menu, method
            ORDER BY menu, method
            """.format(where=tWhere),
            tParams,
        ).df()
        tDf["value"] = tDf["avg_pct_burnt"]
        return tDf

    def paired(self, menu, dateRange):
        """Per capture, AI vs conditional columns side by side (F-C3 scatter / IoU).
        One row per capture_id; ai_* and rule_* come from FILTER aggregates so the
        join is a single self-grouped pass. pixels_roi for both methods is included
        for the ROI-IoU point sizing."""
        tEmpty = pd.DataFrame(
            columns=[
                "capture_id", "capture_date",
                "ai_pixels_roi", "rule_pixels_roi",
                "ai_pct_proper", "rule_pct_proper",
                "ai_pct_slightly_burnt", "rule_pct_slightly_burnt",
                "ai_pct_burnt", "rule_pct_burnt",
                "ai_pct_not_done", "rule_pct_not_done",
                "ai_maillard_score", "rule_maillard_score",
            ]
        )
        if not self.hasScores():
            return tEmpty
        tWhere, tParams = self._buildFilter([menu] if menu else None, dateRange)
        return self.mConnection.execute(
            """
            SELECT capture_id,
                   any_value(capture_date) AS capture_date,
                   max(pixels_roi)         FILTER (method = ?) AS ai_pixels_roi,
                   max(pixels_roi)         FILTER (method = ?) AS rule_pixels_roi,
                   max(pct_proper)         FILTER (method = ?) AS ai_pct_proper,
                   max(pct_proper)         FILTER (method = ?) AS rule_pct_proper,
                   max(pct_slightly_burnt) FILTER (method = ?) AS ai_pct_slightly_burnt,
                   max(pct_slightly_burnt) FILTER (method = ?) AS rule_pct_slightly_burnt,
                   max(pct_burnt)          FILTER (method = ?) AS ai_pct_burnt,
                   max(pct_burnt)          FILTER (method = ?) AS rule_pct_burnt,
                   max(pct_not_done)       FILTER (method = ?) AS ai_pct_not_done,
                   max(pct_not_done)       FILTER (method = ?) AS rule_pct_not_done,
                   max(maillard_score)     FILTER (method = ?) AS ai_maillard_score,
                   max(maillard_score)     FILTER (method = ?) AS rule_maillard_score
            FROM scores
            {where}
            GROUP BY capture_id
            ORDER BY capture_id
            """.format(where=tWhere),
            self._methodFilterParams() + tParams,
        ).df()

    def captureList(self, filters):
        """Capture rows for the Explore table (F-D3): one row per capture_id with
        both methods' key scores and overlay/mono paths. filters is a dict that may
        carry 'menus' and 'date_range'."""
        tEmpty = pd.DataFrame(
            columns=[
                "capture_id", "menu", "capture_date",
                "ai_pixels_roi", "rule_pixels_roi",
                "ai_pct_burnt", "rule_pct_burnt",
                "ai_maillard_score", "rule_maillard_score",
                "ai_grade", "rule_grade",
                "ai_overlay_path", "rule_overlay_path", "mono_path",
            ]
        )
        if not self.hasScores():
            return tEmpty
        tMenus = None
        tDateRange = None
        if filters:
            tMenus = filters.get("menus")
            tDateRange = filters.get("date_range")
        tWhere, tParams = self._buildFilter(tMenus, tDateRange)
        return self.mConnection.execute(
            """
            SELECT capture_id,
                   any_value(menu)         AS menu,
                   any_value(capture_date) AS capture_date,
                   max(pixels_roi)     FILTER (method = ?) AS ai_pixels_roi,
                   max(pixels_roi)     FILTER (method = ?) AS rule_pixels_roi,
                   max(pct_burnt)      FILTER (method = ?) AS ai_pct_burnt,
                   max(pct_burnt)      FILTER (method = ?) AS rule_pct_burnt,
                   max(maillard_score) FILTER (method = ?) AS ai_maillard_score,
                   max(maillard_score) FILTER (method = ?) AS rule_maillard_score,
                   max(grade)          FILTER (method = ?) AS ai_grade,
                   max(grade)          FILTER (method = ?) AS rule_grade,
                   any_value(overlay_path) FILTER (method = ?) AS ai_overlay_path,
                   any_value(overlay_path) FILTER (method = ?) AS rule_overlay_path,
                   any_value(mono_path)    AS mono_path
            FROM scores
            {where}
            GROUP BY capture_id
            ORDER BY capture_date, capture_id
            """.format(where=tWhere),
            self._captureListMethodParams() + tParams,
        ).df()

    def getCapture(self, capture_id):
        """Both-method rows for one capture (Compare tab): overlay/mono paths and the
        full score set per method, one DataFrame row per method."""
        tEmpty = pd.DataFrame()
        if not self.hasScores():
            return tEmpty
        return self.mConnection.execute(
            """
            SELECT *
            FROM scores
            WHERE capture_id = ?
            ORDER BY method
            """,
            [capture_id],
        ).df()

    def menuInventory(self):
        """List of distinct menus for the sidebar multiselect."""
        tDf = self.menusAndDates()
        if tDf is None or tDf.empty:
            return []
        return tDf["menu"].tolist()

    def dateRange(self):
        """(min_date, max_date) across all scored captures, or None when empty."""
        if not self.hasScores():
            return None
        tRow = self.mConnection.execute(
            "SELECT min(capture_date), max(capture_date) FROM scores"
        ).fetchone()
        if tRow is None or tRow[0] is None:
            return None
        return (tRow[0], tRow[1])

    def captureIdFor(self, deviceId, menu, captureDate, captureIndex):
        """Resolve the curated/demo capture_id from its natural key. captureDate may
        be an ISO string or a date; compared against capture_date cast to text."""
        if self.mConnection is None:
            return None
        try:
            tRow = self.mConnection.execute(
                """
                SELECT capture_id FROM captures
                WHERE device_id = ? AND menu = ?
                  AND CAST(capture_date AS VARCHAR) = ? AND capture_index = ?
                LIMIT 1
                """,
                [deviceId, menu, str(captureDate), captureIndex],
            ).fetchone()
        except Exception:
            return None
        return int(tRow[0]) if tRow else None

    def maskBundle(self, captureId):
        """Load the per-capture npz mask bundle for the hero/per-panel render:
        {mono_bg, onnx_mask, rule_mask, onnx_class_map, rule_class_map}. None when the
        capture has no bundle or the file is missing (dashboard falls back to a guard)."""
        if self.mConnection is None:
            return None
        try:
            tRow = self.mConnection.execute(
                "SELECT mask_path FROM captures WHERE capture_id = ?", [captureId]
            ).fetchone()
        except Exception:
            return None
        if not tRow or not tRow[0] or not os.path.exists(tRow[0]):
            return None
        with np.load(tRow[0]) as tNpz:
            return {
                "mono_bg": tNpz["mono_bg"],
                "onnx_mask": tNpz["onnx_mask"].astype(bool),
                "rule_mask": tNpz["rule_mask"].astype(bool),
                "onnx_class_map": tNpz["onnx_class_map"],
                "rule_class_map": tNpz["rule_class_map"],
            }

    def pairedScores(self, captureId):
        """Both-method score rows for one capture as a list of dicts (per-panel bar +
        NOT_DONE-dominant banner)."""
        tDf = self.getCapture(captureId)
        if tDf is None or tDf.empty:
            return []
        return tDf.to_dict("records")

    def captureTable(self, menus):
        """Explore-tab capture table for the given menus (wraps captureList)."""
        return self.captureList({"menus": menus, "date_range": None})

    def aiVsCond(self, menus):
        """Per-capture AI vs Rule burnt% with ROI IoU for the agreement scatter
        (columns onnx_pct, rule_pct, iou)."""
        tEmpty = pd.DataFrame(columns=["onnx_pct", "rule_pct", "iou"])
        if not self.hasScores():
            return tEmpty
        # menu lives in both joined tables, so qualify it explicitly rather than
        # rewriting a shared filter string.
        tWhere = ""
        tParams = []
        if menus:
            tList = list(menus)
            if tList:
                tWhere = "WHERE s.menu IN ({0})".format(", ".join(["?"] * len(tList)))
                tParams = tList
        return self.mConnection.execute(
            """
            SELECT max(s.pct_burnt) FILTER (s.method = ?) AS onnx_pct,
                   max(s.pct_burnt) FILTER (s.method = ?) AS rule_pct,
                   any_value(c.iou) AS iou
            FROM scores s JOIN captures c USING(capture_id)
            {where}
            GROUP BY s.capture_id
            ORDER BY s.capture_id
            """.format(where=tWhere),
            [METHOD_AI, METHOD_CONDITIONAL] + tParams,
        ).df()

    def close(self):
        if self.mConnection is not None:
            self.mConnection.close()

    def _buildFilter(self, menus, dateRange):
        """Build a parameterized WHERE clause shared by the aggregation queries.
        menus is an optional iterable of menu strings; dateRange is an optional
        (start, end) inclusive pair. Returns (whereSql, params)."""
        tClauses = []
        tParams = []
        if menus:
            tMenuList = list(menus)
            if tMenuList:
                tPlaceholders = ", ".join(["?"] * len(tMenuList))
                tClauses.append("menu IN ({0})".format(tPlaceholders))
                tParams.extend(tMenuList)
        if dateRange and len(dateRange) == 2:
            tStart, tEnd = dateRange
            if tStart is not None:
                tClauses.append("capture_date >= ?")
                tParams.append(tStart)
            if tEnd is not None:
                tClauses.append("capture_date <= ?")
                tParams.append(tEnd)
        if not tClauses:
            return "", tParams
        return "WHERE " + " AND ".join(tClauses), tParams

    def _methodFilterParams(self):
        """Method arguments for the 14 FILTER columns in paired(), ai/rule paired."""
        tAi = METHOD_AI
        tRule = METHOD_CONDITIONAL
        return [
            tAi, tRule,   # pixels_roi
            tAi, tRule,   # pct_proper
            tAi, tRule,   # pct_slightly_burnt
            tAi, tRule,   # pct_burnt
            tAi, tRule,   # pct_not_done
            tAi, tRule,   # maillard_score
        ]

    def _captureListMethodParams(self):
        """Method arguments for the FILTER columns in captureList(), ai/rule paired."""
        tAi = METHOD_AI
        tRule = METHOD_CONDITIONAL
        return [
            tAi, tRule,   # pixels_roi
            tAi, tRule,   # pct_burnt
            tAi, tRule,   # maillard_score
            tAi, tRule,   # grade
            tAi, tRule,   # overlay_path
        ]
