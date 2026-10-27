"""Load a personal transcript from SQLite and calculate its metrics."""

from __future__ import annotations

import sqlite3

import database
from calculations import calculate_transcript


def load_transcript(
    connection: sqlite3.Connection, target_cgpa: float | None = None
) -> dict:
    """Load the single student's semesters and return calculated metrics."""
    if target_cgpa is None:
        profile = database.get_profile(connection)
        target_cgpa = float(profile["target_cgpa"]) if profile else 8.0
    semesters = database.get_transcript_data(connection)
    return calculate_transcript(semesters, target_cgpa=target_cgpa)


def semester_subjects(transcript: dict) -> list[dict]:
    """Flatten graded subjects, useful for tables and CSV-style views."""
    rows: list[dict] = []
    for semester in transcript["semesters"]:
        for subject in semester["subjects"]:
            row = dict(subject)
            row["semester_number"] = semester["number"]
            row["semester_year"] = semester["academic_year"]
            rows.append(row)
    return rows


def grade_rows(transcript: dict) -> list[dict]:
    """Return the grade distribution with share-of-total added."""
    total = sum(item["count"] for item in transcript["grade_distribution"])
    rows = []
    for item in transcript["grade_distribution"]:
        row = dict(item)
        row["share"] = (row["count"] / total * 100) if total else 0.0
        rows.append(row)
    return rows
