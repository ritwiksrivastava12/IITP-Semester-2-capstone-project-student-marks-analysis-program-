"""CampusMarks — a local, single-student college transcript application.

The app intentionally has no login, teacher tools, classes or student directory.
It stores one student's profile, semester subjects and marks, then derives SGPA,
CGPA, percentages, grades and personal reports from those records.
"""

from __future__ import annotations

import csv
import hmac
import io
import os
import re
import secrets
import sqlite3
import time
from datetime import date
from functools import wraps
from pathlib import Path

from flask import (
    Blueprint,
    Flask,
    Response,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import analysis as analytics
import charts
import database
import demo_data
from calculations import (
    BACKLOG,
    CLEARED,
    EMPTY,
    FAIL,
    IN_PROGRESS,
    PASS,
    PASS_PERCENTAGE,
    PENDING,
    GRADE_BANDS,
    parse_optional_mark,
    validate_subject_configuration,
    validate_target_cgpa,
)

BASE_DIR = Path(__file__).resolve().parent
bp = Blueprint("main", __name__)

STATUS_LABELS = {
    CLEARED: "Cleared",
    BACKLOG: "Backlog",
    IN_PROGRESS: "In progress",
    EMPTY: "Not started",
    PASS: "Passed",
    FAIL: "Failed",
    PENDING: "Pending",
}


# ---------------------------------------------------------------------------
# App factory and request lifecycle
# ---------------------------------------------------------------------------


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get(
            "SECRET_KEY", "campuses-marks-local-development-key"
        ),
        DATABASE=os.environ.get(
            "MARKS_DATABASE",
            str(Path(app.instance_path) / database.DEFAULT_DATABASE_NAME),
        ),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    database.init_db(app.config["DATABASE"])
    app.register_blueprint(bp)

    @app.teardown_appcontext
    def close_db(_exception=None):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        if response.mimetype in {"text/html", "text/csv"}:
            response.headers.setdefault("Cache-Control", "no-store, max-age=0")
        return response

    @app.errorhandler(400)
    def bad_request(error):
        return render_template(
            "errors/error.html",
            code=400,
            title="Bad request",
            message=getattr(
                error, "description", "The request could not be processed."
            ),
        ), 400

    @app.errorhandler(404)
    def not_found(_error):
        return render_template(
            "errors/error.html",
            code=404,
            title="Page not found",
            message="That page or transcript record does not exist.",
        ), 404

    @app.errorhandler(413)
    def too_large(_error):
        return render_template(
            "errors/error.html",
            code=413,
            title="Request too large",
            message="The submitted form was too large to process.",
        ), 413

    @app.errorhandler(500)
    def server_error(_error):
        # Flask logs the real exception; the student sees a friendly message.
        return render_template(
            "errors/error.html",
            code=500,
            title="Something went wrong",
            message="The request could not be completed. Please try again.",
        ), 500

    return app


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = database.get_connection(current_app.config["DATABASE"])
    return g.db


def csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


@bp.before_app_request
def load_request_context():
    g.profile = database.get_profile(get_db())
    csrf_token()

    if request.method == "POST":
        expected = session.get("_csrf_token", "")
        submitted = request.form.get("csrf_token", "")
        if not submitted or not expected or not hmac.compare_digest(
            str(submitted), str(expected)
        ):
            abort(
                400,
                description=(
                    "The security token was missing or invalid. "
                    "Reload the page and try again."
                ),
            )


@bp.app_context_processor
def inject_template_globals():
    return {
        "profile": getattr(g, "profile", None),
        "csrf_token": csrf_token,
        "today": date.today(),
        "grade_bands": GRADE_BANDS,
        "pass_percentage": PASS_PERCENTAGE,
    }


@bp.app_template_filter("num")
def number_filter(value, places: int = 2):
    if value is None or value == "":
        return "—"
    try:
        return f"{float(value):,.{places}f}"
    except (TypeError, ValueError):
        return "—"


@bp.app_template_filter("input_num")
def input_number_filter(value):
    if value is None:
        return ""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return ""


@bp.app_template_filter("date_only")
def date_filter(value):
    if not value:
        return "—"
    return str(value)[:10]


@bp.app_template_filter("initials")
def initials_filter(value):
    parts = [
        part for part in str(value or "").split() if part and part[0].isalnum()
    ]
    if not parts:
        return "?"
    return "".join(part[0].upper() for part in parts[:2])


@bp.app_template_filter("status_label")
def status_label_filter(value):
    return STATUS_LABELS.get(value, str(value or "—").title())


@bp.app_template_filter("status_class")
def status_class_filter(value):
    return str(value or "").lower().replace("_", "-")


@bp.app_template_filter("grade_class")
def grade_class_filter(value):
    text = str(value or "").strip().lower()
    if text == "a+":
        return "a-plus"
    return text or "none"


def profile_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if getattr(g, "profile", None) is None:
            flash("Set up your student profile to continue.", "error")
            return redirect(url_for("main.setup"))
        return view(*args, **kwargs)

    return wrapped


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def clean_text(
    raw: object,
    label: str,
    *,
    required: bool = True,
    max_length: int = 100,
) -> str:
    value = str(raw or "").strip()
    if not value:
        if required:
            raise ValueError(f"{label} is required.")
        return ""
    if len(value) > max_length:
        raise ValueError(f"{label} must be {max_length} characters or fewer.")
    return value


def parse_integer(
    raw: object, label: str, *, minimum: int, maximum: int
) -> int:
    text = str(raw or "").strip()
    if not text:
        raise ValueError(f"{label} is required.")
    try:
        number = int(text)
    except ValueError:
        raise ValueError(f"{label} must be a whole number.") from None
    if number < minimum or number > maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}.")
    return number


def fetch_semester_or_404(semester_id: int) -> dict:
    row = database.get_semester(get_db(), semester_id)
    if row is None:
        abort(404)
    return row


def fetch_subject_or_404(subject_id: int) -> dict:
    row = database.get_subject(get_db(), subject_id)
    if row is None:
        abort(404)
    return row


def transcript_snapshot() -> dict:
    profile = getattr(g, "profile", None) or database.get_profile(get_db())
    target = float(profile["target_cgpa"]) if profile else 8.0
    return analytics.load_transcript(get_db(), target_cgpa=target)


def semester_number_exists(
    number: int, exclude_semester_id: int | None = None
) -> bool:
    if exclude_semester_id is None:
        row = database.fetch_one(
            get_db(),
            "SELECT id FROM semesters WHERE number = ?",
            (number,),
        )
    else:
        row = database.fetch_one(
            get_db(),
            "SELECT id FROM semesters WHERE number = ? AND id <> ?",
            (number, exclude_semester_id),
        )
    return row is not None


def validate_semester_form(exclude_id: int | None = None) -> dict:
    number = parse_integer(
        request.form.get("number"), "Semester number", minimum=1, maximum=12
    )
    if semester_number_exists(number, exclude_id):
        raise ValueError(f"Semester {number} already exists.")
    academic_year = clean_text(
        request.form.get("academic_year"),
        "Academic year",
        required=False,
        max_length=20,
    )
    return {"number": number, "academic_year": academic_year}


def validate_subject_form(subject_name_hint: str = "Subject") -> dict:
    name = clean_text(
        request.form.get("name"), "Subject name", required=True, max_length=80
    )
    code = clean_text(
        request.form.get("code"),
        "Subject code",
        required=False,
        max_length=20,
    )
    credits, max_marks = validate_subject_configuration(
        request.form.get("credits"), request.form.get("max_marks")
    )
    marks = parse_optional_mark(
        request.form.get("marks_obtained"),
        max_marks,
        name or subject_name_hint,
    )
    return {
        "name": name,
        "code": code,
        "credits": credits,
        "max_marks": max_marks,
        "marks_obtained": marks,
    }


def safe_download_part(value: str, fallback: str = "student") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return cleaned[:50] or fallback


# ---------------------------------------------------------------------------
# Welcome, onboarding and profile
# ---------------------------------------------------------------------------


@bp.route("/")
def index():
    if g.profile:
        return redirect(url_for("main.dashboard"))
    return render_template("welcome.html")


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if g.profile:
        return redirect(url_for("main.dashboard"))

    form_values = {
        "name": "",
        "college": "",
        "degree": "",
        "branch": "",
        "target_cgpa": "8.5",
    }
    if request.method == "POST":
        form_values = {
            "name": request.form.get("name", "").strip(),
            "college": request.form.get("college", "").strip(),
            "degree": request.form.get("degree", "").strip(),
            "branch": request.form.get("branch", "").strip(),
            "target_cgpa": request.form.get("target_cgpa", "").strip(),
        }
        try:
            name = clean_text(
                form_values["name"], "Your name", required=True, max_length=80
            )
            college = clean_text(
                form_values["college"],
                "College name",
                required=False,
                max_length=120,
            )
            degree = clean_text(
                form_values["degree"],
                "Degree",
                required=False,
                max_length=60,
            )
            branch = clean_text(
                form_values["branch"],
                "Branch",
                required=False,
                max_length=80,
            )
            target = validate_target_cgpa(form_values["target_cgpa"])
            with get_db() as connection:
                connection.execute(
                    "INSERT INTO profile "
                    "(id, name, college, degree, branch, target_cgpa) "
                    "VALUES (1, ?, ?, ?, ?, ?)",
                    (name, college, degree, branch, target),
                )
            flash("Your student profile is ready.", "success")
            return redirect(url_for("main.dashboard"))
        except ValueError as error:
            flash(str(error), "error")
        except sqlite3.IntegrityError:
            flash(
                "A profile already exists. Edit it from Settings instead.",
                "error",
            )

    return render_template("setup.html", form_values=form_values)


@bp.route("/demo/load", methods=["POST"])
def load_demo():
    if g.profile:
        flash(
            "A profile already exists. Reset your data before loading the demo.",
            "error",
        )
        return redirect(url_for("main.dashboard"))

    with get_db() as connection:
        summary = demo_data.load_demo(connection)
    if summary is None:
        flash("The demo could not be loaded.", "error")
        return redirect(url_for("main.index"))

    flash(
        "College demo loaded: 4 semesters, "
        f"{summary['subjects']} subjects and {summary['marks']} entered marks.",
        "success",
    )
    return redirect(url_for("main.dashboard"))


# ---------------------------------------------------------------------------
# Dashboard and semester pages
# ---------------------------------------------------------------------------


@bp.route("/dashboard")
@profile_required
def dashboard():
    transcript = transcript_snapshot()
    active = transcript["active_semester"] or transcript["latest_semester"]
    recent_semesters = sorted(
        transcript["semesters"],
        key=lambda semester: semester["number"],
        reverse=True,
    )[:4]
    return render_template(
        "dashboard.html",
        transcript=transcript,
        active_semester=active,
        recent_semesters=recent_semesters,
        chart_version=int(time.time()),
    )


@bp.route("/semesters")
@profile_required
def semesters():
    transcript = transcript_snapshot()
    return render_template("semesters.html", transcript=transcript)


@bp.route("/semesters/new", methods=["GET", "POST"])
@profile_required
def semester_new():
    transcript = transcript_snapshot()
    form_values = {
        "number": str(transcript["next_semester_number"] or ""),
        "academic_year": "",
    }
    if request.method == "POST":
        form_values = {
            "number": request.form.get("number", "").strip(),
            "academic_year": request.form.get("academic_year", "").strip(),
        }
        try:
            values = validate_semester_form()
            with get_db() as connection:
                cursor = connection.execute(
                    "INSERT INTO semesters (number, academic_year) VALUES (?, ?)",
                    (values["number"], values["academic_year"]),
                )
            flash(f"Semester {values['number']} created.", "success")
            return redirect(
                url_for("main.semester_detail", semester_id=cursor.lastrowid)
            )
        except ValueError as error:
            flash(str(error), "error")
        except sqlite3.IntegrityError:
            flash("A semester with that number already exists.", "error")

    return render_template(
        "semester_form.html",
        form_values=form_values,
        form_heading="Add a semester",
        form_kicker="Semester setup",
        submit_label="Create semester",
        form_action=url_for("main.semester_new"),
        cancel_url=url_for("main.semesters"),
    )


@bp.route("/semesters/<int:semester_id>/edit", methods=["GET", "POST"])
@profile_required
def semester_edit(semester_id: int):
    semester = fetch_semester_or_404(semester_id)
    form_values = {
        "number": str(semester["number"]),
        "academic_year": semester["academic_year"] or "",
    }
    if request.method == "POST":
        form_values = {
            "number": request.form.get("number", "").strip(),
            "academic_year": request.form.get("academic_year", "").strip(),
        }
        try:
            values = validate_semester_form(exclude_id=semester_id)
            with get_db() as connection:
                connection.execute(
                    "UPDATE semesters SET number = ?, academic_year = ? WHERE id = ?",
                    (
                        values["number"],
                        values["academic_year"],
                        semester_id,
                    ),
                )
            flash("Semester details updated.", "success")
            return redirect(
                url_for("main.semester_detail", semester_id=semester_id)
            )
        except ValueError as error:
            flash(str(error), "error")
        except sqlite3.IntegrityError:
            flash("A semester with that number already exists.", "error")

    return render_template(
        "semester_form.html",
        semester=semester,
        form_values=form_values,
        form_heading=f"Edit Semester {semester['number']}",
        form_kicker="Semester setup",
        submit_label="Save semester",
        form_action=url_for(
            "main.semester_edit", semester_id=semester_id
        ),
        cancel_url=url_for(
            "main.semester_detail", semester_id=semester_id
        ),
    )


@bp.route("/semesters/<int:semester_id>/delete", methods=["POST"])
@profile_required
def semester_delete(semester_id: int):
    semester = fetch_semester_or_404(semester_id)
    subject_count = database.count_subjects(get_db(), semester_id)
    with get_db() as connection:
        connection.execute("DELETE FROM semesters WHERE id = ?", (semester_id,))
    flash(
        f"Semester {semester['number']} deleted with {subject_count} "
        f"subject{'s' if subject_count != 1 else ''}.",
        "success",
    )
    return redirect(url_for("main.semesters"))


@bp.route("/semesters/<int:semester_id>")
@profile_required
def semester_detail(semester_id: int):
    transcript = transcript_snapshot()
    semester = next(
        (
            row
            for row in transcript["semesters"]
            if int(row["id"]) == int(semester_id)
        ),
        None,
    )
    if semester is None:
        abort(404)
    return render_template(
        "semester_detail.html",
        transcript=transcript,
        semester=semester,
    )


@bp.route("/semesters/<int:semester_id>/subjects/new", methods=["GET", "POST"])
@profile_required
def subject_new(semester_id: int):
    semester = fetch_semester_or_404(semester_id)
    form_values = {
        "name": "",
        "code": "",
        "credits": "3",
        "max_marks": "100",
        "marks_obtained": "",
    }
    if request.method == "POST":
        form_values = {
            "name": request.form.get("name", "").strip(),
            "code": request.form.get("code", "").strip(),
            "credits": request.form.get("credits", "").strip(),
            "max_marks": request.form.get("max_marks", "").strip(),
            "marks_obtained": request.form.get("marks_obtained", "").strip(),
        }
        try:
            values = validate_subject_form()
            with get_db() as connection:
                connection.execute(
                    "INSERT INTO subjects "
                    "(semester_id, name, code, credits, max_marks, marks_obtained) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        semester_id,
                        values["name"],
                        values["code"],
                        values["credits"],
                        values["max_marks"],
                        values["marks_obtained"],
                    ),
                )
            flash(f'Subject "{values["name"]}" added.', "success")
            return redirect(
                url_for("main.semester_detail", semester_id=semester_id)
            )
        except ValueError as error:
            flash(str(error), "error")
        except sqlite3.IntegrityError:
            flash(
                "That subject already exists in this semester.",
                "error",
            )

    return render_template(
        "subject_form.html",
        semester=semester,
        subject=None,
        form_values=form_values,
        form_heading="Add a subject",
        form_kicker="Subject setup",
        submit_label="Add subject",
        form_action=url_for(
            "main.subject_new", semester_id=semester_id
        ),
        cancel_url=url_for(
            "main.semester_detail", semester_id=semester_id
        ),
    )


@bp.route("/subjects/<int:subject_id>/edit", methods=["GET", "POST"])
@profile_required
def subject_edit(subject_id: int):
    subject = fetch_subject_or_404(subject_id)
    semester = fetch_semester_or_404(int(subject["semester_id"]))
    form_values = {
        "name": subject["name"],
        "code": subject["code"] or "",
        "credits": f"{float(subject['credits']):g}",
        "max_marks": f"{float(subject['max_marks']):g}",
        "marks_obtained": (
            f"{float(subject['marks_obtained']):g}"
            if subject["marks_obtained"] is not None
            else ""
        ),
    }
    if request.method == "POST":
        form_values = {
            "name": request.form.get("name", "").strip(),
            "code": request.form.get("code", "").strip(),
            "credits": request.form.get("credits", "").strip(),
            "max_marks": request.form.get("max_marks", "").strip(),
            "marks_obtained": request.form.get("marks_obtained", "").strip(),
        }
        try:
            values = validate_subject_form()
            with get_db() as connection:
                connection.execute(
                    "UPDATE subjects SET name = ?, code = ?, credits = ?, "
                    "max_marks = ?, marks_obtained = ? WHERE id = ?",
                    (
                        values["name"],
                        values["code"],
                        values["credits"],
                        values["max_marks"],
                        values["marks_obtained"],
                        subject_id,
                    ),
                )
            flash("Subject updated.", "success")
            return redirect(
                url_for(
                    "main.semester_detail",
                    semester_id=int(subject["semester_id"]),
                )
            )
        except ValueError as error:
            flash(str(error), "error")
        except sqlite3.IntegrityError:
            flash(
                "That subject name already exists in this semester.",
                "error",
            )

    return render_template(
        "subject_form.html",
        semester=semester,
        subject=subject,
        form_values=form_values,
        form_heading=f"Edit {subject['name']}",
        form_kicker="Subject setup",
        submit_label="Save subject",
        form_action=url_for(
            "main.subject_edit", subject_id=subject_id
        ),
        cancel_url=url_for(
            "main.semester_detail", semester_id=int(subject["semester_id"])
        ),
    )


@bp.route("/subjects/<int:subject_id>/delete", methods=["POST"])
@profile_required
def subject_delete(subject_id: int):
    subject = fetch_subject_or_404(subject_id)
    semester_id = int(subject["semester_id"])
    with get_db() as connection:
        connection.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    flash(f'Subject "{subject["name"]}" deleted.', "success")
    return redirect(url_for("main.semester_detail", semester_id=semester_id))


@bp.route("/semesters/<int:semester_id>/marks", methods=["POST"])
@profile_required
def save_marks(semester_id: int):
    fetch_semester_or_404(semester_id)
    subjects = database.get_subjects(get_db(), semester_id)
    if not subjects:
        flash("Add a subject before entering marks.", "error")
        return redirect(
            url_for("main.semester_detail", semester_id=semester_id)
        )

    values: dict[int, float | None] = {}
    errors: list[str] = []
    for subject in subjects:
        raw = request.form.get(f"mark_{subject['id']}")
        try:
            values[int(subject["id"])] = parse_optional_mark(
                raw, float(subject["max_marks"]), subject["name"]
            )
        except ValueError as error:
            errors.append(str(error))

    if errors:
        flash(errors[0], "error")
        return redirect(
            url_for("main.semester_detail", semester_id=semester_id)
        )

    with get_db() as connection:
        for subject_id, mark in values.items():
            connection.execute(
                "UPDATE subjects SET marks_obtained = ? WHERE id = ?",
                (mark, subject_id),
            )
    entered = sum(1 for value in values.values() if value is not None)
    flash(
        f"Marks saved. {entered} of {len(values)} subjects now have a mark.",
        "success",
    )
    return redirect(url_for("main.semester_detail", semester_id=semester_id))


# ---------------------------------------------------------------------------
# Transcript, analysis and reports
# ---------------------------------------------------------------------------


@bp.route("/results")
@profile_required
def results():
    transcript = transcript_snapshot()
    return render_template("results.html", transcript=transcript)


@bp.route("/analysis")
@profile_required
def analysis_page():
    transcript = transcript_snapshot()
    return render_template(
        "analysis.html",
        transcript=transcript,
        grade_rows=analytics.grade_rows(transcript),
        chart_version=int(time.time()),
    )


@bp.route("/reports")
@profile_required
def reports():
    transcript = transcript_snapshot()
    chart_items = [
        {"key": key, **meta} for key, meta in charts.CHART_META.items()
    ]
    return render_template(
        "reports.html",
        transcript=transcript,
        chart_items=chart_items,
        chart_version=int(time.time()),
    )


@bp.route("/charts/<chart_name>.png")
@profile_required
def chart_image(chart_name: str):
    renderer = charts.CHART_RENDERERS.get(chart_name)
    if renderer is None:
        abort(404)
    transcript = transcript_snapshot()
    image = renderer(transcript, g.profile)
    response = Response(image, mimetype="image/png")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


def _csv_response(text: str, filename: str) -> Response:
    response = Response("\ufeff" + text, mimetype="text/csv")
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )
    return response


@bp.route("/exports/<export_type>.csv")
@profile_required
def export_csv(export_type: str):
    transcript = transcript_snapshot()
    student = safe_download_part(g.profile["name"])

    if export_type == "transcript":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Semester",
                "Academic year",
                "Subject code",
                "Subject",
                "Credits",
                "Maximum marks",
                "Marks obtained",
                "Percentage",
                "Grade",
                "Grade points",
                "Status",
            ]
        )
        for semester in transcript["semesters"]:
            for subject in semester["subjects"]:
                writer.writerow(
                    [
                        semester["number"],
                        semester["academic_year"],
                        subject["code"],
                        subject["name"],
                        f"{subject['credits']:g}",
                        f"{subject['max_marks']:g}",
                        (
                            f"{subject['marks_obtained']:g}"
                            if subject["marks_obtained"] is not None
                            else ""
                        ),
                        (
                            f"{subject['percentage']:.2f}"
                            if subject["percentage"] is not None
                            else ""
                        ),
                        subject["grade_letter"] or "",
                        (
                            subject["grade_points"]
                            if subject["grade_points"] is not None
                            else ""
                        ),
                        STATUS_LABELS.get(subject["status"], ""),
                    ]
                )
        return _csv_response(
            output.getvalue(), f"{student}_transcript.csv"
        )

    if export_type == "semesters":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Semester",
                "Academic year",
                "Subjects",
                "Graded subjects",
                "Credits",
                "SGPA",
                "Percentage",
                "Status",
            ]
        )
        for semester in transcript["semesters"]:
            writer.writerow(
                [
                    semester["number"],
                    semester["academic_year"],
                    semester["subject_count"],
                    semester["graded_subject_count"],
                    f"{semester['credits_total']:g}",
                    f"{semester['sgpa']:.2f}"
                    if semester["sgpa"] is not None
                    else "",
                    f"{semester['percentage']:.2f}"
                    if semester["percentage"] is not None
                    else "",
                    STATUS_LABELS.get(semester["status"], ""),
                ]
            )
        return _csv_response(
            output.getvalue(), f"{student}_semester_summary.csv"
        )

    abort(404)


# ---------------------------------------------------------------------------
# Settings and data controls
# ---------------------------------------------------------------------------


@bp.route("/settings")
@profile_required
def settings():
    transcript = transcript_snapshot()
    return render_template("settings.html", transcript=transcript)


@bp.route("/settings/profile", methods=["POST"])
@profile_required
def update_profile():
    try:
        name = clean_text(
            request.form.get("name"), "Your name", required=True, max_length=80
        )
        college = clean_text(
            request.form.get("college"),
            "College name",
            required=False,
            max_length=120,
        )
        degree = clean_text(
            request.form.get("degree"),
            "Degree",
            required=False,
            max_length=60,
        )
        branch = clean_text(
            request.form.get("branch"),
            "Branch",
            required=False,
            max_length=80,
        )
        with get_db() as connection:
            connection.execute(
                "UPDATE profile SET name = ?, college = ?, degree = ?, "
                "branch = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (name, college, degree, branch),
            )
        g.profile = database.get_profile(get_db())
        flash("Profile updated.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("main.settings"))


@bp.route("/settings/target", methods=["POST"])
@profile_required
def update_target():
    try:
        target = validate_target_cgpa(request.form.get("target_cgpa"))
        with get_db() as connection:
            connection.execute(
                "UPDATE profile SET target_cgpa = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (target,),
            )
        g.profile = database.get_profile(get_db())
        flash(f"Target CGPA updated to {target:.2f}.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("main.settings"))


@bp.route("/settings/reset", methods=["POST"])
@profile_required
def reset_data():
    confirmation = str(request.form.get("confirm_text", "")).strip().upper()
    if confirmation != "DELETE":
        flash(
            'Data was not deleted. Type DELETE exactly to confirm.',
            "error",
        )
        return redirect(url_for("main.settings"))

    with get_db() as connection:
        demo_data.reset_all(connection)
    session.pop("_csrf_token", None)
    flash("All transcript data was deleted. You can start again.", "success")
    return redirect(url_for("main.index"))


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=True)
