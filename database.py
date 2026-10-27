"""SQLite connection, schema, and data access for a personal college transcript.

The application stores one student's own profile, semesters, subjects and marks.
There are deliberately no workspace, teacher, class or multi-student tables.
Every value supplied by a user is passed as a bound SQL parameter instead of
being joined into the SQL string.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DATABASE_NAME = "college_marks.db"


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS profile (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    name         TEXT NOT NULL,
    college      TEXT NOT NULL DEFAULT '',
    degree       TEXT NOT NULL DEFAULT '',
    branch       TEXT NOT NULL DEFAULT '',
    target_cgpa  REAL NOT NULL DEFAULT 8.0
                 CHECK (target_cgpa >= 0 AND target_cgpa <= 10),
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS semesters (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    number        INTEGER NOT NULL UNIQUE CHECK (number BETWEEN 1 AND 12),
    academic_year TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subjects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    semester_id     INTEGER NOT NULL,
    name            TEXT NOT NULL COLLATE NOCASE,
    code            TEXT NOT NULL DEFAULT '',
    credits         REAL NOT NULL CHECK (credits > 0 AND credits <= 20),
    max_marks       REAL NOT NULL DEFAULT 100
                    CHECK (max_marks > 0 AND max_marks <= 1000),
    marks_obtained   REAL
                    CHECK (marks_obtained IS NULL
                           OR (marks_obtained >= 0
                               AND marks_obtained <= max_marks)),
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (semester_id, name),
    FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_subjects_semester
    ON subjects(semester_id, name COLLATE NOCASE);
"""


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection with named columns and foreign keys enabled."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def init_db(db_path: str | Path) -> None:
    """Create the transcript tables if they do not exist. Existing rows remain."""
    connection = get_connection(db_path)
    try:
        connection.executescript(SCHEMA)
        connection.commit()
    finally:
        connection.close()


@contextmanager
def transaction(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Run related statements atomically and close the connection afterwards."""
    connection = get_connection(db_path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def fetch_all(
    connection: sqlite3.Connection, sql: str, params: tuple = ()
) -> list[sqlite3.Row]:
    return connection.execute(sql, params).fetchall()


def fetch_one(
    connection: sqlite3.Connection, sql: str, params: tuple = ()
) -> sqlite3.Row | None:
    return connection.execute(sql, params).fetchone()


# ---------------------------------------------------------------------------
# Common reads
# ---------------------------------------------------------------------------


def get_profile(connection: sqlite3.Connection) -> dict | None:
    row = fetch_one(connection, "SELECT * FROM profile WHERE id = 1")
    return dict(row) if row else None


def get_semesters(connection: sqlite3.Connection) -> list[dict]:
    rows = fetch_all(
        connection,
        "SELECT * FROM semesters ORDER BY number, id",
    )
    return [dict(row) for row in rows]


def get_semester(connection: sqlite3.Connection, semester_id: int) -> dict | None:
    row = fetch_one(
        connection,
        "SELECT * FROM semesters WHERE id = ?",
        (semester_id,),
    )
    return dict(row) if row else None


def get_subjects(
    connection: sqlite3.Connection, semester_id: int
) -> list[dict]:
    rows = fetch_all(
        connection,
        "SELECT * FROM subjects WHERE semester_id = ? "
        "ORDER BY name COLLATE NOCASE, id",
        (semester_id,),
    )
    return [dict(row) for row in rows]


def get_subject(connection: sqlite3.Connection, subject_id: int) -> dict | None:
    row = fetch_one(
        connection,
        "SELECT * FROM subjects WHERE id = ?",
        (subject_id,),
    )
    return dict(row) if row else None


def get_semester_with_subjects(
    connection: sqlite3.Connection, semester_id: int
) -> dict | None:
    semester = get_semester(connection, semester_id)
    if semester is None:
        return None
    semester["subjects"] = get_subjects(connection, semester_id)
    return semester


def get_transcript_data(connection: sqlite3.Connection) -> list[dict]:
    """Return semesters ordered by number, with their subjects attached."""
    semesters = get_semesters(connection)
    subjects_by_semester: dict[int, list[dict]] = {}
    for row in fetch_all(
        connection,
        "SELECT * FROM subjects ORDER BY semester_id, name COLLATE NOCASE, id",
    ):
        subject = dict(row)
        subjects_by_semester.setdefault(int(subject["semester_id"]), []).append(
            subject
        )
    for semester in semesters:
        semester["subjects"] = subjects_by_semester.get(int(semester["id"]), [])
        semester["label"] = semester_label(semester)
    return semesters


def semester_label(semester: sqlite3.Row | dict | None) -> str:
    """Return a human-readable semester label."""
    if not semester:
        return "Semester"
    data = dict(semester)
    number = data.get("number")
    label = f"Semester {number}" if number is not None else "Semester"
    year = str(data.get("academic_year") or "").strip()
    if year:
        label += f" · {year}"
    return label


def count_subjects(connection: sqlite3.Connection, semester_id: int) -> int:
    row = fetch_one(
        connection,
        "SELECT COUNT(*) AS count FROM subjects WHERE semester_id = ?",
        (semester_id,),
    )
    return int(row["count"]) if row else 0
