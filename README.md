# QM 7363 Capstone — Agentic Risk Analyst

Predicts adverse internal control opinions and produces an evidence-linked,
verifiable assessment with a replayable trace of every query the agent ran.

| | |
|---|---|
| Course | QM 7363-01 Advanced Machine Learning, University of Tulsa |
| Instructor | Ismail Abdulrashid, Ph.D. |
| Team | Mark (lead), Jessica, Said Shoaib, Enock, Mouzam Younas |
| Window | September 28 to December 7, 2026 |
| Plan | `docs/QM7363_ProjectPlan_v2.docx` |

---

## Setup

You need Python 3.11 or newer. Check with `python --version`.

**1. Clone the repository**

```
git clone <repo-url>
cd qm7363
```

**2. Create a virtual environment**

macOS / Linux:
```
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):
```
py -m venv .venv
.venv\Scripts\Activate.ps1
```

Your prompt should now start with `(.venv)`. If it does not, the environment is
not active and everything below will install to the wrong place.

**3. Install dependencies**

First person to set this up runs:
```
pip install -r requirements.in
pip freeze > requirements.txt
git add requirements.txt && git commit -m "Pin dependency versions"
```

Everyone after that runs:
```
pip install -r requirements.txt
```

`requirements.in` lists what we need. `requirements.txt` records the exact
versions that actually got installed. Always install from the `.txt` so all five
of us are running identical versions.

**4. Point the code at the data**

The data files are **not** in this repository. See the Data section below.

```
cp config.example.py config.py
```

Then edit `config.py` and set `DATA_DIR` to wherever you put the shared data
folder on your own machine. `config.py` is gitignored, so your path stays yours.

**5. Check that it works**

```
python -m pytest tests/ -v
```

All tests should pass. If `test_panel_loads` fails, your `DATA_DIR` is wrong.

---

## Data

Data lives in the shared OneDrive folder, **not** in git. The panel is a 47 MB
Excel file and repositories are for code, not datasets. Putting it in git makes
every clone slow and every change store a whole new copy.

Shared folder contents:

| File | What it is |
|---|---|
| `final_panel.xlsx` | Mouzam's firm-year panel. 83,726 rows, 12,275 firms, FY2011 to FY2022 |
| `build_panel.py` | Mouzam's script that rebuilds the panel from the raw Compustat extracts |
| `raw/` | The five raw Compustat and WRDS extracts |

Download the folder once, put it anywhere on your machine, and point `DATA_DIR`
at it.

### One rule about the label

`auopic` is the target. It has three codes that matter:

| Code | Rows | Meaning |
|---|---|---|
| 0 | 40,802 | **Never audited for internal controls.** Smaller filers are exempt under SOX 404(b). |
| 1 | 40,719 | Assessed and effective. This is the true negative. |
| 2 | 2,009 | Adverse opinion, a material weakness. This is the positive class. |

**Code 0 is not a clean firm. It is an unknown, and it is 48.8% of the panel.**

Use `load_panel()` from `src/data.py`. It applies the filter for you and returns
42,728 rows at a 4.70% adverse rate. Do not read the Excel file directly into a
model.

---

## Layout

```
qm7363/
  src/           importable code. everything reusable goes here
    data.py      panel loading, the auopic filter, feature lists
    model.py     risk model training and scoring        (Jessica)
    tools.py     the nine agent tools                   (Said Shoaib)
    agent.py     agent loop, prompts, verification      (Enock)
    app.py       Streamlit interface                    (Mouzam)
  tests/         pytest. one test file per src module
  notebooks/     exploration only. nothing final lives here
  docs/          plan, tool contract, decision log, meeting notes
  outputs/       generated results. gitignored
  data/          local data if you prefer it here. gitignored
  config.py      your local paths. gitignored
```

Notebooks are for figuring things out. Once something works, move it into `src/`
and write a test. Nothing in the final report should depend on a notebook.

---

## How we work

**Branches.** Never commit to `main`. Branch, push, open a pull request, and have
your role's assistant review it before merge.

```
git checkout -b jessica/label-filter
git add -A && git commit -m "Apply auopic filter, exclude code 0"
git push -u origin jessica/label-filter
```

**Review pairs** are the primary and assistant on each role:

| Role | Primary | Reviewer |
|---|---|---|
| Data and Model | Jessica | Enock |
| Tool Layer | Said Shoaib | Mouzam |
| Agent | Enock | Jessica |
| Application and Evaluation | Mouzam | Mark |
| Lead | Mark | Said Shoaib |

**Meetings.** Twice weekly. Class is one. The project meeting is Wednesday at
7:00 PM on Teams. Agenda is fixed and it is in `docs/MEETING_TEMPLATE.md`.

**Decisions** go in `docs/DECISION_LOG.md` during the meeting where they are made,
not afterward. That file is the raw material for the methods section of the report.

**Never commit:** API keys, `config.py`, the data files, anything in `outputs/`.
`.gitignore` covers all of these. If you think you committed a key, say so
immediately and rotate it.
