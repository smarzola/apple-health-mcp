"""Test MCP tool functions directly (bypassing the MCP protocol layer)."""

from __future__ import annotations

import json
import sqlite3

import apple_health_mcp.server as server


def test_list_metrics(db: sqlite3.Connection) -> None:
    server._db = db
    result = json.loads(server.list_metrics())
    by_type = {r["type"]: r["count"] for r in result}
    assert by_type["StepCount"] == 2
    assert by_type["HeartRate"] == 1
    assert by_type["SleepAnalysis"] == 1


def test_list_workout_types(db: sqlite3.Connection) -> None:
    server._db = db
    result = json.loads(server.list_workout_types())
    by_type = {r["activity_type"]: r["count"] for r in result}
    assert by_type["Running"] == 1
    assert by_type["Cycling"] == 1


def test_query_select(db: sqlite3.Connection) -> None:
    server._db = db
    result = json.loads(server.query("SELECT count(*) AS n FROM records"))
    assert result[0]["n"] == 4


def test_query_rejects_non_select(db: sqlite3.Connection) -> None:
    server._db = db
    result = json.loads(server.query("DROP TABLE records"))
    assert "error" in result
    assert "SELECT" in result["error"]


def test_query_rejects_insert(db: sqlite3.Connection) -> None:
    server._db = db
    result = json.loads(server.query("INSERT INTO records VALUES ('a','b','c','d','e','f')"))
    assert "error" in result


def test_summary_by_day(db: sqlite3.Connection) -> None:
    server._db = db
    result = json.loads(server.summary("StepCount", "day"))
    assert len(result) == 2
    assert result[0]["period"] == "2025-01-01"
    assert result[0]["sum_value"] == 1234.0
    assert result[1]["period"] == "2025-01-02"
    assert result[1]["sum_value"] == 5678.0


def test_summary_by_month(db: sqlite3.Connection) -> None:
    server._db = db
    result = json.loads(server.summary("StepCount", "month"))
    assert len(result) == 1
    assert result[0]["period"] == "2025-01"
    assert result[0]["sum_value"] == 1234.0 + 5678.0


def test_summary_invalid_period(db: sqlite3.Connection) -> None:
    server._db = db
    result = json.loads(server.summary("StepCount", "year"))
    assert "error" in result


def test_summary_unknown_metric(db: sqlite3.Connection) -> None:
    server._db = db
    result = json.loads(server.summary("NonExistent", "day"))
    assert "error" in result
