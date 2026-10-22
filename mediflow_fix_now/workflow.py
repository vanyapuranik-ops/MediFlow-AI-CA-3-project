"""MediFlow AI Task 5: thin service layer between the Streamlit UI and backend.py.

NOT the agent orchestration. The supplied Task 3 ZIP contains no Planner/Research/
Executor/Critic classes, so this module only (a) calls the existing backend
functions, and (b) adds a small human-approval state machine and new-request
checks. Every validation decision is delegated to backend.detect_scheduling_conflicts /
backend.validate_schedule. Original CSV data is never modified or written.
All data is synthetic; approval only changes an in-memory simulated schedule.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from dataclasses import dataclass, field

import pandas as pd

import backend

PENDING, APPROVED, REJECTED, VALIDATION_FAILED = (
    "PENDING", "APPROVED", "REJECTED", "VALIDATION_FAILED")
# Assumption (not in the supplied backend): demo clinic hours used for slot suggestions only.
DAY_START_MIN, DAY_END_MIN, SLOT_STEP = 8 * 60, 17 * 60, 15
MAX_RETRIES = 3


def fmt_minutes(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def working_schedule_path() -> Path:
    """Path for the persisted simulated schedule; original appointments.csv is never changed."""
    return Path(backend.ROOT) / "working_appointments.csv"


def load_working_schedule(original: pd.DataFrame) -> tuple[pd.DataFrame, bool, str | None]:
    """Load a previously approved schedule if it exists and passes safety checks.

    Returns (schedule, loaded_from_disk, warning). Invalid persisted state is ignored.
    """
    path = working_schedule_path()
    if not path.exists():
        return original.copy(deep=True), False, None
    try:
        saved = pd.read_csv(path, dtype={"patient_id": str, "appointment_id": str})
        required = set(original.columns)
        if not required.issubset(saved.columns):
            raise ValueError("saved schedule is missing required columns")
        if saved["appointment_id"].isna().any() or saved["appointment_id"].duplicated().any():
            raise ValueError("saved schedule has missing or duplicate appointment IDs")
        if not set(saved["patient_id"]).issubset(set(original["patient_id"])):
            raise ValueError("saved schedule references unknown patients")
        passed, conflicts = backend.validate_schedule(saved)
        if not passed:
            raise ValueError(f"saved schedule contains {len(conflicts)} conflict(s)")
        # Existing appointment identity and non-time fields must not be changed.
        old = original.set_index("appointment_id")
        new = saved.set_index("appointment_id")
        for aid in set(old.index).intersection(new.index):
            for col in original.columns:
                if col not in ("appointment_id", "start_time") and str(old.loc[aid, col]) != str(new.loc[aid, col]):
                    raise ValueError(f"saved schedule changed protected field {col} for {aid}")
        return saved[original.columns.tolist()].copy(), True, None
    except Exception as exc:
        return original.copy(deep=True), False, f"Saved working schedule was ignored: {exc}. Original schedule loaded."


def save_working_schedule(schedule: pd.DataFrame) -> None:
    """Atomically persist a validated simulated schedule, never the source CSV."""
    passed, conflicts = backend.validate_schedule(schedule)
    if not passed:
        raise ValueError(f"Refusing to save an invalid schedule ({len(conflicts)} conflict(s)).")
    path = working_schedule_path()
    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        schedule.to_csv(temp, index=False)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def reset_working_schedule() -> None:
    """Delete persisted simulated state so the next launch starts from source CSVs."""
    path = working_schedule_path()
    if path.exists():
        path.unlink()


def load_safely():
    """Return (patients, appointments, error_message). Never raises."""
    try:
        p, a = backend.load_data()
        return p, a, None
    except FileNotFoundError as e:
        return None, None, f"Missing data file: {e.filename or e}. Expected patients.csv and appointments.csv next to backend.py."
    except (ValueError, KeyError, pd.errors.ParserError, pd.errors.EmptyDataError) as e:
        return None, None, f"Data validation failed: {e}"


def _active(df):
    return df[df.status.astype(str).str.upper() != "CANCELLED"]


# ---------- new appointment requests ----------
def validate_request_input(patients, appointments, patient_id, doctor_id,
                           date_str, start_time, duration_min):
    """Return list of human-readable input errors (empty list = OK)."""
    errs = []
    if patient_id not in set(patients.patient_id):
        errs.append(f"Unknown patient_id '{patient_id}'.")
    doctor_id = (doctor_id or "").strip().upper()
    if not doctor_id:
        errs.append("Doctor ID is required.")
    elif doctor_id not in set(appointments.doctor_id):
        errs.append(f"Doctor '{doctor_id}' is not in the synthetic schedule.")
    try:
        d = dt.date.fromisoformat(str(date_str))
        if d.weekday() >= 5:
            errs.append("Date is a weekend; demo clinic schedules weekdays only.")
    except ValueError:
        errs.append(f"Invalid date '{date_str}' (use YYYY-MM-DD).")
    start = None
    try:
        start = backend._minutes(start_time)
    except (ValueError, TypeError):
        errs.append(f"Invalid time '{start_time}' (use HH:MM, 24h).")
    try:
        dur = int(duration_min)
        if not 5 <= dur <= 120:
            errs.append("Duration must be between 5 and 120 minutes.")
        elif start is not None and not (DAY_START_MIN <= start and start + dur <= DAY_END_MIN):
            errs.append(f"Appointment must fall within clinic hours {fmt_minutes(DAY_START_MIN)}-{fmt_minutes(DAY_END_MIN)}.")
    except (ValueError, TypeError):
        errs.append("Duration must be a whole number of minutes.")
    return errs


def next_appointment_id(appointments) -> str:
    nums = pd.to_numeric(appointments.appointment_id.astype(str).str.extract(r"(\d+)$")[0],
                         errors="coerce").dropna()
    return f"A{int(nums.max()) + 1 if len(nums) else 100}"


def check_new_request(patients, appointments, patient_id, doctor_id, date_str,
                      start_time, duration_min):
    """Validate a request against the current schedule using backend conflict detection.

    Returns dict: ok, errors, conflicts (DataFrame), row (dict|None), recommended_slots (list).
    """
    errs = validate_request_input(patients, appointments, patient_id, doctor_id,
                                  date_str, start_time, duration_min)
    out = {"ok": False, "errors": errs, "conflicts": pd.DataFrame(), "row": None,
           "recommended_slots": []}
    if errs:
        return out
    doctor_id = doctor_id.strip().upper()
    dept = patients.loc[patients.patient_id == patient_id, "department"].iloc[0]
    row = {"appointment_id": next_appointment_id(appointments), "patient_id": patient_id,
           "department": dept, "doctor_id": doctor_id, "date": str(date_str),
           "start_time": start_time, "duration_min": int(duration_min), "status": "BOOKED"}
    trial = pd.concat([appointments, pd.DataFrame([row])], ignore_index=True)
    allc = backend.detect_scheduling_conflicts(trial)
    mine = allc[(allc.appointment_id_1 == row["appointment_id"]) |
                (allc.appointment_id_2 == row["appointment_id"])]
    out.update(row=row, conflicts=mine.reset_index(drop=True), ok=mine.empty)
    out["recommended_slots"] = recommend_slots(appointments, doctor_id, str(date_str),
                                               int(duration_min))
    if not mine.empty:
        out["errors"] = [f"Requested slot {start_time} conflicts with {len(mine)} existing appointment(s)."]
    return out


def recommend_slots(appointments, doctor_id, date_str, duration_min, limit=5):
    """Free start times for doctor/date; each candidate is checked by the backend detector."""
    slots = []
    for start in range(DAY_START_MIN, DAY_END_MIN - duration_min + 1, SLOT_STEP):
        cand = {"appointment_id": "_CAND", "patient_id": "_", "department": "_",
                "doctor_id": doctor_id, "date": date_str, "start_time": fmt_minutes(start),
                "duration_min": duration_min, "status": "BOOKED"}
        trial = pd.concat([appointments, pd.DataFrame([cand])], ignore_index=True)
        c = backend.detect_scheduling_conflicts(trial)
        if c[(c.appointment_id_1 == "_CAND") | (c.appointment_id_2 == "_CAND")].empty:
            slots.append(fmt_minutes(start))
            if len(slots) >= limit:
                break
    return slots


# ---------- proposals + human approval ----------
@dataclass
class Proposal:
    proposal_id: str
    kind: str                      # "RESCHEDULE_DRAFT" | "NEW_APPOINTMENT"
    changes: pd.DataFrame          # columns: appointment_id, field, old, new
    summary: str
    validation_passed: bool
    validation_conflicts: pd.DataFrame
    attempts: list = field(default_factory=list)   # retry/correction log
    status: str = PENDING
    reasons: list = field(default_factory=list)
    new_row: dict | None = None
    created: str = field(default_factory=lambda: dt.datetime.now().strftime("%H:%M:%S"))


def apply_changes(appointments, proposal: Proposal) -> pd.DataFrame:
    """Return a COPY of the schedule with the proposal applied (input is never mutated)."""
    out = appointments.copy()
    if proposal.kind == "NEW_APPOINTMENT" and proposal.new_row:
        out = pd.concat([out, pd.DataFrame([proposal.new_row])], ignore_index=True)
    else:
        for _, ch in proposal.changes.iterrows():
            out.loc[out.appointment_id == ch["appointment_id"], "start_time"] = ch["new"]
    return out


def plan_reschedule(appointments, proposal_id: str):
    """Run backend.propose_schedule, validate, and retry on remaining conflicts.

    Each attempt re-runs propose_schedule on the previous attempt's result (a real
    correction pass). Returns a Proposal or None if no conflicts exist to fix.
    """
    if backend.validate_schedule(appointments)[0]:
        return None
    work, attempts = appointments.copy(), []
    for n in range(1, MAX_RETRIES + 1):
        draft = backend.propose_schedule(work)
        trial = work.copy()
        trial["start_time"] = draft["proposed_start_time"].values
        passed, remaining = backend.validate_schedule(trial)
        attempts.append({"attempt": n, "moves": int(draft.changed.sum()),
                         "remaining_conflicts": len(remaining), "passed": passed})
        work = trial
        if passed or draft.changed.sum() == 0:
            break
    orig = appointments.set_index("appointment_id").start_time
    rows = [{"appointment_id": i, "field": "start_time", "old": orig[i], "new": t}
            for i, t in work.set_index("appointment_id").start_time.items() if orig[i] != t]
    passed, remaining = backend.validate_schedule(work)
    return Proposal(proposal_id, "RESCHEDULE_DRAFT",
                    pd.DataFrame(rows, columns=["appointment_id", "field", "old", "new"]),
                    f"Move {len(rows)} appointment(s) to clear scheduling conflicts",
                    passed, remaining, attempts,
                    reasons=[] if passed else
                    [f"{len(remaining)} conflict(s) remain after {len(attempts)} attempt(s)."])


def proposal_from_request(check: dict, proposal_id: str) -> Proposal:
    r = check["row"]
    ch = pd.DataFrame([{"appointment_id": r["appointment_id"], "field": "new appointment",
                        "old": "-", "new": f'{r["doctor_id"]} {r["date"]} {r["start_time"]} ({r["duration_min"]} min)'}])
    return Proposal(proposal_id, "NEW_APPOINTMENT", ch,
                    f'New appointment for {r["patient_id"]} with {r["doctor_id"]}',
                    check["ok"], check["conflicts"], new_row=r,
                    reasons=[] if check["ok"] else check["errors"])


def approve(proposal: Proposal, working: pd.DataFrame):
    """Human approval. Re-validates against the CURRENT schedule; never bypasses the Critic.

    Returns (new_working_schedule, proposal). Only an in-memory copy changes.
    """
    if proposal.status != PENDING:
        proposal.reasons = [f"Proposal already {proposal.status}; no action taken."]
        return working, proposal
    try:
        if proposal.kind == "NEW_APPOINTMENT":
            if proposal.new_row["appointment_id"] in set(working.appointment_id):
                raise ValueError("Appointment ID already exists in the working schedule.")
        if proposal.kind == "RESCHEDULE_DRAFT":
            cur = working.set_index("appointment_id").start_time
            stale = [c.appointment_id for c in proposal.changes.itertuples()
                     if c.appointment_id not in cur.index or cur[c.appointment_id] != c.old]
            if stale:
                raise ValueError(f"Proposal is stale; schedule changed for {stale}. Regenerate it.")
        candidate = apply_changes(working, proposal)
        if proposal.kind == "NEW_APPOINTMENT":
            allc = backend.detect_scheduling_conflicts(candidate)
            nid = proposal.new_row["appointment_id"]
            bad = allc[(allc.appointment_id_1 == nid) | (allc.appointment_id_2 == nid)]
            passed = bad.empty
        else:
            passed, bad = backend.validate_schedule(candidate)
    except Exception as e:  # execution error -> surfaced, state unchanged
        proposal.status, proposal.reasons = VALIDATION_FAILED, [f"Execution error: {e}"]
        return working, proposal
    if not passed:
        proposal.status = VALIDATION_FAILED
        proposal.validation_conflicts = bad.reset_index(drop=True)
        proposal.reasons = [f"Re-validation at approval time found {len(bad)} conflict(s); not applied."]
        return working, proposal
    proposal.status, proposal.validation_passed, proposal.reasons = APPROVED, True, []
    return candidate, proposal


def reject(proposal: Proposal, note: str = ""):
    if proposal.status == PENDING:
        proposal.status = REJECTED
        proposal.reasons = [note or "Rejected by reviewer."]
    return proposal


def priority_for_appointments(patients, appointments):
    """Join backend.prioritise_patients onto active appointments (administrative flag only)."""
    pr = backend.prioritise_patients(patients)[
        ["patient_id", "patient_name", "priority_flag", "priority_rank", "priority_explanation"]]
    return _active(appointments).merge(pr, on="patient_id", how="left").sort_values(
        ["priority_rank", "date", "start_time"]).reset_index(drop=True)
