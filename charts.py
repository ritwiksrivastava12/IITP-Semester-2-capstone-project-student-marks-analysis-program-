"""Matplotlib charts for the personal college transcript.

Images are rendered in memory, never written to disk. Each renderer accepts the
already calculated transcript, so chart values and page values cannot drift.
"""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")  # Non-interactive backend, safe for a local Flask server.

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from calculations import (
    BACKLOG,
    IN_PROGRESS,
    PASS_PERCENTAGE,
)

ACCENT = "#2f6b5f"
ACCENT_LIGHT = "#74a99a"
BLUE = "#376c9e"
GOLD = "#c58b2a"
RED = "#b74b4b"
GREEN = "#247458"
ORANGE = "#a76227"
GRAY = "#8b9198"
TEXT = "#24343b"
MUTED = "#66747b"
PALETTE = [
    "#2f6b5f",
    "#376c9e",
    "#c58b2a",
    "#8e5c9e",
    "#b74b4b",
    "#4f8f8a",
    "#9b7b4f",
    "#667085",
]
GRADE_COLORS = {
    "O": "#2f6b5f",
    "A+": "#3e806e",
    "A": "#4f8f8a",
    "B+": "#376c9e",
    "B": "#6f91ae",
    "C": "#c58b2a",
    "F": "#b74b4b",
}
MAX_SUBJECT_BARS = 24


def _short(text: object, limit: int = 24) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _student_name(profile: dict | None) -> str:
    return str((profile or {}).get("name") or "Student").strip() or "Student"


def _subtitle(profile: dict | None, extra: str = "") -> str:
    name = _student_name(profile)
    return f"{name} · {extra}" if extra else name


def _render(fig) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(
        buffer,
        format="png",
        dpi=150,
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
    )
    plt.close(fig)
    return buffer.getvalue()


def _empty_chart(
    title: str,
    message: str,
    profile: dict | None,
    *,
    wide: bool = False,
) -> bytes:
    fig, ax = plt.subplots(figsize=(8.2, 5.0) if not wide else (12.0, 5.0))
    fig.patch.set_facecolor("#fffefa")
    ax.set_facecolor("#fffefa")
    ax.axis("off")
    ax.text(
        0.5,
        0.68,
        title,
        ha="center",
        va="center",
        fontsize=15,
        fontweight="bold",
        color=TEXT,
        transform=ax.transAxes,
        family="DejaVu Serif",
    )
    ax.text(
        0.5,
        0.48,
        message,
        ha="center",
        va="center",
        fontsize=10.5,
        color=MUTED,
        transform=ax.transAxes,
        wrap=True,
    )
    ax.text(
        0.5,
        0.23,
        _subtitle(profile, "College transcript"),
        ha="center",
        va="center",
        fontsize=8.5,
        color=GRAY,
        transform=ax.transAxes,
    )
    return _render(fig)


def _style_axis(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#d7d1c5")
    ax.spines["bottom"].set_color("#d7d1c5")
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color="#e8e3d8", linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    ax.title.set_color(TEXT)


def sgpa_trend_chart(transcript: dict, profile: dict | None = None) -> bytes:
    """Bar chart of SGPA with a cumulative CGPA line and target line."""
    semesters = [row for row in transcript["semesters"] if row["sgpa"] is not None]
    if not semesters:
        return _empty_chart(
            "SGPA & CGPA trend",
            "Add a subject and enter a mark to begin the semester trend.",
            profile,
        )

    fig, ax = plt.subplots(figsize=(8.6, 4.7))
    fig.patch.set_facecolor("#fffefa")
    fig.subplots_adjust(left=0.09, right=0.97, top=0.82, bottom=0.16)
    _style_axis(ax)

    positions = list(range(len(semesters)))
    labels = [f"S{row['number']}" for row in semesters]
    bar_colors = []
    bar_hatches = []
    for row in semesters:
        if row["status"] == BACKLOG:
            bar_colors.append(RED)
        elif row["status"] == IN_PROGRESS:
            bar_colors.append("#d9b36b")
        else:
            bar_colors.append(ACCENT)
        bar_hatches.append("//" if row["is_provisional"] else "")

    bars = ax.bar(
        positions,
        [float(row["sgpa"]) for row in semesters],
        color=bar_colors,
        width=0.56,
        edgecolor="#ffffff",
        linewidth=0.8,
        zorder=3,
    )
    for bar, hatch in zip(bars, bar_hatches):
        if hatch:
            bar.set_hatch(hatch)
            bar.set_edgecolor("#9a6b1f")
            bar.set_linewidth(0.8)

    for index, row in enumerate(semesters):
        ax.text(
            index,
            min(float(row["sgpa"]) + 0.22, 10.25),
            f"{row['sgpa']:.2f}",
            ha="center",
            va="bottom",
            fontsize=8,
            color=TEXT,
            fontweight="bold",
        )

    cumulative = [
        (index, float(row["cumulative_cgpa"]))
        for index, row in enumerate(semesters)
        if row["cumulative_cgpa"] is not None
    ]
    if cumulative:
        ax.plot(
            [point[0] for point in cumulative],
            [point[1] for point in cumulative],
            color=BLUE,
            linewidth=2.0,
            marker="o",
            markersize=4.5,
            zorder=4,
            label="Cumulative CGPA",
        )

    target = float(transcript.get("target_cgpa") or 0)
    if target > 0:
        ax.axhline(
            target,
            color=GOLD,
            linewidth=1.3,
            linestyle=(0, (4, 4)),
            zorder=2,
            label=f"Target CGPA {target:.2f}",
        )

    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 10.6)
    ax.set_yticks([0, 2, 4, 6, 8, 10])
    ax.set_ylabel("Grade points", color=MUTED, fontsize=9)
    ax.set_title(
        "SGPA and CGPA by semester",
        loc="left",
        fontsize=14,
        fontweight="bold",
        pad=10,
    )
    ax.text(
        0,
        1.035,
        _subtitle(
            profile,
            f"{len(semesters)} semester{'s' if len(semesters) != 1 else ''}"
            + (
                f" · CGPA {transcript['cgpa']:.2f}"
                if transcript.get("cgpa") is not None
                else ""
            ),
        ),
        transform=ax.transAxes,
        color=MUTED,
        fontsize=8.6,
    )
    handles = [
        Patch(facecolor=ACCENT, label="Semester SGPA"),
        Patch(
            facecolor="#d9b36b",
            edgecolor="#9a6b1f",
            hatch="//",
            label="Provisional SGPA",
        ),
    ]
    if cumulative:
        handles.append(
            Line2D([0], [0], color=BLUE, marker="o", linewidth=2, label="Cumulative CGPA")
        )
    if target > 0:
        handles.append(
            Line2D(
                [0],
                [0],
                color=GOLD,
                linewidth=1.3,
                linestyle=(0, (4, 4)),
                label=f"Target {target:.2f}",
            )
        )
    ax.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0, -0.13),
        ncol=min(4, len(handles)),
        frameon=False,
        fontsize=7.8,
        handlelength=1.8,
        columnspacing=1.4,
    )
    return _render(fig)


def subject_marks_chart(transcript: dict, profile: dict | None = None) -> bytes:
    """Horizontal comparison of every entered subject percentage."""
    subjects = list(transcript.get("graded_subjects") or [])
    if not subjects:
        return _empty_chart(
            "Subject marks comparison",
            "No subject marks have been entered yet.",
            profile,
        )

    total_subjects = len(subjects)
    selected = sorted(
        subjects,
        key=lambda subject: (
            -float(subject["percentage"]),
            int(subject["semester_number"]),
            str(subject["name"]).casefold(),
        ),
    )[:MAX_SUBJECT_BARS]
    selected.sort(
        key=lambda subject: (
            int(subject["semester_number"]),
            -float(subject["percentage"]),
            str(subject["name"]).casefold(),
        )
    )

    height = min(10.2, max(4.7, 0.34 * len(selected) + 1.7))
    fig, ax = plt.subplots(figsize=(8.8, height))
    fig.patch.set_facecolor("#fffefa")
    fig.subplots_adjust(
        left=0.34, right=0.94, top=1 - (0.9 / height), bottom=0.13
    )
    _style_axis(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color="#e8e3d8", linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)

    positions = list(range(len(selected)))
    values = [float(subject["percentage"]) for subject in selected]
    colors = [
        RED if subject["status"] != "PASS" else PALETTE[(int(subject["semester_number"]) - 1) % len(PALETTE)]
        for subject in selected
    ]
    ax.barh(
        positions,
        values,
        color=colors,
        height=0.62,
        edgecolor="#ffffff",
        linewidth=0.6,
        zorder=3,
    )
    labels = []
    for subject in selected:
        code = str(subject.get("code") or "").strip()
        name = _short(subject["name"], 23)
        prefix = f"S{subject['semester_number']} · "
        labels.append(prefix + (f"{code} — {name}" if code else name))
    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=7.7)
    ax.invert_yaxis()
    ax.set_xlim(0, 108)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.set_xlabel("Marks obtained (%)", color=MUTED, fontsize=9)
    ax.axvline(
        PASS_PERCENTAGE,
        color=GOLD,
        linewidth=1.2,
        linestyle=(0, (4, 4)),
        zorder=2,
    )
    ax.text(
        PASS_PERCENTAGE + 1.5,
        -0.9,
        f"Pass {PASS_PERCENTAGE:g}%",
        color=GOLD,
        fontsize=7.5,
        va="bottom",
    )
    for index, value in enumerate(values):
        ax.text(
            min(value + 1.5, 106),
            index,
            f"{value:.1f}",
            va="center",
            fontsize=7,
            color=TEXT,
        )
    note = (
        f"Showing {len(selected)} of {total_subjects} subjects"
        if total_subjects > len(selected)
        else f"{len(selected)} graded subjects"
    )
    ax.set_title(
        "Subject marks comparison",
        loc="left",
        fontsize=14,
        fontweight="bold",
        pad=10,
    )
    ax.text(
        0,
        1.005,
        _subtitle(profile, note),
        transform=ax.transAxes,
        color=MUTED,
        fontsize=8.6,
    )
    return _render(fig)


def grade_distribution_chart(transcript: dict, profile: dict | None = None) -> bytes:
    """Donut chart of grade letters across all graded subjects."""
    rows = [row for row in transcript.get("grade_distribution", []) if row["count"]]
    if not rows:
        return _empty_chart(
            "Grade distribution",
            "Grades appear once at least one subject mark is entered.",
            profile,
        )

    fig, ax = plt.subplots(figsize=(7.4, 4.7))
    fig.patch.set_facecolor("#fffefa")
    fig.subplots_adjust(left=0.02, right=0.62, top=0.84, bottom=0.1)
    colors = [GRADE_COLORS.get(row["letter"], GRAY) for row in rows]
    values = [row["count"] for row in rows]
    labels = [
        f"{row['letter']} ({row['count']})" for row in rows
    ]
    wedges, _texts, autotexts = ax.pie(
        values,
        colors=colors,
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.36, "edgecolor": "#fffefa", "linewidth": 2},
        autopct=lambda pct: f"{pct:.0f}%" if pct >= 5 else "",
        pctdistance=0.82,
        textprops={"color": "#ffffff", "fontsize": 8, "fontweight": "bold"},
        labels=None,
    )
    for text in autotexts:
        text.set_color("#ffffff")
    total = sum(values)
    ax.text(
        0,
        0.08,
        str(total),
        ha="center",
        va="center",
        fontsize=24,
        fontweight="bold",
        color=TEXT,
        family="DejaVu Serif",
    )
    ax.text(
        0,
        -0.14,
        "graded\nsubjects",
        ha="center",
        va="center",
        fontsize=8,
        color=MUTED,
        linespacing=1.2,
    )
    ax.legend(
        wedges,
        labels,
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        frameon=False,
        fontsize=8,
        title="Grade (subjects)",
        title_fontsize=8,
    )
    ax.set_title(
        "Grade distribution",
        loc="left",
        fontsize=14,
        fontweight="bold",
        pad=10,
    )
    ax.text(
        -0.05,
        1.02,
        _subtitle(profile, "Fixed 10-point scale"),
        transform=ax.transAxes,
        color=MUTED,
        fontsize=8.6,
    )
    return _render(fig)


def semester_performance_chart(
    transcript: dict, profile: dict | None = None
) -> bytes:
    """Semester percentage bars with the 40% pass line."""
    semesters = [
        row for row in transcript["semesters"] if row["percentage"] is not None
    ]
    if not semesters:
        return _empty_chart(
            "Semester marks percentage",
            "Enter subject marks to compare semester percentages.",
            profile,
        )

    fig, ax = plt.subplots(figsize=(8.2, 4.6))
    fig.patch.set_facecolor("#fffefa")
    fig.subplots_adjust(left=0.09, right=0.97, top=0.82, bottom=0.19)
    _style_axis(ax)

    positions = list(range(len(semesters)))
    values = [float(row["percentage"]) for row in semesters]
    colors = []
    for row in semesters:
        if row["status"] == BACKLOG:
            colors.append(RED)
        elif row["status"] == IN_PROGRESS:
            colors.append("#d9b36b")
        else:
            colors.append(ACCENT)
    bars = ax.bar(
        positions,
        values,
        color=colors,
        width=0.56,
        edgecolor="#ffffff",
        linewidth=0.8,
        zorder=3,
    )
    for bar, row in zip(bars, semesters):
        if row["is_provisional"]:
            bar.set_hatch("//")
            bar.set_edgecolor("#9a6b1f")
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            min(bar.get_height() + 1.8, 102),
            f"{bar.get_height():.1f}%",
            ha="center",
            va="bottom",
            fontsize=8,
            color=TEXT,
            fontweight="bold",
        )

    ax.axhline(
        PASS_PERCENTAGE,
        color=GOLD,
        linewidth=1.2,
        linestyle=(0, (4, 4)),
        zorder=2,
        label=f"Pass {PASS_PERCENTAGE:g}%",
    )
    ax.set_xticks(positions)
    ax.set_xticklabels([f"S{row['number']}" for row in semesters])
    ax.set_ylim(0, 108)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_ylabel("Percentage (%)", color=MUTED, fontsize=9)
    ax.set_title(
        "Semester marks percentage",
        loc="left",
        fontsize=14,
        fontweight="bold",
        pad=10,
    )
    ax.text(
        0,
        1.035,
        _subtitle(profile, "Provisional bars use entered subjects only"),
        transform=ax.transAxes,
        color=MUTED,
        fontsize=8.6,
    )
    handles = [
        Patch(facecolor=ACCENT, label="Complete semester"),
        Patch(
            facecolor="#d9b36b",
            edgecolor="#9a6b1f",
            hatch="//",
            label="In progress",
        ),
        Line2D(
            [0],
            [0],
            color=GOLD,
            linewidth=1.2,
            linestyle=(0, (4, 4)),
            label=f"Pass {PASS_PERCENTAGE:g}%",
        ),
    ]
    ax.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0, -0.16),
        ncol=3,
        frameon=False,
        fontsize=7.8,
    )
    return _render(fig)


def credit_progress_chart(transcript: dict, profile: dict | None = None) -> bytes:
    """Stacked bars showing earned, backlog and pending credits."""
    semesters = [row for row in transcript["semesters"] if row["subject_count"]]
    if not semesters:
        return _empty_chart(
            "Credit progress",
            "Add subjects to see how credits are earned across semesters.",
            profile,
        )

    fig, ax = plt.subplots(figsize=(8.2, 4.6))
    fig.patch.set_facecolor("#fffefa")
    fig.subplots_adjust(left=0.09, right=0.97, top=0.82, bottom=0.19)
    _style_axis(ax)

    positions = list(range(len(semesters)))
    earned = [float(row["credits_earned"]) for row in semesters]
    backlog = [float(row["credits_backlog"]) for row in semesters]
    pending = [float(row["credits_pending"]) for row in semesters]

    ax.bar(
        positions,
        earned,
        color=GREEN,
        width=0.58,
        edgecolor="#ffffff",
        linewidth=0.7,
        label="Credits earned",
        zorder=3,
    )
    ax.bar(
        positions,
        backlog,
        bottom=earned,
        color=RED,
        width=0.58,
        edgecolor="#ffffff",
        linewidth=0.7,
        label="Backlog credits",
        zorder=3,
    )
    bottom = [a + b for a, b in zip(earned, backlog)]
    ax.bar(
        positions,
        pending,
        bottom=bottom,
        color="#d9b36b",
        width=0.58,
        edgecolor="#ffffff",
        linewidth=0.7,
        hatch="//",
        label="Pending marks",
        zorder=3,
    )
    for index, row in enumerate(semesters):
        ax.text(
            index,
            float(row["credits_total"]) + 3,
            f"{row['credits_total']:g}",
            ha="center",
            va="bottom",
            fontsize=8,
            color=TEXT,
            fontweight="bold",
        )

    ax.set_xticks(positions)
    ax.set_xticklabels([f"S{row['number']}" for row in semesters])
    ax.set_ylabel("Credits", color=MUTED, fontsize=9)
    ax.set_ylim(0, max([row["credits_total"] for row in semesters] + [4]) * 1.28)
    ax.set_title(
        "Credit progress by semester",
        loc="left",
        fontsize=14,
        fontweight="bold",
        pad=10,
    )
    ax.text(
        0,
        1.035,
        _subtitle(
            profile,
            f"{transcript['credits_earned']:g} of {transcript['credits_total']:g} credits earned",
        ),
        transform=ax.transAxes,
        color=MUTED,
        fontsize=8.6,
    )
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(0, -0.16),
        ncol=3,
        frameon=False,
        fontsize=7.8,
    )
    return _render(fig)


CHART_META = {
    "sgpa_trend": {
        "title": "SGPA & CGPA trend",
        "description": "Semester SGPA bars and the cumulative CGPA line. The dashed line is your target.",
    },
    "subject_marks": {
        "title": "Subject marks comparison",
        "description": "Every entered subject ordered by semester, with the 40% pass line.",
    },
    "grade_distribution": {
        "title": "Grade distribution",
        "description": "How your graded subjects are spread across the fixed 10-point grade scale.",
    },
    "semester_performance": {
        "title": "Semester marks percentage",
        "description": "Marks percentage for each semester. Hatched bars are still in progress.",
    },
    "credit_progress": {
        "title": "Credit progress",
        "description": "Earned, backlog and pending credits for each semester.",
    },
}

CHART_RENDERERS = {
    "sgpa_trend": sgpa_trend_chart,
    "subject_marks": subject_marks_chart,
    "grade_distribution": grade_distribution_chart,
    "semester_performance": semester_performance_chart,
    "credit_progress": credit_progress_chart,
}
