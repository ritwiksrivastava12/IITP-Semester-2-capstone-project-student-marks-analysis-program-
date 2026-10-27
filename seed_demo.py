r"""Seed a realistic college student transcript into the application database.

Run from the project root:
    .\.venv\Scripts\python.exe seed_demo.py

The seed is idempotent: if a student profile already exists, it makes no changes.
Use the Settings page to reset data before loading a fresh demo.
"""

from __future__ import annotations

from app import create_app
import database
import demo_data


def seed() -> int:
    app = create_app()
    db_path = app.config["DATABASE"]

    with database.transaction(db_path) as connection:
        summary = demo_data.load_demo(connection)

    if summary is None:
        print(
            "A student profile already exists in "
            f"{db_path}. The demo was not loaded."
        )
        return 0

    print(f"College demo created in {db_path}")
    print(
        "Student: "
        f"{summary['profile']['name']} · "
        f"{summary['profile']['degree']} "
        f"{summary['profile']['branch']}"
    )
    print(
        f"Semesters: {summary['semesters']} | Subjects: {summary['subjects']} | "
        f"Entered marks: {summary['marks']}"
    )
    print("Open the application at http://127.0.0.1:5000/")
    return 0


if __name__ == "__main__":
    raise SystemExit(seed())
