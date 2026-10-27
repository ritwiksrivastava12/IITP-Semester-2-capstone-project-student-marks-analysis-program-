"""End-to-end route tests using a temporary single-student database."""

import csv
import io
import tempfile
import unittest
from pathlib import Path

import database
from app import create_app


class RouteTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = str(Path(self.temp_dir.name) / "routes_test.db")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "route-test-secret",
                "DATABASE": self.db_path,
            }
        )
        self.client = self.app.test_client()
        self.client.get("/")
        self.setup_profile()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def token(self):
        with self.client.session_transaction() as session:
            return session["_csrf_token"]

    def post(self, path, data=None, follow_redirects=True):
        payload = dict(data or {})
        payload.setdefault("csrf_token", self.token())
        return self.client.post(path, data=payload, follow_redirects=follow_redirects)

    def query_all(self, sql, params=()):
        connection = database.get_connection(self.db_path)
        try:
            return database.fetch_all(connection, sql, params)
        finally:
            connection.close()

    def query_one(self, sql, params=()):
        connection = database.get_connection(self.db_path)
        try:
            return database.fetch_one(connection, sql, params)
        finally:
            connection.close()

    def setup_profile(self, name="Route Student", target="8.0"):
        response = self.post(
            "/setup",
            {
                "name": name,
                "college": "Test College",
                "degree": "B.Tech",
                "branch": "Computer Science",
                "target_cgpa": target,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.query_one("SELECT COUNT(*) AS count FROM profile")["count"], 1
        )

    def add_semester(self, number=1, year="2024-25"):
        response = self.post(
            "/semesters/new",
            {"number": str(number), "academic_year": year},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        row = self.query_one(
            "SELECT * FROM semesters WHERE number = ?", (number,)
        )
        self.assertIsNotNone(row, "Semester was not created")
        return int(row["id"])

    def add_subject(
        self,
        semester_id,
        name="Algorithms",
        *,
        code="CS301",
        credits="4",
        maximum="100",
        marks="",
    ):
        response = self.post(
            f"/semesters/{semester_id}/subjects/new",
            {
                "name": name,
                "code": code,
                "credits": credits,
                "max_marks": maximum,
                "marks_obtained": marks,
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        row = self.query_one(
            "SELECT * FROM subjects WHERE semester_id = ? AND name = ?",
            (semester_id, name),
        )
        self.assertIsNotNone(row, "Subject was not created")
        return int(row["id"])

    def save_marks(self, semester_id, marks):
        subjects = self.query_all(
            "SELECT id FROM subjects WHERE semester_id = ?", (semester_id,)
        )
        data = {
            f"mark_{row['id']}": "" if marks.get(int(row["id"])) is None else str(marks[int(row["id"])])
            for row in subjects
        }
        return self.post(
            f"/semesters/{semester_id}/marks", data, follow_redirects=True
        )

    def subject_row(self, subject_id):
        return self.query_one("SELECT * FROM subjects WHERE id = ?", (subject_id,))

    # ------------------------------------------------------------------
    # Profile, security and removed school features
    # ------------------------------------------------------------------

    def test_setup_redirects_when_profile_exists(self):
        response = self.client.get("/setup")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard", response.headers["Location"])

    def test_profile_and_target_updates(self):
        response = self.post(
            "/settings/profile",
            {
                "name": "Updated Student",
                "college": "Updated College",
                "degree": "B.Sc",
                "branch": "Computer Science",
            },
        )
        self.assertEqual(response.status_code, 200)
        profile = self.query_one("SELECT * FROM profile")
        self.assertEqual(profile["name"], "Updated Student")
        self.assertEqual(profile["degree"], "B.Sc")

        self.post("/settings/target", {"target_cgpa": "9.10"})
        profile = self.query_one("SELECT * FROM profile")
        self.assertAlmostEqual(profile["target_cgpa"], 9.10)

        response = self.post("/settings/target", {"target_cgpa": "10.5"})
        self.assertIn("between 0 and 10", response.get_data(as_text=True))
        profile = self.query_one("SELECT * FROM profile")
        self.assertAlmostEqual(profile["target_cgpa"], 9.10)

        response = self.post(
            "/settings/profile",
            {"name": "", "college": "", "degree": "", "branch": ""},
        )
        self.assertIn("Your name is required", response.get_data(as_text=True))
        self.assertEqual(self.query_one("SELECT * FROM profile")["name"], "Updated Student")

    def test_csrf_token_required_for_state_changes(self):
        before = self.query_one("SELECT COUNT(*) AS count FROM semesters")["count"]
        response = self.client.post(
            "/semesters/new", data={"number": "2", "academic_year": "2024-25"}
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            "/semesters/new",
            data={
                "number": "2",
                "academic_year": "2024-25",
                "csrf_token": "wrong-token",
            },
        )
        self.assertEqual(response.status_code, 400)
        after = self.query_one("SELECT COUNT(*) AS count FROM semesters")["count"]
        self.assertEqual(before, after)

    def test_removed_school_routes_return_404(self):
        for path in [
            "/workspaces",
            "/classes",
            "/students",
            "/subjects",
            "/marks",
            "/enter-marks",
            "/results/1",
            "/login",
            "/register",
        ]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_dashboard_pages_require_a_profile(self):
        other_temp = tempfile.TemporaryDirectory()
        self.addCleanup(other_temp.cleanup)
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "fresh-secret",
                "DATABASE": str(Path(other_temp.name) / "fresh.db"),
            }
        )
        client = app.test_client()
        response = client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/setup", response.headers["Location"])
        self.assertEqual(client.get("/").status_code, 200)
        self.assertIn("Set up my profile", client.get("/").get_data(as_text=True))

    # ------------------------------------------------------------------
    # Semester CRUD
    # ------------------------------------------------------------------

    def test_semester_crud_and_unique_number_validation(self):
        empty = self.client.get("/semesters")
        self.assertIn("Your transcript is empty", empty.get_data(as_text=True))

        semester_id = self.add_semester(1, "2024-25")
        detail = self.client.get(f"/semesters/{semester_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("Semester 1", detail.get_data(as_text=True))

        response = self.post(
            "/semesters/new",
            {"number": "1", "academic_year": "2025-26"},
            follow_redirects=True,
        )
        self.assertIn("Semester 1 already exists", response.get_data(as_text=True))
        self.assertEqual(
            self.query_one("SELECT COUNT(*) AS count FROM semesters")["count"], 1
        )

        response = self.post(
            "/semesters/new",
            {"number": "13", "academic_year": ""},
            follow_redirects=True,
        )
        self.assertIn("between 1 and 12", response.get_data(as_text=True))
        self.assertEqual(
            self.query_one("SELECT COUNT(*) AS count FROM semesters")["count"], 1
        )

        response = self.post(
            f"/semesters/{semester_id}/edit",
            {"number": "2", "academic_year": "2025-26"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        semester = self.query_one("SELECT * FROM semesters WHERE id = ?", (semester_id,))
        self.assertEqual(semester["number"], 2)
        self.assertEqual(semester["academic_year"], "2025-26")

    def test_semester_delete_cascades_subjects(self):
        semester_id = self.add_semester(1)
        self.add_subject(semester_id, "Networks", code="CS401")
        self.add_subject(semester_id, "Databases", code="CS303")
        response = self.post(
            f"/semesters/{semester_id}/delete", follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.query_one("SELECT COUNT(*) AS count FROM semesters")["count"], 0
        )
        self.assertEqual(
            self.query_one("SELECT COUNT(*) AS count FROM subjects")["count"], 0
        )
        self.assertEqual(self.client.get(f"/semesters/{semester_id}").status_code, 404)

    # ------------------------------------------------------------------
    # Subject CRUD and marks
    # ------------------------------------------------------------------

    def test_subject_validation_edit_and_delete(self):
        semester_id = self.add_semester(1)
        subject_id = self.add_subject(
            semester_id, "Data Structures", code="CS201", credits="4", marks="88"
        )
        subject = self.subject_row(subject_id)
        self.assertEqual(subject["name"], "Data Structures")
        self.assertEqual(subject["marks_obtained"], 88.0)

        # Duplicate names are case-insensitive inside a semester.
        response = self.post(
            f"/semesters/{semester_id}/subjects/new",
            {
                "name": "data structures",
                "code": "",
                "credits": "3",
                "max_marks": "100",
                "marks_obtained": "",
            },
            follow_redirects=True,
        )
        self.assertIn("already exists", response.get_data(as_text=True))
        self.assertEqual(
            self.query_one("SELECT COUNT(*) AS count FROM subjects")["count"], 1
        )

        invalid_cases = [
            {"name": "Bad Credits", "credits": "0", "max_marks": "100"},
            {"name": "Bad Maximum", "credits": "3", "max_marks": "0"},
            {
                "name": "Mark Too High",
                "credits": "3",
                "max_marks": "100",
                "marks_obtained": "101",
            },
        ]
        for data in invalid_cases:
            with self.subTest(name=data["name"]):
                payload = {
                    "name": data["name"],
                    "code": "",
                    "credits": data["credits"],
                    "max_marks": data["max_marks"],
                    "marks_obtained": data.get("marks_obtained", ""),
                }
                response = self.post(
                    f"/semesters/{semester_id}/subjects/new",
                    payload,
                    follow_redirects=True,
                )
                self.assertIn("flash-error", response.get_data(as_text=True))
                self.assertIsNone(
                    self.query_one(
                        "SELECT * FROM subjects WHERE name = ?", (data["name"],)
                    )
                )

        response = self.post(
            f"/subjects/{subject_id}/edit",
            {
                "name": "Advanced Data Structures",
                "code": "CS202",
                "credits": "5",
                "max_marks": "150",
                "marks_obtained": "120",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        subject = self.subject_row(subject_id)
        self.assertEqual(subject["name"], "Advanced Data Structures")
        self.assertEqual(subject["credits"], 5.0)
        self.assertEqual(subject["max_marks"], 150.0)
        self.assertEqual(subject["marks_obtained"], 120.0)

        self.post(f"/subjects/{subject_id}/delete", follow_redirects=True)
        self.assertIsNone(self.subject_row(subject_id))

    def test_marks_pending_zero_validation_and_clearing(self):
        semester_id = self.add_semester(1)
        algorithms = self.add_subject(semester_id, "Algorithms", code="CS301", credits="4")
        databases = self.add_subject(semester_id, "Databases", code="CS303", credits="3")

        # A blank mark is pending, not zero.
        response = self.save_marks(semester_id, {algorithms: 80, databases: None})
        self.assertEqual(response.status_code, 200)
        self.assertIn("in progress", response.get_data(as_text=True).lower())
        self.assertIsNone(self.subject_row(databases)["marks_obtained"])
        self.assertEqual(self.subject_row(algorithms)["marks_obtained"], 80.0)

        # An invalid mark is rejected and no subject is silently changed.
        response = self.save_marks(semester_id, {algorithms: 101, databases: 60})
        self.assertIn("cannot exceed", response.get_data(as_text=True))
        self.assertEqual(self.subject_row(algorithms)["marks_obtained"], 80.0)
        self.assertIsNone(self.subject_row(databases)["marks_obtained"])

        # Negative and non-numeric values are rejected too.
        response = self.save_marks(semester_id, {algorithms: -1, databases: 60})
        self.assertIn("cannot be negative", response.get_data(as_text=True))
        response = self.save_marks(semester_id, {algorithms: "abc", databases: 60})
        self.assertIn("valid number", response.get_data(as_text=True))
        self.assertEqual(self.subject_row(algorithms)["marks_obtained"], 80.0)

        # Zero is a real entered mark: the semester becomes complete but has a backlog.
        self.save_marks(semester_id, {algorithms: 80, databases: 0})
        self.assertEqual(self.subject_row(databases)["marks_obtained"], 0.0)
        detail = self.client.get(f"/semesters/{semester_id}").get_data(as_text=True)
        self.assertIn("Backlog", detail)

        # Blanking a previously saved mark returns it to pending.
        self.save_marks(semester_id, {algorithms: 80, databases: None})
        self.assertIsNone(self.subject_row(databases)["marks_obtained"])
        detail = self.client.get(f"/semesters/{semester_id}").get_data(as_text=True)
        self.assertIn("Provisional", detail)

    # ------------------------------------------------------------------
    # Transcript, analysis, reports and pending-only edge case
    # ------------------------------------------------------------------

    def test_transcript_analysis_and_reports_pages(self):
        semester_id = self.add_semester(1, "2024-25")
        self.add_subject(
            semester_id, "Algorithms", code="CS301", credits="4", marks="92"
        )
        self.add_subject(
            semester_id, "Databases", code="CS303", credits="3", marks="81"
        )
        for path in ["/dashboard", "/semesters", "/results", "/analysis", "/reports"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.content_type)

        transcript = self.client.get("/results").get_data(as_text=True)
        self.assertIn("Academic transcript", transcript)
        self.assertIn("Algorithms", transcript)
        self.assertIn("CGPA", transcript)
        self.assertIn("Target 8.00 CGPA", transcript)

        analysis = self.client.get("/analysis").get_data(as_text=True)
        self.assertIn("Subject ranking", analysis)
        self.assertIn("Grade distribution", analysis)
        self.assertIn("Only your data", analysis)

        reports = self.client.get("/reports").get_data(as_text=True)
        self.assertIn("SGPA &amp; CGPA trend", reports)
        self.assertEqual(reports.count("/charts/"), 5)

    def test_pending_only_transcript_pages_render_without_errors(self):
        semester_id = self.add_semester(1)
        self.add_subject(semester_id, "Theory of Computation", code="CS403", marks="")
        for path in [
            "/dashboard",
            "/semesters",
            f"/semesters/{semester_id}",
            "/results",
            "/analysis",
            "/reports",
        ]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    # ------------------------------------------------------------------
    # CSV, charts and data controls
    # ------------------------------------------------------------------

    def get_csv(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.content_type)
        text = response.get_data(as_text=True)
        self.assertTrue(text.startswith("\ufeff"))
        rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
        return rows, response

    def test_csv_exports(self):
        semester_id = self.add_semester(1, "2024-25")
        self.add_subject(
            semester_id, "Algorithms", code="CS301", credits="4", marks="92"
        )
        pending_id = self.add_subject(
            semester_id, "Mini Project", code="CS405", credits="2", marks=""
        )
        self.assertGreater(pending_id, 0)

        rows, response = self.get_csv("/exports/transcript.csv")
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertIn("Route_Student_transcript.csv", response.headers["Content-Disposition"])
        self.assertEqual(rows[0][3], "Subject")
        self.assertEqual(len(rows), 3)
        algorithms = next(row for row in rows[1:] if row[3] == "Algorithms")
        pending = next(row for row in rows[1:] if row[3] == "Mini Project")
        self.assertEqual(algorithms[6], "92")
        self.assertEqual(algorithms[7], "92.00")
        self.assertEqual(algorithms[8], "O")
        self.assertEqual(algorithms[10], "Passed")
        self.assertEqual(pending[6], "")
        self.assertEqual(pending[8], "")
        self.assertEqual(pending[10], "Pending")

        summary_rows, response = self.get_csv("/exports/semesters.csv")
        self.assertIn("Route_Student_semester_summary.csv", response.headers["Content-Disposition"])
        self.assertEqual(summary_rows[0][0], "Semester")
        self.assertEqual(len(summary_rows), 2)
        self.assertEqual(summary_rows[1][0], "1")
        self.assertEqual(summary_rows[1][2], "2")
        self.assertEqual(summary_rows[1][3], "1")

        self.assertEqual(self.client.get("/exports/unknown.csv").status_code, 404)

    def test_chart_endpoints_return_uncached_pngs(self):
        semester_id = self.add_semester(1)
        self.add_subject(semester_id, "Algorithms", credits="4", marks="90")
        for chart_name in [
            "sgpa_trend",
            "subject_marks",
            "grade_distribution",
            "semester_performance",
            "credit_progress",
        ]:
            with self.subTest(chart=chart_name):
                response = self.client.get(f"/charts/{chart_name}.png")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, "image/png")
                self.assertTrue(response.get_data().startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(self.client.get("/charts/unknown.png").status_code, 404)

    def test_reset_requires_exact_confirmation_and_clears_everything(self):
        semester_id = self.add_semester(1)
        self.add_subject(semester_id, "Algorithms", marks="88")

        response = self.post(
            "/settings/reset", {"confirm_text": "keep my data"}, follow_redirects=True
        )
        self.assertIn("Data was not deleted", response.get_data(as_text=True))
        self.assertEqual(
            self.query_one("SELECT COUNT(*) AS count FROM profile")["count"], 1
        )
        self.assertEqual(
            self.query_one("SELECT COUNT(*) AS count FROM semesters")["count"], 1
        )

        response = self.post(
            "/settings/reset", {"confirm_text": "DELETE"}, follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("All transcript data was deleted", response.get_data(as_text=True))
        self.assertEqual(
            self.query_one("SELECT COUNT(*) AS count FROM profile")["count"], 0
        )
        self.assertEqual(
            self.query_one("SELECT COUNT(*) AS count FROM semesters")["count"], 0
        )
        self.assertEqual(
            self.query_one("SELECT COUNT(*) AS count FROM subjects")["count"], 0
        )

    def test_data_persists_across_a_fresh_application_instance(self):
        semester_id = self.add_semester(1, "2024-25")
        self.add_subject(semester_id, "Algorithms", marks="92")

        restarted_app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "another-secret",
                "DATABASE": self.db_path,
            }
        )
        restarted_client = restarted_app.test_client()
        dashboard = restarted_client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        text = dashboard.get_data(as_text=True)
        self.assertIn("Route Student", text)
        self.assertIn("Semester 1", text)
        self.assertIn("10.00", text)  # 92% = O = 10 grade points.


class NoProfileRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = str(Path(self.temp_dir.name) / "welcome_test.db")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "welcome-test-secret",
                "DATABASE": self.db_path,
            }
        )
        self.client = self.app.test_client()
        self.client.get("/")

    def token(self):
        with self.client.session_transaction() as session:
            return session["_csrf_token"]

    def post(self, path, data=None, follow_redirects=True):
        payload = dict(data or {})
        payload.setdefault("csrf_token", self.token())
        return self.client.post(path, data=payload, follow_redirects=follow_redirects)

    def query_one(self, sql, params=()):
        connection = database.get_connection(self.db_path)
        try:
            return database.fetch_one(connection, sql, params)
        finally:
            connection.close()

    def test_welcome_page_and_onboarding_validation(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("Set up my profile", text)
        self.assertIn("Explore the college demo", text)
        self.assertNotIn("workspace", text.lower())

        response = self.post(
            "/setup",
            {"name": "", "target_cgpa": "8.5"},
            follow_redirects=True,
        )
        self.assertIn("Your name is required", response.get_data(as_text=True))
        self.assertIsNone(self.query_one("SELECT * FROM profile"))

        response = self.post(
            "/setup",
            {"name": "New Student", "target_cgpa": "12"},
            follow_redirects=True,
        )
        self.assertIn("between 0 and 10", response.get_data(as_text=True))
        self.assertIsNone(self.query_one("SELECT * FROM profile"))

    def test_setup_creates_profile_and_redirects_to_dashboard(self):
        response = self.post(
            "/setup",
            {
                "name": "New Student",
                "college": "New College",
                "degree": "B.Tech",
                "branch": "CSE",
                "target_cgpa": "8.5",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard", response.headers["Location"])
        profile = self.query_one("SELECT * FROM profile")
        self.assertEqual(profile["name"], "New Student")
        self.assertAlmostEqual(profile["target_cgpa"], 8.5)

    def test_demo_loads_full_transcript_once(self):
        response = self.post("/demo/load", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("Aarav Mehta", text)
        self.assertIn("9.00", text)
        self.assertIn("College demo loaded", text)
        self.assertEqual(
            self.query_one("SELECT COUNT(*) AS count FROM semesters")["count"], 4
        )
        self.assertEqual(
            self.query_one("SELECT COUNT(*) AS count FROM subjects")["count"], 20
        )
        self.assertEqual(
            self.query_one(
                "SELECT COUNT(*) AS count FROM subjects WHERE marks_obtained IS NULL"
            )["count"],
            2,
        )

        # A second attempt cannot overwrite the existing transcript.
        response = self.post("/demo/load", follow_redirects=True)
        self.assertIn("profile already exists", response.get_data(as_text=True))
        self.assertEqual(
            self.query_one("SELECT COUNT(*) AS count FROM subjects")["count"], 20
        )


if __name__ == "__main__":
    unittest.main()
