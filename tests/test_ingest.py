from __future__ import annotations

import sqlite3
from pathlib import Path

from apple_health_mcp.server import _build_db, _strip_prefix


def test_strip_prefix_quantity() -> None:
    assert _strip_prefix("HKQuantityTypeIdentifierStepCount") == "StepCount"


def test_strip_prefix_category() -> None:
    assert _strip_prefix("HKCategoryTypeIdentifierSleepAnalysis") == "SleepAnalysis"


def test_strip_prefix_workout() -> None:
    assert _strip_prefix("HKWorkoutActivityTypeRunning") == "Running"


def test_strip_prefix_passthrough() -> None:
    assert _strip_prefix("UnknownType") == "UnknownType"


def test_ingest_record_counts(db: sqlite3.Connection) -> None:
    (count,) = db.execute("SELECT count(*) FROM records").fetchone()
    assert count == 4


def test_ingest_workout_counts(db: sqlite3.Connection) -> None:
    (count,) = db.execute("SELECT count(*) FROM workouts").fetchone()
    assert count == 2


def test_prefixes_stripped_in_records(db: sqlite3.Connection) -> None:
    types = {row[0] for row in db.execute("SELECT DISTINCT type FROM records")}
    assert types == {"StepCount", "HeartRate", "SleepAnalysis"}
    assert not any(t.startswith("HK") for t in types)


def test_prefixes_stripped_in_workouts(db: sqlite3.Connection) -> None:
    types = {row[0] for row in db.execute("SELECT DISTINCT activity_type FROM workouts")}
    assert types == {"Running", "Cycling"}


def test_workout_values(db: sqlite3.Connection) -> None:
    row = db.execute(
        "SELECT duration, total_energy_kcal, total_distance, distance_unit "
        "FROM workouts WHERE activity_type = 'Running'"
    ).fetchone()
    assert row["duration"] == 30.5
    assert row["total_energy_kcal"] == 300.0
    assert row["total_distance"] == 5.2
    assert row["distance_unit"] == "km"


def test_load_from_zip(sample_zip: Path) -> None:
    conn = _build_db(str(sample_zip))
    (count,) = conn.execute("SELECT count(*) FROM records").fetchone()
    assert count == 4


def test_bad_path_raises() -> None:
    import pytest

    with pytest.raises(FileNotFoundError):
        _build_db("/nonexistent/export.xml")
