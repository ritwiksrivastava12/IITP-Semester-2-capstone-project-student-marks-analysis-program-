# CampusMarks — College SGPA & CGPA Tracker

CampusMarks is a **single-student college transcript application** built with
Flask, SQLite, Jinja2, Matplotlib, HTML, CSS and a small amount of JavaScript.
It replaces the earlier multi-student school project: there are no classes,
student directories, teacher tools, class rankings or workspace switching.

One student can record their own semesters, subjects, credits and marks, then
review calculated grades, SGPA, CGPA, personal trends, printable transcripts and
CSV exports. All data stays in a local SQLite file.

> **No login or access control.** This is a local, single-user project. Anyone
> who can open the application or read the SQLite file can see and edit the
> transcript. There are deliberately no accounts, passwords or permissions.

---

## Contents

- [What the application does](#what-the-application-does)
- [Quick start on Windows](#quick-start-on-windows)
- [First-time walkthrough](#first-time-walkthrough)
- [Grading and calculation rules](#grading-and-calculation-rules)
- [Demo transcript](#demo-transcript)
- [Database and persistence](#database-and-persistence)
- [Pages and routes](#pages-and-routes)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Charts, CSV exports and printing](#charts-csv-exports-and-printing)
- [Running the tests](#running-the-tests)
- [Verification performed](#verification-performed)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)

---

## What the application does

### Personal academic record

- Create one student profile with name, college, degree, branch and target CGPA.
- Add up to 12 numbered college semesters, each with an optional academic year.
- Add any number of subjects to each semester. Every subject has:
  - a name and optional subject code;
  - credits between 0.5 and 20;
  - maximum marks between 1 and 1000;
  - an optional mark out of that maximum.
- Edit or delete semesters and subjects with confirmation for destructive actions.
- Enter or update all subject marks from one inline marks table.
- Leave a mark blank while a result is pending. **Blank is never converted to
  zero.**

### Results and analysis

- Grade letters and grade points use a fixed 10-point scale.
- Credit-weighted **SGPA** for each semester.
- Credit-weighted **CGPA** across fully entered semesters only.
- Separate provisional SGPA for a semester that still has pending marks.
- Overall percentage for completed semesters.
- Backlog detection when an entered mark is below 40%.
- Counts and percentages of graded, pending and failed subjects.
- Personal best/weakest subject, best semester and subject ranking.
- Target CGPA progress and the gap to the target.
- Five on-demand Matplotlib charts.
- Printable academic transcript and chart/report pages.
- Two UTF-8 CSV exports.

### Removed from the earlier version

The following features are intentionally gone:

- workspaces and workspace switching;
- classes, sections and class subjects;
- a student directory or multiple student records;
- class averages, pass rates and class rankings;
- multi-student marks entry;
- teacher/administrative settings.

The only "ranking" left is a personal ordering of the student's own subjects
inside **My analysis**. It is not a comparison with other students.

---

## Quick start on Windows

### Prerequisites

- Windows 10 or 11.
- Python 3.11 or newer. This project was verified with **Python 3.14.4**.
- PowerShell.
- Internet access for the first dependency installation.

### 1. Open the project folder

```powershell
cd "D:\student marks analysis program"
```

Adjust the path if the project is stored elsewhere.

### 2. Create a virtual environment

```powershell
py -3 -m venv .venv
```

If `py` is unavailable, use:

```powershell
python -m venv .venv
```

### 3. Install dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` pins:

```text
Flask==3.1.3
matplotlib==3.11.2
```

### 4. Start the application

```powershell
.\.venv\Scripts\python.exe app.py
```

The Flask development server listens on:

```text
http://127.0.0.1:5000
```

Open that address in a browser. Press **Ctrl+C** in PowerShell to stop it.
The database remains on disk between runs.

Development mode is enabled by the `app.py` entry point. The Flask debug
reloader is convenient locally but must not be treated as a production server.

### Optional: use an activated environment

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Optional: load the demo from PowerShell

Load the demo **only when the database has no profile**. First stop the server,
then run:

```powershell
.\.venv\Scripts\python.exe seed_demo.py
.\.venv\Scripts\python.exe app.py
```

The seed is idempotent: if a profile already exists, it prints a message and
changes nothing.

The welcome page also has an **Explore the college demo** button. It is shown
only while no profile exists.

---

## First-time walkthrough

1. Start the app and open `http://127.0.0.1:5000/`.
2. Choose one:
   - **Set up my profile** to enter your own details; or
   - **Explore the college demo** to load the fictional four-semester transcript.
3. Open **Semesters** and select **Add semester**.
4. Enter the semester number and academic year.
5. Select **Add subject** and enter its code, credits and maximum marks.
6. Enter marks in the **Subjects & marks** table. Use **Save marks**.
7. Repeat for other semesters.
8. Review:
   - **Dashboard** for CGPA, latest SGPA, credits and target progress;
   - **Transcript** for the printable semester-by-semester record;
   - **My analysis** for personal comparisons and grade bands;
   - **Charts & reports** for the five charts and CSV downloads.
9. Open **Settings** to update the profile or target, or to reset all data.

A semester's SGPA appears as soon as at least one mark is entered. It remains
**provisional** until every subject in that semester has a mark.

---

## Grading and calculation rules

### Fixed 10-point grade scale

| Percentage | Grade | Grade points | Description |
|---:|:---:|---:|---|
| 90% and above | O | 10 | Outstanding |
| 80% to below 90% | A+ | 9 | Excellent |
| 70% to below 80% | A | 8 | Very good |
| 60% to below 70% | B+ | 7 | Good |
| 50% to below 60% | B | 6 | Above average |
| 40% to below 50% | C | 5 | Average |
| Below 40% | F | 0 | Fail |

- A subject passes at **40% or more**.
- The percentage for one subject is:

```text
subject percentage = marks obtained / maximum marks × 100
```

- A failed subject is included with **0 grade points**, not omitted from SGPA or
  CGPA.
- Grade bands are fixed in code and are not configurable in the interface.

### SGPA

SGPA is the credit-weighted average of the **graded subjects** in one semester:

```text
SGPA = Σ(subject credits × grade points) / Σ(subject credits)
```

Only subjects with an entered mark are included. If a semester has pending
marks, the displayed SGPA is **provisional** and uses the graded subjects only.
Pending subjects are never treated as zero.

### CGPA

Official CGPA uses **complete semesters only**:

```text
CGPA = Σ(credits × grade points for every subject in complete semesters)
       ────────────────────────────────────────────────────────────────
              Σ(all subject credits in complete semesters)
```

A semester is complete only when **every listed subject has an entered mark**.
A saved zero counts as an entered mark. A semester with any blank mark is
excluded from official CGPA, even though its provisional SGPA is displayed.

If no semester is complete, CGPA is shown as `—`.

### Credits and percentage

- **Credits earned** counts passed subjects, whether their semester is complete
  or still in progress.
- **Credits pending** counts subjects with no mark.
- **Backlog credits** counts failed subjects.
- **Overall percentage** uses marks and maximum marks from complete semesters
  only.
- **Graded average** in My analysis uses every entered mark, including subjects
  in an in-progress semester.

### Semester statuses

| Status | Meaning |
|---|---|
| Not started | The semester has no subjects. |
| In progress | At least one subject has no mark. |
| Cleared | Every subject has a mark and all are at least 40%. |
| Backlog | Every subject has a mark, but at least one is below 40%. |

### Target CGPA

The target is stored with the profile and can be changed in Settings. It must be
between 0 and 10. The dashboard compares the official CGPA with the target and
shows the remaining gap when the target has not been met.

---

## Demo transcript

The fictional student is **Aarav Mehta**, a B.Tech Computer Science &
Engineering student at the fictional **National Institute of Technology**. The
demo contains:

| Semester | Academic year | Subjects | Credits | Entered marks | SGPA | Status |
|---|---|---:|---:|---:|---:|---|
| Semester 1 | 2024-25 | 5 | 16.0 | 5 | 8.88 | Cleared |
| Semester 2 | 2024-25 | 5 | 16.0 | 5 | 9.31 | Cleared |
| Semester 3 | 2025-26 | 5 | 19.0 | 5 | 8.84 | Cleared |
| Semester 4 | 2025-26 | 5 | 16.0 | 3 | 9.30 provisional | In progress |

Semester 4 has two pending subjects: **Theory of Computation** and
**Mini Project**. They are excluded from the provisional SGPA and keep Semester
4 out of the official CGPA.

Verified demo totals:

- 4 semesters, 20 subjects, 18 entered marks and 2 pending marks.
- Official CGPA: **9.00**, using the three complete semesters (51 completed
  credits).
- Credits earned across all graded subjects: **61.0 / 67.0**.
- Overall percentage in completed semesters: **84.3%** (1,264 / 1,500).
- Target CGPA: **8.50**, so the demo shows the target as met.

---

## Database and persistence

The default database is:

```text
instance/college_marks.db
```

It is created automatically on first startup. Existing tables and rows are
never reset during normal startup.

> The old school-version file `instance/marks_analysis.db` is not used by this
> application. It is not migrated or read automatically.

### Schema

| Table | Purpose | Important rules |
|---|---|---|
| `profile` | The one student profile | Singleton row with `id = 1`; target 0–10 |
| `semesters` | College semesters | Number 1–12, unique; optional academic year |
| `subjects` | Subjects and marks | Belongs to one semester; unique name per semester; credits 0.5–20; maximum 1–1000; mark blank or 0–maximum |

- Foreign keys are enabled on every connection.
- Deleting a semester cascades to its subjects.
- Subject names are unique case-insensitively inside a semester, but the same
  subject name may be reused in another semester.
- SQL values are passed as bound parameters.
- The database connection is opened per request and closed automatically.

### Backup

1. Stop the Flask server.
2. Copy `instance\college_marks.db` to a safe location.
3. To restore, stop the server and replace the file with the backup.

### Reset

Open **Settings → Reset all data**, type `DELETE`, and confirm. This permanently
removes the profile, every semester and every subject. It also clears the CSRF
token for the session. The welcome page then appears again.

To start with a completely new SQLite file, stop the server and remove
`instance\college_marks.db`. The schema is recreated on the next start.

---

## Pages and routes

| Route | Purpose |
|---|---|
| `GET /` | Welcome page, or redirect to dashboard when a profile exists |
| `GET/POST /setup` | Create the one student profile |
| `POST /demo/load` | Load the college demo when no profile exists |
| `GET /dashboard` | CGPA, latest SGPA, credits, pending marks, trend and recent semesters |
| `GET /semesters` | Semester directory |
| `GET/POST /semesters/new` | Add a semester |
| `GET/POST /semesters/<id>/edit` | Edit a semester |
| `POST /semesters/<id>/delete` | Delete a semester and its subjects |
| `GET /semesters/<id>` | Subject table, inline marks form and semester summary |
| `GET/POST /semesters/<id>/subjects/new` | Add a subject |
| `GET/POST /subjects/<id>/edit` | Edit a subject |
| `POST /subjects/<id>/delete` | Delete a subject |
| `POST /semesters/<id>/marks` | Save or clear all marks for a semester |
| `GET /results` | Printable academic transcript |
| `GET /analysis` | Personal subject and semester analysis |
| `GET /reports` | Five charts and CSV downloads |
| `GET /charts/<name>.png` | Render one chart as PNG |
| `GET /exports/transcript.csv` | Subject-level CSV |
| `GET /exports/semesters.csv` | Semester summary CSV |
| `GET/POST /settings` | Profile, target and reset controls |
| `POST /settings/profile` | Update profile |
| `POST /settings/target` | Update target CGPA |
| `POST /settings/reset` | Delete all personal data |

Old school routes such as `/workspaces`, `/classes`, `/students`, `/subjects`
and `/marks` return 404. There are no `/login` or `/register` routes.

### Security behaviour

- POST forms include a session CSRF token; missing or incorrect tokens return 400.
- CSRF comparisons use constant-time comparison.
- Cookies are HTTP-only and `SameSite=Lax`; CSRF tokens are not marked secure
  because the app runs over local HTTP.
- Responses include `X-Content-Type-Options`, `X-Frame-Options` and
  `Referrer-Policy` headers.
- HTML and CSV responses use `Cache-Control: no-store`.
- Request bodies are capped at 2 MB.
- There is still **no authentication**. Local file access is equivalent to full
  transcript access.

---

## Architecture

```text
Browser
   │  HTML forms, links and chart images
   ▼
app.py
   │  Flask app factory and blueprint: routes, validation orchestration,
   │  session CSRF, CSV responses, chart responses and error pages
   ├── database.py
   │      Schema, connections, common transcript queries
   ├── calculations.py
   │      Pure grading, SGPA/CGPA, validation and status rules
   ├── analysis.py
   │      Loads a transcript from SQLite and adds analysis rows
   ├── demo_data.py
   │      Fictional profile/transcript definition and reset helper
   └── charts.py
          Five Matplotlib renderers returning PNG bytes
   │
   ▼
Jinja2 templates + static CSS/JavaScript
   │
   ▼
SQLite: instance/college_marks.db
```

### Design choices

- **Application factory:** `create_app()` allows tests to use temporary
  databases and configuration.
- **Singleton profile:** the schema enforces one student with `id = 1`.
- **Calculations are pure:** `calculations.py` imports neither Flask nor SQLite,
  so the same rules drive pages, CSVs, charts and tests.
- **Derived results are never stored:** grades, SGPA and CGPA are recalculated
  from marks and subject credits on every request.
- **Pending is distinct from zero:** SQLite stores blank marks as `NULL`; a saved
  zero is a real, passed-or-failed mark.
- **One source of truth:** transcript pages, exports and charts receive the same
  calculated transcript snapshot.
- **In-memory charts:** Matplotlib uses the `Agg` backend. Figures are closed
  after rendering and images use `Cache-Control: no-store`.
- **Parameterized SQL:** no user value is joined into an SQL string.
- **CSRF protection:** every state-changing request must carry the session token.
- **Error pages:** custom 400, 404, 413 and 500 templates.

### File responsibilities

| Path | Responsibility |
|---|---|
| `app.py` | App factory, routes, form orchestration, CSRF, exports, chart responses, errors |
| `database.py` | SQLite schema, connections, transactions, transcript read helpers |
| `calculations.py` | Grade scale, subject/semester/transcript calculations, validation |
| `analysis.py` | Database-to-transcript loading and presentation helpers |
| `charts.py` | Five Matplotlib figures and empty states |
| `demo_data.py` | Fictional student, four-semester demo and reset helper |
| `seed_demo.py` | Idempotent command-line demo seeder |
| `templates/` | Jinja2 pages, transcript, forms, report and error pages |
| `static/css/style.css` | Layout, college components, dark mode, print and responsive styles |
| `static/js/main.js` | Theme, mobile navigation, flash dismissal, confirmations, printing, client hints |
| `static/favicon.svg` | Small CampusMarks browser icon |
| `tests/` | Unit and end-to-end tests using temporary databases |

---

## Project structure

```text
student marks analysis program/
├── app.py
├── analysis.py
├── calculations.py
├── charts.py
├── database.py
├── demo_data.py
├── seed_demo.py
├── requirements.txt
├── .gitignore
├── README.md
├── instance/
│   ├── college_marks.db       # new single-student database; runtime only
│   └── marks_analysis.db      # old version; not used by this app
├── static/
│   ├── css/style.css
│   ├── js/main.js
│   └── favicon.svg
├── templates/
│   ├── base.html
│   ├── welcome.html
│   ├── setup.html
│   ├── dashboard.html
│   ├── semesters.html
│   ├── semester_detail.html
│   ├── semester_form.html
│   ├── subject_form.html
│   ├── results.html
│   ├── analysis.html
│   ├── reports.html
│   ├── settings.html
│   └── errors/error.html
└── tests/
    ├── test_calculations.py
    ├── test_database.py
    ├── test_analysis.py
    ├── test_routes.py
    └── test_charts.py
```

The `instance/` directory and `.venv/` are excluded by `.gitignore` because they
contain local runtime data and dependencies.

---

## Charts, CSV exports and printing

All five charts are generated from the current transcript snapshot. They are not
saved to disk.

| Chart | What it shows |
|---|---|
| **A. SGPA & CGPA trend** | Semester SGPA bars, running cumulative CGPA line, provisional bars and target line |
| **B. Subject marks comparison** | Every entered subject as a percentage, with the 40% pass line |
| **C. Grade distribution** | Donut chart and counts for O, A+, A, B+, B, C and F |
| **D. Semester marks percentage** | Percentage per semester; in-progress semesters are marked as provisional |
| **E. Credit progress** | Earned, backlog and pending credits per semester |

Charts show explanatory empty states when the transcript has no relevant data.
An unknown chart name returns 404.

CSV exports:

- **Transcript CSV** — one row per subject with semester, academic year, subject
  code, subject, credits, maximum marks, marks, percentage, grade, grade points
  and status.
- **Semester summary CSV** — one row per semester with subject counts, graded
  subjects, credits, SGPA, percentage and status.

Both files are UTF-8 with a BOM so spreadsheet applications open them correctly.
Blank marks remain blank in the subject export.

The transcript and report pages include print controls and dedicated print
styles. A transcript is a personal record, not an official university document.

---

## Running the tests

From the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite uses temporary SQLite databases and does not modify the real
`instance/college_marks.db`.

It covers:

- grade boundaries, pending marks, zero as a real mark, credit-weighted SGPA;
- complete-only CGPA, running cumulative CGPA, target gaps and completed
  percentages;
- singleton profile constraints, foreign keys, cascades, unique semester numbers,
  subject constraints and transcript query ordering;
- demo loading and full reset;
- every page route, setup/onboarding, CSRF rejection, profile/target updates,
  semester and subject CRUD, marks validation and clearing, pending-only pages,
  charts, CSVs, persistence across a new app instance and reset confirmation;
- all five chart renderers with normal, empty, pending-only and missing-profile
  data.

**Verified result on 25 October 2026:**

```text
Ran 61 tests in 5.283s

OK
```

Run the command again after making changes; the exact elapsed time will vary.

---

## Verification performed

The following checks were actually run during the final verification pass:

- Full automated suite: **61 tests passed**.
- Seeded demo loaded successfully with **CGPA 9.00**, **4 semesters**,
  **20 subjects**, **18 entered marks** and **2 pending marks**.
- Started the real Flask server with `.\.venv\Scripts\python.exe app.py`.
- Rendered the seeded application at **1440 × 1000** and **390 × 844** using
  headless Chrome through Playwright:
  - dashboard, semesters, semester detail, transcript, analysis, reports and
    settings;
  - welcome and setup pages from a separate empty temporary database;
  - desktop layouts and the mobile stacked layout were visually inspected.
- Checked the document width of every page at both sizes: no page-level
  horizontal overflow. Wide data tables were converted into compact mobile
  layouts instead of clipping.
- Fixed responsive clipping found during the pass in the dashboard's
  recent-semester table, transcript columns, inline marks entry, grading
  reference, subject ranking and semester comparison. The desktop recent
  semesters card also now shows its **Open** links without side scrolling.
- Confirmed the five chart endpoints return valid PNG images and that every chart
  image loads with a non-zero natural size in the pages.
- Confirmed the transcript CSV and semester CSV download with attachment headers,
  correct content types, UTF-8 BOM and expected first rows.
- Exercised the theme toggle and mobile navigation in the browser: theme
  persisted to `localStorage` after reload, the sidebar opened/closed, and the
  overlay and `aria-expanded` state changed correctly. Light and dark dashboard
  screenshots were both inspected.
- Ran the live onboarding flow in an isolated temporary database: created a
  profile through the setup form, confirmed the empty dashboard, reset the data
  through the Settings form and its confirm dialog, loaded the demo from the
  welcome page, and saved a pending mark. The demo returned to **CGPA 9.00** and
  the mark-save flash confirmed the updated count.
- Browsed every application page in both viewport sizes and collected browser
  console and page errors; none were reported. The SVG favicon also returns 200.
- Automated route tests verified CSV downloads, chart responses, CSRF rejection,
  reset confirmation, persistence after restarting the app and pending-only
  transcript pages.

The demo screenshots were generated as temporary verification artifacts and are
not required by the application.

---

## Configuration

The app reads these environment variables before applying defaults:

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | Local development fallback | Flask session signing, including CSRF tokens |
| `MARKS_DATABASE` | `instance/college_marks.db` | SQLite database path |

The database directory is created automatically. For a different local database:

```powershell
$env:MARKS_DATABASE = "C:\Users\you\Documents\my_transcript.db"
.\.venv\Scripts\python.exe app.py
```

The development key is suitable only for this local, no-login project.

---

## Troubleshooting

### `python app.py` opens nothing

Confirm the virtual environment exists and dependencies are installed:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Check the terminal for `Running on http://127.0.0.1:5000`.

### Port 5000 is already in use

Stop the other Flask process, or terminate the old server with **Ctrl+C** in its
terminal. If a stale process remains, find and stop only that process before
starting again.

### PowerShell blocks `.venv\Scripts\Activate.ps1`

Either keep using the direct `.\.venv\Scripts\python.exe` commands, or allow
activation for the current terminal only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### The demo button is not visible

A profile already exists. Open **Settings**, reset all data, and then use the
welcome page demo button or run `seed_demo.py`.

### A semester shows a provisional SGPA but no official CGPA

At least one subject in every semester still has a blank mark, so no semester is
complete yet. Enter every mark for at least one semester. A real zero is a
valid mark; an empty field is not.

### Charts do not change

Charts are generated on demand and sent with `no-store`. Refresh the report page
after saving marks. The page adds a version query parameter to defeat old cached
images.

### I want to start over

Use **Settings → Reset all data** and type `DELETE`. To discard the whole SQLite
database instead, stop the server and delete `instance\college_marks.db`.

---

## Limitations

- **No authentication or encryption.** Do not expose this app to an untrusted
  network. The Flask development server is local-only and not production-ready.
- **One student per database.** Supporting another student requires a separate
  database file or a deliberate schema change.
- **Fixed grading scale.** The 10-point O/A+/A/B+/B/C/F scale and the 40% pass
  mark are not configurable, matching the intended college model.
- **No attendance, timetable or fee features.** The project is only a marks,
  SGPA and CGPA tracker.
- **Not an official transcript.** The printable page is a personal record and
  does not replace a document issued by a college or university.
- **No historical grade-scale versions.** If the grading rules changed between
  semesters, this app would still apply one current scale to every semester.
