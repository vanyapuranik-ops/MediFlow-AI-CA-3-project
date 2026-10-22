# MediFlow AI: Task 3 Backend

## Contents
- `patients.csv`: fictional patient records and predefined administrative priority flags.
- `appointments.csv`: fictional appointment records, including intentional overlaps to test conflict detection.
- `backend.py`: data loading, basic data validation, conflict detection, administrative prioritisation, draft rescheduling, and schedule validation.

## Setup
Install Python 3 and pandas:
`python -m pip install pandas`

## Quick test
Run this from this folder:
```python
from backend import load_data, detect_scheduling_conflicts, prioritise_patients, propose_schedule, validate_schedule
patients, appointments = load_data()
print(detect_scheduling_conflicts(appointments))
print(prioritise_patients(patients)[["patient_id", "priority_flag", "priority_rank"]])
draft = propose_schedule(appointments)
check = appointments.copy()
check["start_time"] = draft["proposed_start_time"]
passed, remaining = validate_schedule(check)
print(draft[["appointment_id", "start_time", "proposed_start_time", "changed"]])
print("Validation passed:", passed)
print("Remaining conflicts:", len(remaining))
```

## Safety and scope
All records are synthetic and fictional. Priority flags are predefined administrative demo labels, not clinical urgency predictions. Rescheduling output is only a draft recommendation; it does not modify a real system. Hospital staff must review and approve consequential changes.

---

# Task 5: Streamlit Dashboard

## Install and launch
```bash
python -m pip install -r requirements.txt     # pandas, streamlit, pytest
streamlit run app.py                          # opens http://localhost:8501
python -m pytest -q                           # run all tests
```

## Files added in Task 5
- `app.py`: Streamlit UI. `workflow.py`: thin service layer (request checks, slot recommendation, proposal/approval state). `backend.py` and both CSVs are **unchanged**.
- `tests/`: baseline backend tests, workflow tests, headless UI tests (`streamlit.testing.v1.AppTest`).

## Dashboard features (all wired to `backend.py` / `workflow.py`)
- **Overview**: metrics from `summarise_workflow`; stage table; working-schedule validation result.
- **New request**: patient/doctor/date/time/duration form, input validation, conflict check via `detect_scheduling_conflicts`, recommended free slots, submit to approval queue.
- **Data**: patients, working vs original appointments, CSV download of the working schedule.
- **Conflicts**: `detect_scheduling_conflicts` on original and working data.
- **Priority**: `prioritise_patients` (administrative flags, not clinical triage) joined to appointments.
- **Reschedule**: `propose_schedule` -> `validate_schedule`, with up to 3 retry/correction passes shown per proposal.
- **Approvals**: PENDING / APPROVED / REJECTED / VALIDATION FAILED. Approval **re-validates** against the current schedule and refuses stale or conflicting proposals.
- **Persistent simulated schedule**: a validated, human-approved schedule is saved to `working_appointments.csv`, then restored on the next app launch. The source `appointments.csv` remains unchanged. The Audit log tab includes a reset action that deletes the persisted simulated schedule and restores the original schedule.

## Limitations
- The supplied Task 3 ZIP had **no Planner/Research/Executor/Critic orchestration, no approval workflow and no tests**. The UI maps Planner -> `propose_schedule` and Critic -> `validate_schedule`; Research and Executor are shown as "Not available". The approval state machine, request checks and slot recommendation are new code in `workflow.py`, not part of the original backend.
- Clinic hours (08:00-17:00), weekday-only dates and 5-120 min durations are demo assumptions I added for new requests.
- Only the simulated working schedule is persisted to `working_appointments.csv` after a validated human approval. The original `appointments.csv` is never modified. Proposal and audit history are session-only and are not persisted. Use the reset control in Audit log to delete the saved working schedule and reload the original data.
- `propose_schedule` can only move appointments later; it does not change doctors or dates.
- Verified with automated headless tests and a server start check only; no real browser/visual testing was done.

## Task 6: validation and end-to-end workflow

`agents.py` adds a deterministic, tool-based four-stage workflow for the synthetic proof of concept:

- **ResearchAgent** checks required columns, duplicate identifiers, patient references, durations, times, statuses, administrative priority flags, and existing schedule conflicts.
- **PlannerAgent** chooses validation-only or bounded correction and caps attempts at three.
- **ExecutorAgent** invokes the existing backend schedule proposal function on a copy of the schedule.
- **CriticAgent** checks conflicts, patient references, appointment identity, and immutable fields before any recommendation is marked ready for human approval.

Run the workflow demo from this directory:

```bash
python -c "import backend; from agents import run_agent_workflow; p,a=backend.load_data(); r=run_agent_workflow(p,a); print('status:',r.status); print('attempts:',r.attempts); print('critic:',r.critic)"
```

Run the complete test suite:

```bash
python -m pytest -q
```

The agent workflow is deterministic and uses Python functions, not an LLM. A successful result is `PENDING_HUMAN_APPROVAL`; this module does not itself approve or persist any change. Original CSVs are not written. The Streamlit UI currently uses `workflow.py`; the `agents.py` workflow is separately tested and has not yet been wired into the UI. This is a remaining integration task, not a claim that the dashboard runs all four agents.


Test note: the UI test for a new appointment first resolves the intentionally seeded A100/A104 conflict. The persistence layer requires the complete working schedule to be conflict-free before saving an approval.


## Agentic Workflow UI

The Streamlit dashboard includes an **Agentic Workflow** tab that calls the real
`agents.run_agent_workflow()` orchestration function. The UI displays Research,
Planner, Executor and Critic outputs plus the bounded correction history. A
validated schedule change is added to the existing human approval queue; it is
not applied until approved. Approval revalidates against the current working
schedule and persists only to `working_appointments.csv`. The source
`appointments.csv` remains unchanged.

Run:
```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
python -m pytest -q
```
