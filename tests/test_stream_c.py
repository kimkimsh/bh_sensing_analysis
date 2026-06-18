"""Offline test for Stream C (DuckDB persistence + aggregation queries).

Writes a synthetic capture plus two ScoreResult rows (ai + conditional) through
ScoreRepository, reopens the DB read_only via AggregationQueries, and asserts the
aggregation queries return non-empty frames whose ai vs conditional values differ.
Also asserts a non-existent DB path is handled without crashing. Run directly:
  cd <repo> && PYTHONPATH=. .venv/bin/python tests/test_stream_c.py
"""
from __future__ import annotations

import datetime
import os
import tempfile

from bh_score.ingest.types import CaptureGroup
from bh_score.persist.queries import AggregationQueries
from bh_score.persist.repository import ScoreRepository
from bh_score.scoring.result import (
    METHOD_AI,
    METHOD_CONDITIONAL,
    ScoreResult,
)


def buildCapture():
    return CaptureGroup(
        capture_id=12345,
        device_id=206,
        meat="beef",
        cut="striploin",
        menu="beef/striploin",
        capture_date=datetime.date(2025, 9, 3),
        capture_index=1,
        band_count=10,
        frame_dir="tests/fixtures/260612_office_backup/206/beef/striploin/250903",
        band_paths={},
    )


def buildScore(method, pixelsRoi, pctBurnt, maillard, overlayPath):
    return ScoreResult(
        method=method,
        menu="beef/striploin",
        pixels_roi=pixelsRoi,
        pixels_not_done=int(pixelsRoi * 0.5),
        pixels_proper=int(pixelsRoi * 0.3),
        pixels_slightly_burnt=int(pixelsRoi * 0.1),
        pixels_burnt=int(pixelsRoi * 0.1),
        pct_proper=30.0,
        pct_slightly_burnt=10.0,
        pct_burnt=pctBurnt,
        pct_burnt_raw=pctBurnt + 3.0,
        pct_not_done=50.0,
        cooking_score=30.0,
        maillard_score=maillard,
        grade=0,
        grade_label="COMPLETE",
        instance_count=1,
        overlay_path=overlayPath,
        mono_path="cache/mono_12345.png",
    )


def runTest():
    tTempDir = tempfile.mkdtemp(prefix="stream_c_")
    tDbPath = os.path.join(tTempDir, "scores.duckdb")

    tCapture = buildCapture()
    tAiScore = buildScore(METHOD_AI, 9000, 7.0, 50.0, "cache/ai_12345.png")
    tRuleScore = buildScore(METHOD_CONDITIONAL, 7000, 12.0, 70.0, "cache/rule_12345.png")

    tRepo = ScoreRepository(tDbPath)
    tRepo.initSchema()
    tRepo.writeCapture(tCapture)
    tRepo.writeScore(tAiScore, tCapture)
    tRepo.writeScore(tRuleScore, tCapture)
    # Re-run upsert with identical keys to prove no duplicate rows accrue.
    tRepo.writeScore(tAiScore, tCapture)
    tRepo.close()
    print("PASS: repository wrote capture + ai/conditional scores")

    tQueries = AggregationQueries(tDbPath)
    assert tQueries.hasScores() is True, "hasScores must be True after writes"
    print("PASS: hasScores() True on populated DB")

    tMenus = tQueries.menusAndDates()
    assert len(tMenus) == 1, "menusAndDates must list the single menu"
    assert int(tMenus.iloc[0]["capture_count"]) == 1, "one distinct capture expected"
    print("PASS: menusAndDates() returns the menu catalog")

    tByDate = tQueries.byDate(
        ["beef/striploin"],
        (datetime.date(2025, 1, 1), datetime.date(2025, 12, 31)),
        "burnt",
    )
    assert not tByDate.empty, "byDate must return rows"
    tByDateMap = {tRow["method"]: tRow["avg_pct"] for _, tRow in tByDate.iterrows()}
    assert tByDateMap[METHOD_AI] != tByDateMap[METHOD_CONDITIONAL], "ai vs cond burnt% must differ"
    print("PASS: byDate() non-empty and ai vs conditional differ")

    tByMenu = tQueries.byMenu(["beef/striploin"], None)
    assert not tByMenu.empty, "byMenu must return rows"
    tAiBurnt = tByMenu[tByMenu["method"] == METHOD_AI]["avg_pct_burnt"].iloc[0]
    tRuleBurnt = tByMenu[tByMenu["method"] == METHOD_CONDITIONAL]["avg_pct_burnt"].iloc[0]
    assert tAiBurnt != tRuleBurnt, "ai vs cond avg_pct_burnt must differ"
    print("PASS: byMenu() non-empty and ai vs conditional differ")

    tPaired = tQueries.paired("beef/striploin", None)
    assert not tPaired.empty, "paired must return rows"
    tRow = tPaired.iloc[0]
    assert tRow["ai_pixels_roi"] != tRow["rule_pixels_roi"], "paired pixels_roi must differ"
    assert tRow["ai_pct_burnt"] != tRow["rule_pct_burnt"], "paired pct_burnt must differ"
    assert tRow["ai_maillard_score"] != tRow["rule_maillard_score"], "paired maillard must differ"
    print("PASS: paired() non-empty with distinct ai/rule columns")

    tList = tQueries.captureList({"menus": ["beef/striploin"], "date_range": None})
    assert not tList.empty, "captureList must return rows"
    tListRow = tList.iloc[0]
    assert tListRow["ai_overlay_path"] != tListRow["rule_overlay_path"], "overlay paths must differ"
    assert tListRow["mono_path"] == "cache/mono_12345.png", "mono_path must round-trip"
    print("PASS: captureList() non-empty with both methods' paths")

    tCaptureRows = tQueries.getCapture(12345)
    assert len(tCaptureRows) == 2, "getCapture must return both method rows"
    tMethods = set(tCaptureRows["method"].tolist())
    assert tMethods == {METHOD_AI, METHOD_CONDITIONAL}, "both methods present"
    print("PASS: getCapture() returns both method rows")

    tQueries.close()

    tMissing = AggregationQueries(os.path.join(tTempDir, "does_not_exist.duckdb"))
    assert tMissing.hasScores() is False, "missing DB must report hasScores False"
    assert tMissing.byMenu(None, None).empty, "missing DB byMenu must be empty"
    assert tMissing.paired("beef/striploin", None).empty, "missing DB paired must be empty"
    assert tMissing.captureList(None).empty, "missing DB captureList must be empty"
    tMissing.close()
    print("PASS: non-existent DB path -> hasScores() False, queries empty, no crash")

    print("ALL STREAM C TESTS PASSED")


if __name__ == "__main__":
    runTest()
