"""Pure college transcript calculations and form validation.

The module has no Flask or SQLite imports. Pages, CSV exports, charts and tests
all use the same functions, so the same mark can never produce a different
grade in two places.

Grading model
-------------
* A subject is passed at 40% or more of its maximum marks.
* Grade letters and grade points follow a fixed 10-point scale.
* SGPA is the credit-weighted average of a semester's graded subjects.
* CGPA uses only semesters whose marks are fully entered. A semester with a
  missing mark is "in progress" and its SGPA is shown as provisional.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping

PASS = "PASS"
FAIL = "FAIL"
PENDING = "PENDING"

CLEARED = "CLEARED"
BACKLOG = "BACKLOG"
IN_PROGRESS = "IN_PROGRESS"
EMPTY = "EMPTY"

PASS_PERCENTAGE = 40.0
MIN_CREDITS = 0.5
MAX_CREDITS = 20.0
MAX_SUBJECT_MARKS = 1000.0

# (minimum percentage, letter, grade points, description)
GRADE_BANDS: tuple[tuple[float, str, int, str], ...] = (
    (90.0, "O", 10, "Outstanding"),
    (80.0, "A+", 9, "Excellent"),
    (70.0, "A", 8, "Very good"),
    (60.0, "B+", 7, "Good"),
    (50.0, "B", 6, "Above average"),
    (40.0, "C", 5, "Average"),
    (0.0, "F", 0, "Fail"),
)


# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------


def safe_percentage(obtained: float | None, maximum: float | None) -> float:
    """Return a percentage without ever dividing by zero."""
    try:
        maximum_value = float(maximum)
        obtained_value = float(obtained)
    except (TypeError, ValueError):
        return 0.0
    if maximum_value <= 0:
        return 0.0
    return (obtained_value / maximum_value) * 100.0


def grade_for(percentage: float) -> dict:
    """Map a percentage to the fixed 10-point college grade scale."""
    value = max(0.0, min(100.0, float(percentage)))
    for minimum, letter, points, label in GRADE_BANDS:
        if value >= minimum:
            return {
                "letter": letter,
                "points": points,
                "label": label,
                "minimum": minimum,
            }
    # The final band starts at zero, so this is only a defensive fallback.
    return {"letter": "F", "points": 0, "label": "Fail", "minimum": 0.0}


def _decimal_from(value: object, field_name: str) -> Decimal:
    if value is None:
        raise ValueError(f"{field_name} is required.")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_name} must be a valid number.") from None
    if not number.is_finite():
        raise ValueError(f"{field_name} must be a finite number.")
    return number


def parse_optional_mark(
    raw_value: object, maximum: float, subject_name: str
) -> float | None:
    """Validate an optional subject mark.

    Blank input means "not entered yet" and returns ``None``; it is never
    silently converted into a zero. Zero itself is a valid entered mark.
    """
    if raw_value is None or str(raw_value).strip() == "":
        return None
    number = _decimal_from(raw_value, f"{subject_name} mark")
    if maximum is None or float(maximum) <= 0:
        raise ValueError(
            f"{subject_name}: maximum marks is not configured correctly."
        )
    if number < 0:
        raise ValueError(f"{subject_name}: marks cannot be negative.")
    if number > Decimal(str(maximum)):
        raise ValueError(
            f"{subject_name}: marks cannot exceed the maximum of "
            f"{float(maximum):g}."
        )
    return float(number)


def validate_subject_configuration(
    credits: object, max_marks: object
) -> tuple[float, float]:
    """Validate a subject's credits and maximum marks."""
    credit_value = _decimal_from(credits, "Credits")
    maximum = _decimal_from(max_marks, "Maximum marks")
    if credit_value < Decimal(str(MIN_CREDITS)):
        raise ValueError(f"Credits must be at least {MIN_CREDITS:g}.")
    if credit_value > Decimal(str(MAX_CREDITS)):
        raise ValueError(f"Credits cannot exceed {MAX_CREDITS:g}.")
    if maximum <= 0:
        raise ValueError("Maximum marks must be greater than zero.")
    if maximum > Decimal(str(MAX_SUBJECT_MARKS)):
        raise ValueError(
            f"Maximum marks cannot exceed {MAX_SUBJECT_MARKS:g}."
        )
    return float(credit_value), float(maximum)


def validate_target_cgpa(raw_value: object) -> float:
    """Validate the student's personal target CGPA (0–10)."""
    number = _decimal_from(raw_value, "Target CGPA")
    if number < 0 or number > 10:
        raise ValueError("Target CGPA must be between 0 and 10.")
    return float(number)


# ---------------------------------------------------------------------------
# Subject and semester calculations
# ---------------------------------------------------------------------------


def _raw_mark(value: object) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def calculate_subject(subject: Mapping) -> dict:
    """Return a copy of one subject with grade, percentage and status added."""
    entry = dict(subject)
    credits = float(entry.get("credits") or 0)
    maximum = float(entry.get("max_marks") or 0)
    mark = _raw_mark(entry.get("marks_obtained"))
    entered = mark is not None

    entry["credits"] = credits
    entry["max_marks"] = maximum
    entry["marks_obtained"] = mark
    entry["is_pending"] = not entered
    entry["percentage"] = None
    entry["grade_letter"] = None
    entry["grade_points"] = None
    entry["grade_label"] = "Pending"
    entry["status"] = PENDING

    if entered:
        percentage = safe_percentage(mark, maximum)
        grade = grade_for(percentage)
        entry["percentage"] = percentage
        entry["grade_letter"] = grade["letter"]
        entry["grade_points"] = grade["points"]
        entry["grade_label"] = grade["label"]
        entry["status"] = PASS if percentage >= PASS_PERCENTAGE else FAIL

    return entry


def calculate_semester(semester: Mapping) -> dict:
    """Calculate SGPA, credits and status for one semester.

    ``semester`` must contain its subjects under the ``subjects`` key.
    Missing marks are excluded from the provisional SGPA instead of being
    treated as zero. A semester is complete only when every subject has a mark.
    """
    result = dict(semester)
    number = int(result.get("number") or 0)
    subjects = [
        calculate_subject(subject) for subject in result.get("subjects", [])
    ]
    for subject in subjects:
        subject["semester_id"] = result.get("id")
        subject["semester_number"] = number
        subject["semester_label"] = f"Semester {number}" if number else "Semester"

    graded = [subject for subject in subjects if not subject["is_pending"]]
    pending = [subject for subject in subjects if subject["is_pending"]]
    passed = [subject for subject in graded if subject["status"] == PASS]
    failed = [subject for subject in graded if subject["status"] == FAIL]

    credits_total = sum(subject["credits"] for subject in subjects)
    graded_credits = sum(subject["credits"] for subject in graded)
    earned_credits = sum(subject["credits"] for subject in passed)
    backlog_credits = sum(subject["credits"] for subject in failed)
    pending_credits = sum(subject["credits"] for subject in pending)
    weighted_points = sum(
        subject["credits"] * float(subject["grade_points"] or 0)
        for subject in graded
    )

    sgpa = weighted_points / graded_credits if graded_credits else None
    marks_total = sum(float(subject["marks_obtained"]) for subject in graded)
    max_marks_total = sum(subject["max_marks"] for subject in graded)
    percentage = (
        safe_percentage(marks_total, max_marks_total) if graded else None
    )

    completed = bool(subjects) and not pending
    if not subjects:
        status = EMPTY
    elif pending:
        status = IN_PROGRESS
    elif failed:
        status = BACKLOG
    else:
        status = CLEARED

    result.update(
        {
            "subjects": subjects,
            "label": result.get("label") or (
                f"Semester {number}" if number else "Semester"
            ),
            "subject_count": len(subjects),
            "graded_subject_count": len(graded),
            "pending_subject_count": len(pending),
            "pass_count": len(passed),
            "fail_count": len(failed),
            "completed": completed,
            "status": status,
            "credits_total": credits_total,
            "graded_credits": graded_credits,
            "credits_earned": earned_credits,
            "credits_backlog": backlog_credits,
            "credits_pending": pending_credits,
            "weighted_grade_points": weighted_points,
            "sgpa": sgpa,
            "percentage": percentage,
            "marks_total": marks_total,
            "graded_max_marks": max_marks_total,
            "is_provisional": bool(sgpa is not None and not completed),
            "pending_subjects": [subject["name"] for subject in pending],
            "failed_subjects": [subject["name"] for subject in failed],
        }
    )
    return result


# ---------------------------------------------------------------------------
# Whole-transcript calculations
# ---------------------------------------------------------------------------


def _semester_sort_key(semester: Mapping) -> tuple[int, int]:
    return (int(semester.get("number") or 0), int(semester.get("id") or 0))


def _subject_sort_key(subject: Mapping) -> tuple:
    return (
        int(subject.get("semester_number") or 0),
        str(subject.get("name") or "").casefold(),
        int(subject.get("id") or 0),
    )


def _pick_semester(semesters: list[dict], *, highest: bool) -> dict | None:
    if not semesters:
        return None
    scored = [semester for semester in semesters if semester["sgpa"] is not None]
    if not scored:
        return None
    if highest:
        return max(
            scored,
            key=lambda semester: (semester["sgpa"], semester["number"]),
        )
    return min(
        scored,
        key=lambda semester: (semester["sgpa"], semester["number"]),
    )


def calculate_transcript(
    semesters: Iterable[Mapping], target_cgpa: float = 8.0
) -> dict:
    """Build a complete personal transcript snapshot.

    CGPA is calculated from complete semesters only. The current, partially
    entered semester is still displayed with a provisional SGPA so a student can
    see how it is shaping up without inflating the official CGPA.
    """
    semester_rows = [
        calculate_semester(semester)
        for semester in semesters
    ]
    semester_rows.sort(key=_semester_sort_key)

    completed_semesters = [
        semester for semester in semester_rows if semester["completed"]
    ]
    all_subjects = [
        subject
        for semester in semester_rows
        for subject in semester["subjects"]
    ]
    completed_subjects = [
        subject
        for semester in completed_semesters
        for subject in semester["subjects"]
    ]
    graded_subjects = [
        subject for subject in all_subjects if not subject["is_pending"]
    ]
    pending_subjects = [
        subject for subject in all_subjects if subject["is_pending"]
    ]
    failed_subjects = [
        subject for subject in graded_subjects if subject["status"] == FAIL
    ]

    completed_credits = sum(
        subject["credits"] for subject in completed_subjects
    )
    completed_weighted_points = sum(
        subject["credits"] * float(subject["grade_points"] or 0)
        for subject in completed_subjects
    )
    cgpa = (
        completed_weighted_points / completed_credits
        if completed_credits
        else None
    )

    total_marks = sum(
        float(subject["marks_obtained"]) for subject in completed_subjects
    )
    max_total_marks = sum(
        subject["max_marks"] for subject in completed_subjects
    )
    completed_percentage = (
        safe_percentage(total_marks, max_total_marks)
        if completed_subjects
        else None
    )

    graded_marks = sum(
        float(subject["marks_obtained"]) for subject in graded_subjects
    )
    graded_max = sum(subject["max_marks"] for subject in graded_subjects)
    graded_percentage = (
        safe_percentage(graded_marks, graded_max) if graded_subjects else None
    )

    credits_total = sum(subject["credits"] for subject in all_subjects)
    credits_earned = sum(
        subject["credits"]
        for subject in graded_subjects
        if subject["status"] == PASS
    )
    credits_pending = sum(
        subject["credits"] for subject in pending_subjects
    )
    credits_backlog = sum(
        subject["credits"] for subject in failed_subjects
    )

    # Running cumulative CGPA after each semester. An in-progress semester keeps
    # the previous value and is visually marked as provisional by the interface.
    running_points = 0.0
    running_credits = 0.0
    for semester in semester_rows:
        if semester["completed"]:
            running_points += sum(
                subject["credits"] * float(subject["grade_points"] or 0)
                for subject in semester["subjects"]
            )
            running_credits += semester["credits_total"]
        semester["cumulative_cgpa"] = (
            running_points / running_credits if running_credits else None
        )

    distribution_counts = {
        letter: 0 for _minimum, letter, _points, _label in GRADE_BANDS
    }
    for subject in graded_subjects:
        if subject["grade_letter"] in distribution_counts:
            distribution_counts[subject["grade_letter"]] += 1
    grade_distribution = [
        {
            "letter": letter,
            "points": points,
            "label": label,
            "count": distribution_counts[letter],
        }
        for _minimum, letter, points, label in GRADE_BANDS
    ]

    ranked_subjects = sorted(
        graded_subjects,
        key=lambda subject: (
            -float(subject["percentage"]),
            subject["semester_number"],
            str(subject["name"]).casefold(),
        ),
    )
    ranked_semesters = [
        semester for semester in semester_rows if semester["sgpa"] is not None
    ]

    best_semester = _pick_semester(
        completed_semesters or ranked_semesters, highest=True
    )
    worst_semester = _pick_semester(
        completed_semesters or ranked_semesters, highest=False
    )
    best_subject = ranked_subjects[0] if ranked_subjects else None
    weakest_subject = ranked_subjects[-1] if ranked_subjects else None

    latest_semester = max(
        semester_rows, key=_semester_sort_key, default=None
    )
    in_progress = [
        semester for semester in semester_rows if not semester["completed"]
    ]
    active_semester = (
        max(in_progress, key=_semester_sort_key) if in_progress else latest_semester
    )

    target = float(target_cgpa)
    target_gap = target - cgpa if cgpa is not None else None
    next_number = (
        max((semester["number"] for semester in semester_rows), default=0) + 1
    )
    if next_number > 12:
        next_number = None

    return {
        "semesters": semester_rows,
        "semester_count": len(semester_rows),
        "completed_semesters": completed_semesters,
        "completed_semester_count": len(completed_semesters),
        "subjects": all_subjects,
        "subject_count": len(all_subjects),
        "graded_subjects": graded_subjects,
        "graded_subject_count": len(graded_subjects),
        "pending_subjects": pending_subjects,
        "pending_subject_count": len(pending_subjects),
        "failed_subjects": failed_subjects,
        "failed_subject_count": len(failed_subjects),
        "passed_subject_count": len(graded_subjects) - len(failed_subjects),
        "credits_total": credits_total,
        "credits_earned": credits_earned,
        "credits_pending": credits_pending,
        "credits_backlog": credits_backlog,
        "credits_completed": completed_credits,
        "cgpa": cgpa,
        "target_cgpa": target,
        "target_gap": target_gap,
        "target_met": bool(cgpa is not None and cgpa >= target),
        "completed_percentage": completed_percentage,
        "graded_percentage": graded_percentage,
        "total_completed_marks": total_marks,
        "max_completed_marks": max_total_marks,
        "best_semester": best_semester,
        "worst_semester": worst_semester,
        "best_subject": best_subject,
        "weakest_subject": weakest_subject,
        "grade_distribution": grade_distribution,
        "ranked_subjects": ranked_subjects,
        "latest_semester": latest_semester,
        "active_semester": active_semester,
        "next_semester_number": next_number,
        "has_data": bool(all_subjects),
        "has_completed": bool(completed_semesters),
        "has_pending": bool(pending_subjects),
        "has_backlog": bool(failed_subjects),
    }
