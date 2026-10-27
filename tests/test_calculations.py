"""Unit tests for the college grade, SGPA and CGPA calculations."""

import unittest

from calculations import (
    BACKLOG,
    CLEARED,
    EMPTY,
    FAIL,
    IN_PROGRESS,
    PASS,
    PENDING,
    calculate_semester,
    calculate_transcript,
    grade_for,
    parse_optional_mark,
    safe_percentage,
    validate_subject_configuration,
    validate_target_cgpa,
)


def subject(
    name,
    marks,
    *,
    credits=3,
    maximum=100,
    subject_id=1,
    code="",
):
    return {
        "id": subject_id,
        "name": name,
        "code": code,
        "credits": credits,
        "max_marks": maximum,
        "marks_obtained": marks,
    }


def semester(number, subjects, *, semester_id=1, year="2025-26"):
    return {
        "id": semester_id,
        "number": number,
        "academic_year": year,
        "subjects": subjects,
    }


class GradeScaleTests(unittest.TestCase):
    def test_grade_boundaries(self):
        cases = [
            (100, "O", 10),
            (90, "O", 10),
            (89.99, "A+", 9),
            (80, "A+", 9),
            (79.99, "A", 8),
            (70, "A", 8),
            (69.99, "B+", 7),
            (60, "B+", 7),
            (59.99, "B", 6),
            (50, "B", 6),
            (49.99, "C", 5),
            (40, "C", 5),
            (39.99, "F", 0),
            (0, "F", 0),
        ]
        for percentage, letter, points in cases:
            with self.subTest(percentage=percentage):
                grade = grade_for(percentage)
                self.assertEqual(grade["letter"], letter)
                self.assertEqual(grade["points"], points)

    def test_safe_percentage_never_divides_by_zero(self):
        self.assertEqual(safe_percentage(50, 0), 0.0)
        self.assertEqual(safe_percentage(None, 100), 0.0)
        self.assertAlmostEqual(safe_percentage(45, 50), 90.0)


class SemesterCalculationTests(unittest.TestCase):
    def test_empty_semester_status(self):
        result = calculate_semester(semester(1, []))
        self.assertEqual(result["status"], EMPTY)
        self.assertFalse(result["completed"])
        self.assertIsNone(result["sgpa"])
        self.assertIsNone(result["percentage"])

    def test_pending_mark_is_not_zero_and_sgpa_is_provisional(self):
        result = calculate_semester(
            semester(
                1,
                [
                    subject("Maths", 80, credits=4, subject_id=1),
                    subject("Physics", None, credits=3, subject_id=2),
                ],
            )
        )
        physics = next(row for row in result["subjects"] if row["name"] == "Physics")
        self.assertEqual(physics["status"], PENDING)
        self.assertIsNone(physics["marks_obtained"])
        self.assertIsNone(physics["grade_points"])
        self.assertEqual(result["status"], IN_PROGRESS)
        self.assertFalse(result["completed"])
        self.assertTrue(result["is_provisional"])
        self.assertAlmostEqual(result["sgpa"], 9.0)  # 80% = A+ = 9 points.
        self.assertEqual(result["credits_pending"], 3)
        self.assertAlmostEqual(result["percentage"], 80.0)

    def test_sgpa_is_credit_weighted(self):
        result = calculate_semester(
            semester(
                1,
                [
                    subject("Algorithms", 95, credits=4, subject_id=1),  # O = 10
                    subject("Databases", 75, credits=3, subject_id=2),  # A = 8
                ],
            )
        )
        self.assertAlmostEqual(result["sgpa"], (10 * 4 + 8 * 3) / 7)
        self.assertEqual(result["credits_total"], 7)
        self.assertEqual(result["credits_earned"], 7)
        self.assertEqual(result["status"], CLEARED)
        self.assertTrue(result["completed"])

    def test_failed_subject_counts_as_zero_points_and_backlog(self):
        result = calculate_semester(
            semester(
                1,
                [
                    subject("Maths", 30, credits=4, subject_id=1),  # F = 0
                    subject("English", 90, credits=2, subject_id=2),  # O = 10
                ],
            )
        )
        failed = next(row for row in result["subjects"] if row["name"] == "Maths")
        self.assertEqual(failed["status"], FAIL)
        self.assertEqual(failed["grade_points"], 0)
        self.assertAlmostEqual(result["sgpa"], 20 / 6)
        self.assertEqual(result["status"], BACKLOG)
        self.assertEqual(result["credits_backlog"], 4)
        self.assertEqual(result["credits_earned"], 2)


class TranscriptCalculationTests(unittest.TestCase):
    def setUp(self):
        self.semesters = [
            semester(
                1,
                [
                    subject("Maths", 90, credits=4, subject_id=1),
                    subject("Physics", 80, credits=3, subject_id=2),
                ],
                semester_id=1,
                year="2024-25",
            ),
            semester(
                2,
                [
                    subject("Data Structures", 70, credits=4, subject_id=3),
                    subject("English", 60, credits=2, subject_id=4),
                ],
                semester_id=2,
                year="2024-25",
            ),
        ]

    def test_cgpa_uses_credits_across_complete_semesters(self):
        transcript = calculate_transcript(self.semesters, target_cgpa=8.0)
        # Semester 1: 10*4 + 9*3 = 67 / 7. Semester 2: 8*4 + 7*2 = 46 / 6.
        expected = (67 + 46) / (7 + 6)
        self.assertAlmostEqual(transcript["cgpa"], expected)
        self.assertAlmostEqual(transcript["completed_percentage"], (90 + 80 + 70 + 60) / 4)
        self.assertEqual(transcript["completed_semester_count"], 2)
        self.assertTrue(transcript["target_met"])

    def test_in_progress_semester_is_excluded_from_official_cgpa(self):
        self.semesters.append(
            semester(
                3,
                [
                    subject("Networks", 95, credits=4, subject_id=5),
                    subject("Project", None, credits=2, subject_id=6),
                ],
                semester_id=3,
            )
        )
        transcript = calculate_transcript(self.semesters)
        self.assertAlmostEqual(transcript["cgpa"], (67 + 46) / 13)
        self.assertEqual(transcript["completed_semester_count"], 2)
        self.assertTrue(transcript["has_pending"])
        active = transcript["active_semester"]
        self.assertEqual(active["number"], 3)
        self.assertAlmostEqual(active["sgpa"], 10.0)
        self.assertTrue(active["is_provisional"])
        self.assertEqual(transcript["pending_subject_count"], 1)

    def test_backlog_is_included_in_cgpa_with_zero_points(self):
        semesters = [
            semester(
                1,
                [
                    subject("Maths", 30, credits=4, subject_id=1),
                    subject("English", 90, credits=2, subject_id=2),
                ],
            )
        ]
        transcript = calculate_transcript(semesters)
        self.assertAlmostEqual(transcript["cgpa"], 20 / 6)
        self.assertTrue(transcript["has_backlog"])
        self.assertEqual(transcript["failed_subject_count"], 1)
        self.assertEqual(transcript["credits_backlog"], 4)

    def test_percentage_only_uses_completed_semesters(self):
        self.semesters.append(
            semester(
                3,
                [
                    subject("Networks", 100, credits=4, subject_id=5),
                    subject("Project", None, credits=2, subject_id=6),
                ],
                semester_id=3,
            )
        )
        transcript = calculate_transcript(self.semesters)
        self.assertAlmostEqual(transcript["completed_percentage"], 75.0)
        self.assertAlmostEqual(transcript["graded_percentage"], 80.0)

    def test_target_gap_and_missing_cgpa(self):
        empty = calculate_transcript([], target_cgpa=9.0)
        self.assertIsNone(empty["cgpa"])
        self.assertIsNone(empty["target_gap"])
        self.assertFalse(empty["has_data"])

        transcript = calculate_transcript(self.semesters, target_cgpa=9.9)
        self.assertAlmostEqual(transcript["target_gap"], 9.9 - transcript["cgpa"])
        self.assertFalse(transcript["target_met"])

    def test_best_and_weakest_subjects_and_semesters(self):
        transcript = calculate_transcript(self.semesters)
        self.assertEqual(transcript["best_subject"]["name"], "Maths")
        self.assertEqual(transcript["weakest_subject"]["name"], "English")
        self.assertEqual(transcript["best_semester"]["number"], 1)
        self.assertEqual(transcript["worst_semester"]["number"], 2)
        self.assertEqual(transcript["grade_distribution"][0]["letter"], "O")
        self.assertEqual(transcript["grade_distribution"][0]["count"], 1)

    def test_next_semester_number_and_latest(self):
        transcript = calculate_transcript(self.semesters)
        self.assertEqual(transcript["next_semester_number"], 3)
        self.assertEqual(transcript["latest_semester"]["number"], 2)
        self.assertEqual(transcript["active_semester"]["number"], 2)

    def test_semesters_are_sorted_even_when_input_is_not(self):
        transcript = calculate_transcript(list(reversed(self.semesters)))
        self.assertEqual(
            [row["number"] for row in transcript["semesters"]], [1, 2]
        )


class ValidationTests(unittest.TestCase):
    def test_optional_mark_allows_blank_and_zero(self):
        self.assertIsNone(parse_optional_mark("", 100, "Maths"))
        self.assertIsNone(parse_optional_mark(None, 100, "Maths"))
        self.assertEqual(parse_optional_mark("0", 100, "Maths"), 0.0)
        self.assertEqual(parse_optional_mark("85.5", 100, "Maths"), 85.5)

    def test_optional_mark_rejects_invalid_values(self):
        for value in ["-1", "101", "abc", "NaN", "Infinity"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_optional_mark(value, 100, "Maths")

    def test_subject_configuration_validation(self):
        self.assertEqual(validate_subject_configuration("3", "100"), (3.0, 100.0))
        for credits, maximum in [("0", "100"), ("21", "100"), ("3", "0"), ("3", "1001")]:
            with self.subTest(credits=credits, maximum=maximum):
                with self.assertRaises(ValueError):
                    validate_subject_configuration(credits, maximum)

    def test_target_cgpa_validation(self):
        self.assertEqual(validate_target_cgpa("8.5"), 8.5)
        for value in ["-0.1", "10.1", "abc", ""]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_target_cgpa(value)


if __name__ == "__main__":
    unittest.main()
