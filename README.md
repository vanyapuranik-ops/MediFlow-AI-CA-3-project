# MediFlow AI — CA-3 Submission

**Intelligent Hospital Workflow Coordination System**  
A Python + Streamlit synthetic-data proof of concept for administrative appointment scheduling, conflict detection, recommendations, and human-reviewed changes.

## Project scope
- Uses fictional patient and appointment CSV records only.
- Detects overlapping appointments for the same doctor and date.
- Checks appointment requests and suggests available time slots.
- Prepares reschedule proposals and validates the proposed schedule.
- Uses a custom, deterministic Planner / Research / Executor / Critic workflow.
- Keeps approval with a human reviewer; approval re-validates before saving the simulated working schedule.

This is an administrative demonstration, not a clinical decision-support system. Priority labels are predefined demonstration inputs, not clinical triage. It does not connect to a real hospital system.

## Repository contents
- `app.py` — Streamlit dashboard
- `agents.py` — custom agent roles and orchestration
- `backend.py` — synthetic-data loading, conflict detection, prioritisation and schedule proposal logic
- `workflow.py` — request validation, proposal state machine, re-validation and safe persistence of the simulated schedule
- `patients.csv`, `appointments.csv` — fictional demo data
- `tests/` — backend, workflow, agent and UI tests
- `docs/` — report and supporting documentation
- `presentation/` — CA-3 presentation deck

## Run locally (macOS)
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```
Open the local URL printed by Streamlit.

## Run tests
```bash
python -m pytest -q tests/
```
The project owner reported a successful local run of **38 passed in 2.57 seconds** on 23 October 2026 after the approval UI fix. The current packaging environment does not include Streamlit, so this package build did not independently repeat that full UI test run.

## Suggested demonstration
1. Show the synthetic records and the initial scheduling conflict.
2. Check a valid and an invalid appointment request.
3. Generate a reschedule proposal.
4. Show the Critic validation status.
5. Approve or reject the proposal; show that approval is gated by validation.
6. Run the four-agent workflow and inspect its trace.
7. Explain the synthetic-data and human-approval boundaries.

## Data and safety notes
All data are synthetic. The application writes approved changes only to `working_appointments.csv`, a simulated working schedule. Do not place real patient information in this repository. Do not describe administrative priority flags as clinical urgency predictions.

## Authors
Vanya Puranik and Siya Thakur

## Status
Academic proof of concept. Local demonstration only; public deployment and real hospital integration are not claimed.
