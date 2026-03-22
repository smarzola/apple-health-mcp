from __future__ import annotations

import sqlite3
import textwrap
import zipfile
from pathlib import Path

import pytest

from apple_health_mcp.server import _build_db

SAMPLE_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <HealthData>
      <Record type="HKQuantityTypeIdentifierStepCount"
              sourceName="iPhone" unit="count" value="1234"
              startDate="2025-01-01 08:00:00 -0500"
              endDate="2025-01-01 08:30:00 -0500"/>
      <Record type="HKQuantityTypeIdentifierStepCount"
              sourceName="iPhone" unit="count" value="5678"
              startDate="2025-01-02 09:00:00 -0500"
              endDate="2025-01-02 09:30:00 -0500"/>
      <Record type="HKQuantityTypeIdentifierHeartRate"
              sourceName="Watch" unit="count/min" value="72"
              startDate="2025-01-01 10:00:00 -0500"
              endDate="2025-01-01 10:00:05 -0500"/>
      <Record type="HKCategoryTypeIdentifierSleepAnalysis"
              sourceName="Watch" unit="" value="HKCategoryValueSleepAnalysisAsleepCore"
              startDate="2025-01-01 23:00:00 -0500"
              endDate="2025-01-02 06:30:00 -0500"/>
      <Workout workoutActivityType="HKWorkoutActivityTypeRunning"
               sourceName="Watch" duration="30.5" durationUnit="min"
               totalEnergyBurned="300" totalDistance="5.2" totalDistanceUnit="km"
               startDate="2025-01-01 07:00:00 -0500"
               endDate="2025-01-01 07:30:30 -0500"/>
      <Workout workoutActivityType="HKWorkoutActivityTypeCycling"
               sourceName="Watch" duration="60" durationUnit="min"
               totalEnergyBurned="500" totalDistance="20" totalDistanceUnit="km"
               startDate="2025-01-02 17:00:00 -0500"
               endDate="2025-01-02 18:00:00 -0500"/>
    </HealthData>
""")


@pytest.fixture()
def sample_xml(tmp_path: Path) -> Path:
    """Write sample export.xml to a temp file and return its path."""
    p = tmp_path / "export.xml"
    p.write_text(SAMPLE_XML)
    return p


@pytest.fixture()
def sample_zip(tmp_path: Path, sample_xml: Path) -> Path:
    """Create a zip archive matching Apple Health export structure."""
    p = tmp_path / "export.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.write(sample_xml, "apple_health_export/export.xml")
    return p


@pytest.fixture()
def db(sample_xml: Path) -> sqlite3.Connection:
    """Return an in-memory SQLite database loaded with sample data."""
    return _build_db(str(sample_xml))
