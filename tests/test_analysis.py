"""Tests for loading a transcript from SQLite and shaping analysis rows."""

import tempfile
import unittest
from pathlib import Path

import analysis
import database
import demo_data


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "analysis_test.db"
        database.init_db(self.db_path)
        self.conn = database.get_connection(self.db_path)
        self.addCleanup(self.conn.close)

    def make_profile(self, target=8.5):
        self.conn.execute(
            "INSERT INTO profile (id, name, target_cgpa) VALUES (1, ?, ?)",
            ("Analysis Student", target),
        )
        self.conn.commit()

    def make_semester(self, number, year="2024-25"):
        cursor = self.conn.execute(
            "INSERT INTO semesters (number, academic_year) VALUES (?, ?)",
            (number, year),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def make_subject(self, semester_id, name, marks, credits=3, code=""):
        cursor = self.conn.execute(
            "INSERT INTO subjects "
            "(semester_id, name, code, credits, max_marks, marks_obtained) "
            "VALUES (?, ?, ?, ?, 100, ?)",
            (semester_id, name, code, credits, marks),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def test_empty_transcript_uses_profile_target(self):
        self.make_profile(target=8.75)
        transcript = analysis.load_transcript(self.conn)
        self.assertEqual(transcript["target_cgpa"], 8.75)
        self.assertFalse(transcript["has_data"])
        self.assertIsNone(transcript["cgpa"])
        self.assertEqual(transcript["semester_count"], 0)
        self.assertEqual(analysis.grade_rows(transcript)[0]["share"], 0.0)

    def test_load_transcript_uses_database_rows_and_overrides_target(self):
        self.make_profile(target=8.0)
        first = self.make_semester(1)
        self.make_subject(first, "Algorithms", 90, credits=4, code="CS301")
        self.make_subject(first, "Databases", 80, credits=3, code="CS303")

        transcript = analysis.load_transcript(self.conn, target_cgpa=9.5)
        self.assertEqual(transcript["target_cgpa"], 9.5)
        self.assertAlmostEqual(transcript["cgpa"], (10 * 4 + 9 * 3) / 7)
        self.assertEqual(transcript["subject_count"], 2)
        self.assertEqual(transcript["best_subject"]["name"], "Algorithms")

    def test_grade_rows_include_counts_and_shares(self):
        self.make_profile()
        first = self.make_semester(1)
        self.make_subject(first, "Outstanding", 95, credits=3)
        self.make_subject(first, "Excellent", 85, credits=3)
        self.make_subject(first, "Fail", 20, credits=3)
        transcript = analysis.load_transcript(self.conn)
        rows = {row["letter"]: row for row in analysis.grade_rows(transcript)}
        self.assertEqual(rows["O"]["count"], 1)
        self.assertEqual(rows["A+"]["count"], 1)
        self.assertEqual(rows["F"]["count"], 1)
        self.assertAlmostEqual(rows["O"]["share"], 100 / 3)
        self.assertEqual(rows["B"]["count"], 0)

    def test_semester_subjects_flattens_rows_with_semester_metadata(self):
        first = self.make_semester(1, "2024-25")
        second = self.make_semester(2, "2025-26")
        self.make_subject(first, "Maths", 80)
        self.make_subject(second, "Networks", None)
        transcript = {
            "semesters": [
                {
                    "number": 1,
                    "academic_year": "2024-25",
                    "subjects": [
                        {
                            "name": "Maths",
                            "is_pending": False,
                            "semester_number": 1,
                        }
                    ],
                },
                {
                    "number": 2,
                    "academic_year": "2025-26",
                    "subjects": [
                        {
                            "name": "Networks",
                            "is_pending": True,
                            "semester_number": 2,
                        }
                    ],
                },
            ]
        }
        rows = analysis.semester_subjects(transcript)
        self.assertEqual([row["name"] for row in rows], ["Maths", "Networks"])
        self.assertEqual([row["semester_number"] for row in rows], [1, 2])
        self.assertEqual([row["semester_year"] for row in rows], ["2024-25", "2025-26"])

    def test_demo_transcript_metrics(self):
        demo_data.load_demo(self.conn)
        self.conn.commit()
        transcript = analysis.load_transcript(self.conn)
        self.assertEqual(transcript["semester_count"], 4)
        self.assertEqual(transcript["subject_count"], 20)
        self.assertEqual(transcript["pending_subject_count"], 2)
        self.assertEqual(transcript["completed_semester_count"], 3)
        self.assertAlmostEqual(transcript["cgpa"], 9.0)
        self.assertAlmostEqual(transcript["credits_total"], 67.0)
        self.assertAlmostEqual(transcript["credits_earned"], 61.0)
        self.assertEqual(transcript["active_semester"]["number"], 4)
        self.assertTrue(transcript["active_semester"]["is_provisional"])
        self.assertAlmostEqual(transcript["active_semester"]["sgpa"], 9.3)
        self.assertEqual(transcript["active_semester"]["status"], "IN_PROGRESS")
        self.assertAlmostEqual(transcript["completed_percentage"], 84.2666666667, places=6)


if __name__ == "__main__":
    unittest.main()
