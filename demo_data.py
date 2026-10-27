"""College transcript demo data shared by the seed script and the welcome page.

The demo belongs to one fictional student and uses a realistic four-semester
B.Tech Computer Science record. The final semester intentionally has two
pending subjects so the interface can demonstrate provisional SGPA handling.
"""

from __future__ import annotations

import sqlite3

DEMO_PROFILE = {
    "name": "Aarav Mehta",
    "college": "National Institute of Technology",
    "degree": "B.Tech",
    "branch": "Computer Science & Engineering",
    "target_cgpa": 8.5,
}

DEMO_SEMESTERS = [
    {
        "number": 1,
        "academic_year": "2024-25",
        "subjects": [
            ("Linear Algebra", "MA101", 4, 100, 88),
            ("Programming in C", "CS101", 4, 100, 92),
            ("Engineering Physics", "PH101", 3, 100, 79),
            ("Technical Communication", "HS101", 2, 100, 85),
            ("Basic Electrical Engineering", "EE101", 3, 100, 74),
        ],
    },
    {
        "number": 2,
        "academic_year": "2024-25",
        "subjects": [
            ("Data Structures", "CS201", 4, 100, 91),
            ("Discrete Mathematics", "MA201", 3, 100, 84),
            ("Digital Logic Design", "EC201", 3, 100, 77),
            ("Object-Oriented Programming", "CS202", 4, 100, 95),
            ("Environmental Science", "EV201", 2, 100, 81),
        ],
    },
    {
        "number": 3,
        "academic_year": "2025-26",
        "subjects": [
            ("Design & Analysis of Algorithms", "CS301", 4, 100, 89),
            ("Computer Organization", "CS302", 4, 100, 78),
            ("Database Systems", "CS303", 4, 100, 93),
            ("Operating Systems", "CS304", 4, 100, 86),
            ("Probability & Statistics", "MA301", 3, 100, 72),
        ],
    },
    {
        "number": 4,
        "academic_year": "2025-26",
        "subjects": [
            ("Computer Networks", "CS401", 4, 100, 87),
            ("Software Engineering", "CS402", 3, 100, 82),
            ("Theory of Computation", "CS403", 4, 100, None),
            ("Web Technologies", "CS404", 3, 100, 91),
            ("Mini Project", "CS405", 2, 100, None),
        ],
    },
]


def reset_all(connection: sqlite3.Connection) -> None:
    """Remove all personal transcript records, including the profile."""
    connection.execute("DELETE FROM subjects")
    connection.execute("DELETE FROM semesters")
    connection.execute("DELETE FROM profile")
    connection.execute(
        "DELETE FROM sqlite_sequence WHERE name IN ('subjects', 'semesters')"
    )


def load_demo(connection: sqlite3.Connection) -> dict | None:
    """Insert the demo transcript.

    Returns ``None`` without changing anything when a profile already exists.
    """
    existing = connection.execute("SELECT id FROM profile WHERE id = 1").fetchone()
    if existing is not None:
        return None

    # A profile-less database can only contain orphaned rows from an interrupted
    # reset. Clear them so the demo starts from a predictable state.
    reset_all(connection)

    connection.execute(
        "INSERT INTO profile "
        "(id, name, college, degree, branch, target_cgpa) "
        "VALUES (1, ?, ?, ?, ?, ?)",
        (
            DEMO_PROFILE["name"],
            DEMO_PROFILE["college"],
            DEMO_PROFILE["degree"],
            DEMO_PROFILE["branch"],
            DEMO_PROFILE["target_cgpa"],
        ),
    )

    subject_count = 0
    mark_count = 0
    for semester in DEMO_SEMESTERS:
        cursor = connection.execute(
            "INSERT INTO semesters (number, academic_year) VALUES (?, ?)",
            (semester["number"], semester["academic_year"]),
        )
        semester_id = int(cursor.lastrowid)
        for name, code, credits, max_marks, marks in semester["subjects"]:
            connection.execute(
                "INSERT INTO subjects "
                "(semester_id, name, code, credits, max_marks, marks_obtained) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    semester_id,
                    name,
                    code,
                    credits,
                    max_marks,
                    marks,
                ),
            )
            subject_count += 1
            if marks is not None:
                mark_count += 1

    return {
        "profile": DEMO_PROFILE,
        "semesters": len(DEMO_SEMESTERS),
        "subjects": subject_count,
        "marks": mark_count,
    }
