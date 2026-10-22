"""MediFlow AI Task 3: synthetic data and scheduling backend.
All data is fictional. Priority flags are administrative demo inputs, not clinical triage.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
PRIORITY_RANK = {"HIGH": 1, "MEDIUM": 2, "ROUTINE": 3}

def load_data():
    patients = pd.read_csv(ROOT / "patients.csv", dtype={"patient_id": str})
    appointments = pd.read_csv(ROOT / "appointments.csv", dtype={"patient_id": str})
    if patients["patient_id"].duplicated().any():
        raise ValueError("Duplicate patient_id in patients.csv")
    if appointments["appointment_id"].duplicated().any():
        raise ValueError("Duplicate appointment_id in appointments.csv")
    if not set(appointments.patient_id).issubset(set(patients.patient_id)):
        raise ValueError("An appointment references an unknown patient_id")
    if (pd.to_numeric(appointments.duration_min, errors="coerce") <= 0).any():
        raise ValueError("Appointment durations must be positive")
    return patients, appointments

def _minutes(hhmm):
    h, m = map(int, str(hhmm).split(":"))
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"Invalid time: {hhmm}")
    return h * 60 + m

def detect_scheduling_conflicts(appointments):
    """Find overlapping non-cancelled appointments for the same doctor and date."""
    rows = []
    active = appointments[appointments.status.astype(str).str.upper() != "CANCELLED"].copy()
    active["_start"] = active.start_time.map(_minutes)
    active["_end"] = active["_start"] + pd.to_numeric(active.duration_min)
    records = active.to_dict("records")
    for i, a in enumerate(records):
        for b in records[i + 1:]:
            if a["doctor_id"] != b["doctor_id"] or str(a["date"]) != str(b["date"]):
                continue
            if a["_start"] < b["_end"] and b["_start"] < a["_end"]:
                rows.append({
                    "date": str(a["date"]), "doctor_id": a["doctor_id"],
                    "appointment_id_1": a["appointment_id"],
                    "appointment_id_2": b["appointment_id"],
                    "time_1": a["start_time"], "time_2": b["start_time"],
                    "issue": "Overlapping appointments assigned to the same doctor"
                })
    return pd.DataFrame(rows, columns=["date","doctor_id","appointment_id_1",
        "appointment_id_2","time_1","time_2","issue"])

def prioritise_patients(patients):
    """Sort by predefined administrative flags, then age descending; not clinical advice."""
    result = patients.copy()
    result["priority_flag"] = result.priority_flag.astype(str).str.upper().str.strip()
    unknown = sorted(set(result.priority_flag) - set(PRIORITY_RANK))
    if unknown:
        raise ValueError(f"Unknown priority flags: {unknown}")
    result["priority_rank"] = result.priority_flag.map(PRIORITY_RANK)
    result["priority_explanation"] = result.priority_flag.map({
        "HIGH":"Predefined HIGH administrative flag; staff review required",
        "MEDIUM":"Predefined MEDIUM administrative flag; staff review required",
        "ROUTINE":"Predefined ROUTINE administrative flag; staff review required"
    })
    return result.sort_values(["priority_rank","age","patient_id"],
        ascending=[True,False,True]).reset_index(drop=True)

def propose_schedule(appointments):
    """Create a review-only draft, moving overlapping bookings to the next 15-min boundary."""
    draft = appointments.copy()
    proposed = {}
    active = draft[draft.status.astype(str).str.upper() != "CANCELLED"].copy()
    active["_start"] = active.start_time.map(_minutes)
    active["_duration"] = pd.to_numeric(active.duration_min).astype(int)
    active = active.sort_values(["date","doctor_id","_start","appointment_id"])
    placed = []
    for _, row in active.iterrows():
        start = int(row["_start"])
        duration = int(row["_duration"])
        for prior in placed:
            if prior["date"] != str(row["date"]) or prior["doctor_id"] != row["doctor_id"]:
                continue
            if start < prior["end"] and prior["start"] < start + duration:
                start = ((prior["end"] + 14) // 15) * 15
        proposed[row["appointment_id"]] = f"{start//60:02d}:{start%60:02d}"
        placed.append({"date":str(row["date"]),"doctor_id":row["doctor_id"],
                       "start":start,"end":start+duration})
    draft["proposed_start_time"] = draft.apply(
        lambda r: proposed.get(r["appointment_id"], r["start_time"]), axis=1)
    draft["changed"] = draft.proposed_start_time.astype(str) != draft.start_time.astype(str)
    return draft

def validate_schedule(appointments):
    """Critic-style validation. Returns (passed, conflicts)."""
    conflicts = detect_scheduling_conflicts(appointments)
    return conflicts.empty, conflicts

def summarise_workflow(patients, appointments):
    active = appointments[appointments.status.astype(str).str.upper() != "CANCELLED"]
    return {
        "patients": int(patients.patient_id.nunique()),
        "active_appointments": int(len(active)),
        "doctors": int(active.doctor_id.nunique()),
        "conflict_pairs": int(len(detect_scheduling_conflicts(appointments)))
    }
