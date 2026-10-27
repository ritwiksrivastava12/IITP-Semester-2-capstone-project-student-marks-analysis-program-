"""Tests that all five Matplotlib charts render valid PNGs at useful states."""

import unittest

import matplotlib.pyplot as plt

import charts
from calculations import calculate_transcript

PROFILE = {
    "name": "Chart Student",
    "college": "Test College",
    "degree": "B.Tech",
    "branch": "CSE",
}


def subject(name, marks, *, credits=3, maximum=100, subject_id=1, code=""):
    return {
        "id": subject_id,
        "name": name,
        "code": code,
        "credits": credits,
        "max_marks": maximum,
        "marks_obtained": marks,
    }


def semester(number, subjects, *, semester_id=1, year="2024-25"):
    return {
        "id": semester_id,
        "number": number,
        "academic_year": year,
        "subjects": subjects,
    }


def populated_transcript():
    return calculate_transcript(
        [
            semester(
                1,
                [
                    subject("Algorithms", 94, credits=4, subject_id=1, code="CS301"),
                    subject("Databases", 81, credits=4, subject_id=2, code="CS303"),
                    subject("Maths", 74, credits=3, subject_id=3, code="MA301"),
                ],
                semester_id=1,
            ),
            semester(
                2,
                [
                    subject("Networks", 88, credits=4, subject_id=4, code="CS401"),
                    subject("Software Engineering", 35, credits=3, subject_id=5, code="CS402"),
                    subject("Web Technologies", None, credits=3, subject_id=6, code="CS404"),
                ],
                semester_id=2,
                year="2025-26",
            ),
        ],
        target_cgpa=8.5,
    )


class ChartTests(unittest.TestCase):
    def tearDown(self):
        plt.close("all")

    def assert_valid_png(self, image):
        self.assertGreater(len(image), 1000)
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_metadata_matches_renderer_map(self):
        self.assertEqual(set(charts.CHART_META), set(charts.CHART_RENDERERS))
        self.assertEqual(len(charts.CHART_RENDERERS), 5)
        self.assertNotIn("not_a_chart", charts.CHART_RENDERERS)

    def test_all_renderers_produce_png_with_data(self):
        transcript = populated_transcript()
        for name, renderer in charts.CHART_RENDERERS.items():
            with self.subTest(chart=name):
                self.assert_valid_png(renderer(transcript, PROFILE))
        self.assertEqual(plt.get_fignums(), [])

    def test_all_renderers_handle_an_empty_transcript(self):
        transcript = calculate_transcript([], target_cgpa=8.5)
        for name, renderer in charts.CHART_RENDERERS.items():
            with self.subTest(chart=name):
                self.assert_valid_png(renderer(transcript, PROFILE))
        self.assertEqual(plt.get_fignums(), [])

    def test_charts_handle_a_transcript_with_only_pending_marks(self):
        transcript = calculate_transcript(
            [
                semester(
                    1,
                    [subject("Pending Subject", None, credits=4, code="CS101")],
                )
            ]
        )
        for name, renderer in charts.CHART_RENDERERS.items():
            with self.subTest(chart=name):
                self.assert_valid_png(renderer(transcript, PROFILE))
        self.assertEqual(plt.get_fignums(), [])

    def test_renderer_handles_missing_profile(self):
        transcript = populated_transcript()
        for name, renderer in charts.CHART_RENDERERS.items():
            with self.subTest(chart=name):
                self.assert_valid_png(renderer(transcript, None))
        self.assertEqual(plt.get_fignums(), [])


if __name__ == "__main__":
    unittest.main()
