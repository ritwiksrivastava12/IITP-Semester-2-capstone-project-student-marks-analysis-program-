"""SQLite schema, constraint, cascade, and transcript data-access tests."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

import database
import demo_data


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "college_marks_test.db"
        database.init_db(self.db_path)
        self.conn = database.get_connection(self.db_path)
        self.addCleanup(self.conn.close)

    def make_profile(self, name="Test Student", target=8.5):
        self.conn.execute(
            "INSERT INTO profile (id, name, college, degree, branch, target_cgpa) "
            "VALUES (1, ?, ?, ?, ?, ?)",
            (name, "Test College", "B.Tech", "CSE", target),
        )
        self.conn.commit()

    def make_semester(self, number=1, year="2024-25"):
        cursor = self.conn.execute(
            "INSERT INTO semesters (number, academic_year) VALUES (?, ?)",
            (number, year),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def make_subject(
        self,
        semester_id,
        name="Mathematics",
        *,
        code="MA101",
        credits=4,
        maximum=100,
        marks=80,
    ):
        cursor = self.conn.execute(
            "INSERT INTO subjects "
            "(semester_id, name, code, credits, max_marks, marks_obtained) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (semester_id, name, code, credits, maximum, marks),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def test_schema_initializes_new_tables_and_has_no_school_tables(self):
        tables = {
            row["name"]
            for row in database.fetch_all(
                self.conn,
                "SELECT name FROM sqlite_master WHERE type = 'table'",
            )
        }
        self.assertTrue({"profile", "semesters", "subjects"}.issubset(tables))
        for removed in [
            "workspaces",
            "workspace_settings",
            "classes",
            "students",
            "marks",
            "class_subjects",
            "student_subjects",
        ]:
            self.assertNotIn(removed, tables)

    def test_schema_initialization_is_idempotent_and_keeps_data(self):
        self.make_profile("Persistent Student")
        semester_id = self.make_semester(1)
        self.make_subject(semester_id, "Algorithms", marks=91)

        database.init_db(self.db_path)  # Restart-style initialization.

        profile = database.get_profile(self.conn)
        self.assertEqual(profile["name"], "Persistent Student")
        transcript = database.get_transcript_data(self.conn)
        self.assertEqual(len(transcript), 1)
        self.assertEqual(transcript[0]["subjects"][0]["name"], "Algorithms")
        self.assertEqual(transcript[0]["subjects"][0]["marks_obtained"], 91.0)

    def test_foreign_keys_are_enabled(self):
        value = self.conn.execute("PRAGMA foreign_keys").fetchone()[0]
        self.assertEqual(value, 1)

    def test_foreign_key_rejects_subject_without_semester(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO subjects (semester_id, name, credits, max_marks) "
                "VALUES (9999, 'Orphan', 3, 100)"
            )
        self.conn.rollback()

    def test_profile_is_a_singleton(self):
        self.make_profile()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO profile (id, name, target_cgpa) VALUES (1, 'Other', 8)"
            )
        self.conn.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO profile (id, name, target_cgpa) VALUES (2, 'Other', 8)"
            )
        self.conn.rollback()
        count = self.conn.execute("SELECT COUNT(*) FROM profile").fetchone()[0]
        self.assertEqual(count, 1)

    def test_profile_target_cgpa_check(self):
        for target in [-0.1, 10.01]:
            with self.subTest(target=target):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.conn.execute(
                        "INSERT INTO profile (id, name, target_cgpa) "
                        "VALUES (1, 'Bad Target', ?)",
                        (target,),
                    )
                self.conn.rollback()

    def test_semester_number_is_unique_and_bounded(self):
        self.make_semester(4)
        with self.assertRaises(sqlite3.IntegrityError):
            self.make_semester(4)
        self.conn.rollback()
        for number in [0, 13]:
            with self.subTest(number=number):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.make_semester(number)
                self.conn.rollback()

    def test_subject_name_unique_per_semester_but_reusable_elsewhere(self):
        first = self.make_semester(1)
        second = self.make_semester(2)
        self.make_subject(first, "Physics")
        with self.assertRaises(sqlite3.IntegrityError):
            self.make_subject(first, "physics")  # NOCASE uniqueness.
        self.conn.rollback()
        second_id = self.make_subject(second, "Physics")
        self.assertGreater(second_id, 0)

    def test_subject_check_constraints(self):
        semester_id = self.make_semester(1)
        invalid_rows = [
            # name, credits, maximum, marks
            ("Zero credits", 0, 100, 50),
            ("Too many credits", 21, 100, 50),
            ("Zero maximum", 3, 0, 0),
            ("Too high maximum", 3, 1001, 50),
            ("Negative mark", 3, 100, -1),
            ("Mark above maximum", 3, 100, 101),
        ]
        for name, credits, maximum, marks in invalid_rows:
            with self.subTest(name=name):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.conn.execute(
                        "INSERT INTO subjects "
                        "(semester_id, name, credits, max_marks, marks_obtained) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (semester_id, name, credits, maximum, marks),
                    )
                self.conn.rollback()

    def test_blank_mark_is_stored_as_null(self):
        semester_id = self.make_semester(1)
        subject_id = self.make_subject(semester_id, "Pending Subject", marks=None)
        row = database.fetch_one(
            self.conn, "SELECT * FROM subjects WHERE id = ?", (subject_id,)
        )
        self.assertIsNone(row["marks_obtained"])

    def test_deleting_semester_cascades_to_subjects(self):
        semester_id = self.make_semester(1)
        self.make_subject(semester_id, "One")
        self.make_subject(semester_id, "Two")
        self.conn.execute("DELETE FROM semesters WHERE id = ?", (semester_id,))
        self.conn.commit()
        count = self.conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
        self.assertEqual(count, 0)

    def test_transcript_data_groups_and_sorts_semesters_and_subjects(self):
        first = self.make_semester(1, "2024-25")
        second = self.make_semester(2, "2024-25")
        self.make_subject(second, "Networks")
        self.make_subject(first, "Zoology")
        self.make_subject(first, "Algorithms")

        transcript = database.get_transcript_data(self.conn)
        self.assertEqual([row["number"] for row in transcript], [1, 2])
        self.assertEqual(
            [subject["name"] for subject in transcript[0]["subjects"]],
            ["Algorithms", "Zoology"],
        )
        self.assertTrue(transcript[0]["label"].startswith("Semester 1"))
        self.assertIn("2024-25", transcript[0]["label"])

    def test_shared_read_helpers(self):
        semester_id = self.make_semester(3)
        subject_id = self.make_subject(semester_id, "Databases", marks=None)
        semester = database.get_semester(self.conn, semester_id)
        subject = database.get_subject(self.conn, subject_id)
        detailed = database.get_semester_with_subjects(self.conn, semester_id)
        self.assertEqual(semester["number"], 3)
        self.assertEqual(subject["name"], "Databases")
        self.assertEqual(detailed["subjects"][0]["id"], subject_id)
        self.assertEqual(database.count_subjects(self.conn, semester_id), 1)
        self.assertIsNone(database.get_semester(self.conn, 9999))
        self.assertIsNone(database.get_subject(self.conn, 9999))
        self.assertIsNone(database.get_semester_with_subjects(self.conn, 9999))


class DemoDataTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "demo_test.db"
        database.init_db(self.db_path)
        self.conn = database.get_connection(self.db_path)
        self.addCleanup(self.conn.close)

    def test_demo_loads_once_and_has_expected_shape(self):
        summary = demo_data.load_demo(self.conn)
        self.conn.commit()
        self.assertIsNotNone(summary)
        self.assertEqual(summary["semesters"], 4)
        self.assertEqual(summary["subjects"], 20)
        self.assertEqual(summary["marks"], 18)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM profile").fetchone()[0], 1
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM semesters").fetchone()[0], 4
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0], 20
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM subjects WHERE marks_obtained IS NULL"
            ).fetchone()[0],
            2,
        )
        self.assertIsNone(demo_data.load_demo(self.conn))
        self.conn.commit()
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0], 20
        )

    def test_reset_all_removes_profile_semesters_and_subjects(self):
        demo_data.load_demo(self.conn)
        self.conn.commit()
        demo_data.reset_all(self.conn)
        self.conn.commit()
        for table in ["profile", "semesters", "subjects"]:
            with self.subTest(table=table):
                count = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
