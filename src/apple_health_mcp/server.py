"""Apple Health MCP Server — exposes health export data via MCP tools over stdio."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import iterparse

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# XML → SQLite ingestion
# ---------------------------------------------------------------------------

_PREFIX_STRIPS = (
    "HKQuantityTypeIdentifier",
    "HKCategoryTypeIdentifier",
    "HKWorkoutActivityType",
)


def _strip_prefix(value: str) -> str:
    for prefix in _PREFIX_STRIPS:
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS records (
            type        TEXT,
            source_name TEXT,
            unit        TEXT,
            value       TEXT,
            start_date  TEXT,
            end_date    TEXT
        );
        CREATE TABLE IF NOT EXISTS workouts (
            activity_type      TEXT,
            source_name        TEXT,
            duration           REAL,
            duration_unit      TEXT,
            total_energy_kcal  REAL,
            total_distance     REAL,
            distance_unit      TEXT,
            start_date         TEXT,
            end_date           TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_records_type ON records(type);
        CREATE INDEX IF NOT EXISTS idx_records_start ON records(start_date);
        CREATE INDEX IF NOT EXISTS idx_workouts_type ON workouts(activity_type);
        CREATE INDEX IF NOT EXISTS idx_workouts_start ON workouts(start_date);
    """)


def _ingest_xml(xml_path: Path, conn: sqlite3.Connection) -> None:
    """Stream-parse export.xml and load records + workouts into SQLite."""
    _create_schema(conn)

    record_batch: list[tuple[str, ...]] = []
    workout_batch: list[tuple[Any, ...]] = []
    batch_size = 10_000
    count = 0

    for _event, elem in iterparse(str(xml_path), events=("end",)):
        tag = elem.tag

        if tag == "Record":
            attrib = elem.attrib
            record_batch.append(
                (
                    _strip_prefix(attrib.get("type", "")),
                    attrib.get("sourceName", ""),
                    attrib.get("unit", ""),
                    attrib.get("value", ""),
                    attrib.get("startDate", ""),
                    attrib.get("endDate", ""),
                )
            )
            count += 1

        elif tag == "Workout":
            attrib = elem.attrib
            # Energy and distance live in child WorkoutStatistics elements
            energy: float | None = None
            distance: float | None = None
            distance_unit: str = ""
            for stat in elem.iter("WorkoutStatistics"):
                stat_type = stat.attrib.get("type", "")
                if "EnergyBurned" in stat_type:
                    with contextlib.suppress(ValueError, TypeError):
                        energy = float(stat.attrib.get("sum", 0))
                elif "Distance" in stat_type:
                    with contextlib.suppress(ValueError, TypeError):
                        distance = float(stat.attrib.get("sum", 0))
                    distance_unit = stat.attrib.get("unit", "")

            # Fallback: some exports put totals directly on the Workout element
            if energy is None:
                try:
                    energy = float(attrib.get("totalEnergyBurned", 0))
                except (ValueError, TypeError):
                    energy = None
            if distance is None:
                try:
                    distance = float(attrib.get("totalDistance", 0))
                except (ValueError, TypeError):
                    distance = None
                distance_unit = attrib.get("totalDistanceUnit", distance_unit)

            workout_batch.append(
                (
                    _strip_prefix(attrib.get("workoutActivityType", "")),
                    attrib.get("sourceName", ""),
                    float(attrib.get("duration", 0)),
                    attrib.get("durationUnit", ""),
                    energy,
                    distance,
                    distance_unit,
                    attrib.get("startDate", ""),
                    attrib.get("endDate", ""),
                )
            )
            count += 1

        # Free memory — critical for large files
        elem.clear()

        if len(record_batch) >= batch_size:
            conn.executemany("INSERT INTO records VALUES (?,?,?,?,?,?)", record_batch)
            record_batch.clear()
        if len(workout_batch) >= batch_size:
            conn.executemany("INSERT INTO workouts VALUES (?,?,?,?,?,?,?,?,?)", workout_batch)
            workout_batch.clear()

        if count % 100_000 == 0 and count > 0:
            print(f"\r  {count:,} elements loaded …", end="", file=sys.stderr)

    # Flush remaining
    if record_batch:
        conn.executemany("INSERT INTO records VALUES (?,?,?,?,?,?)", record_batch)
    if workout_batch:
        conn.executemany("INSERT INTO workouts VALUES (?,?,?,?,?,?,?,?,?)", workout_batch)
    conn.commit()
    print(f"\r  {count:,} elements loaded — done.", file=sys.stderr)


# ---------------------------------------------------------------------------
# Resolve input path (zip or xml)
# ---------------------------------------------------------------------------


def _resolve_xml(input_path: str) -> Path:
    """Return path to export.xml, extracting from zip if necessary."""
    p = Path(input_path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"Input not found: {p}")

    if p.suffix.lower() == ".zip":
        print(f"Extracting export.xml from {p} …", file=sys.stderr)
        tmp_dir = tempfile.mkdtemp(prefix="apple_health_")
        with zipfile.ZipFile(p) as zf:
            # Apple exports nest under apple_health_export/export.xml
            candidates = [n for n in zf.namelist() if n.endswith("export.xml")]
            if not candidates:
                raise FileNotFoundError("No export.xml found inside the zip archive")
            target = candidates[0]
            zf.extract(target, tmp_dir)
            return Path(tmp_dir) / target

    if p.suffix.lower() == ".xml":
        return p

    raise ValueError(f"Expected a .zip or .xml file, got: {p.suffix}")


# ---------------------------------------------------------------------------
# Build the in-memory database
# ---------------------------------------------------------------------------


def _build_db(input_path: str) -> sqlite3.Connection:
    xml_path = _resolve_xml(input_path)
    print(f"Parsing {xml_path} into in-memory SQLite …", file=sys.stderr)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _ingest_xml(xml_path, conn)
    row = conn.execute(
        "SELECT (SELECT count(*) FROM records) AS r, (SELECT count(*) FROM workouts) AS w"
    ).fetchone()
    print(
        f"Ready — {row['r']:,} records, {row['w']:,} workouts in memory.",
        file=sys.stderr,
    )
    return conn


# ---------------------------------------------------------------------------
# MCP server & tools
# ---------------------------------------------------------------------------

mcp = FastMCP("apple-health")

# Will be set in main() before the server starts.
_db: sqlite3.Connection


@mcp.tool()
def query(sql: str) -> str:
    """Execute a read-only SQL query against the health database.

    The database has two tables:
      records(type, source_name, unit, value, start_date, end_date)
      workouts(activity_type, source_name, duration, duration_unit,
               total_energy_kcal, total_distance, distance_unit, start_date, end_date)

    Only SELECT statements are allowed.
    """
    stripped = sql.strip().rstrip(";").strip()
    if not stripped.upper().startswith("SELECT"):
        return json.dumps({"error": "Only SELECT queries are allowed."})

    try:
        cur = _db.execute(stripped)
        columns = [d[0] for d in cur.description]
        rows = cur.fetchall()
        result = [dict(zip(columns, row, strict=True)) for row in rows]
        return json.dumps(result, default=str)
    except sqlite3.Error as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def summary(metric: str, period: str = "day") -> str:
    """Aggregate a health metric by day, week, or month.

    Args:
        metric: The record type (e.g. "StepCount", "HeartRate").
            Use list_metrics() to see available types.
        period: One of "day", "week", or "month".
    """
    period = period.lower()
    if period == "day":
        date_expr = "substr(start_date, 1, 10)"
    elif period == "week":
        date_expr = "strftime('%Y-W%W', substr(start_date, 1, 10))"
    elif period == "month":
        date_expr = "substr(start_date, 1, 7)"
    else:
        return json.dumps({"error": "period must be 'day', 'week', or 'month'."})

    sql = f"""
        SELECT {date_expr} AS period,
               count(*)       AS count,
               round(avg(CAST(value AS REAL)), 2) AS avg_value,
               round(min(CAST(value AS REAL)), 2) AS min_value,
               round(max(CAST(value AS REAL)), 2) AS max_value,
               round(sum(CAST(value AS REAL)), 2) AS sum_value
        FROM records
        WHERE type = ?
        GROUP BY 1
        ORDER BY 1
    """
    try:
        cur = _db.execute(sql, (metric,))
        columns = [d[0] for d in cur.description]
        rows = cur.fetchall()
        if not rows:
            return json.dumps({"error": f"No records found for metric '{metric}'."})
        result = [dict(zip(columns, row, strict=True)) for row in rows]
        return json.dumps(result, default=str)
    except sqlite3.Error as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def list_metrics() -> str:
    """List all distinct record types and their counts."""
    rows = _db.execute(
        "SELECT type, count(*) AS count FROM records GROUP BY type ORDER BY count DESC"
    ).fetchall()
    return json.dumps([dict(row) for row in rows], default=str)


@mcp.tool()
def list_workout_types() -> str:
    """List all distinct workout activity types and their counts."""
    rows = _db.execute(
        "SELECT activity_type, count(*) AS count FROM workouts "
        "GROUP BY activity_type ORDER BY count DESC"
    ).fetchall()
    return json.dumps([dict(row) for row in rows], default=str)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    global _db

    parser = argparse.ArgumentParser(description="Apple Health MCP Server")
    parser.add_argument(
        "--input",
        default=os.environ.get("HEALTH_EXPORT_PATH"),
        help="Path to Apple Health export.zip or export.xml (or set HEALTH_EXPORT_PATH env var)",
    )
    args = parser.parse_args()

    if not args.input:
        parser.error("Provide --input <path> or set the HEALTH_EXPORT_PATH env var.")

    _db = _build_db(args.input)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
