"""Lightweight, deterministic MediFlow agent workflow for synthetic scheduling data.

These are software agents with explicit responsibilities and exchanged data, not LLMs.
All priority labels are administrative demo flags, never clinical triage.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd
import backend

REQUIRED_APPOINTMENT_COLUMNS = {
    "appointment_id", "patient_id", "department", "doctor_id", "date",
    "start_time", "duration_min", "status",
}
VALID_STATUSES = {"BOOKED", "SCHEDULED", "CONFIRMED", "CANCELLED", "PENDING"}

@dataclass
class WorkflowResult:
    passed: bool
    status: str
    plan: dict
    research: dict
    execution: dict
    critic: dict
    attempts: list[dict] = field(default_factory=list)
    final_schedule: pd.DataFrame | None = None

class ResearchAgent:
    """Inspects synthetic records and returns context for downstream agents."""
    def run(self, patients: pd.DataFrame, appointments: pd.DataFrame) -> dict:
        missing_p = {"patient_id", "priority_flag"} - set(patients.columns)
        missing_a = REQUIRED_APPOINTMENT_COLUMNS - set(appointments.columns)
        errors = []
        if missing_p: errors.append(f"Patients missing columns: {sorted(missing_p)}")
        if missing_a: errors.append(f"Appointments missing columns: {sorted(missing_a)}")
        if errors:
            return {"ok": False, "errors": errors, "conflicts": pd.DataFrame()}
        if patients.patient_id.duplicated().any(): errors.append("Duplicate patient_id values.")
        if appointments.appointment_id.duplicated().any(): errors.append("Duplicate appointment_id values.")
        if not set(appointments.patient_id).issubset(set(patients.patient_id)):
            errors.append("Appointment references an unknown patient_id.")
        if appointments.duration_min.isna().any() or (pd.to_numeric(appointments.duration_min, errors="coerce") <= 0).any():
            errors.append("Appointment durations must be positive numbers.")
        for value in appointments.start_time.astype(str):
            try: backend._minutes(value)
            except (ValueError, TypeError): errors.append(f"Invalid appointment time: {value}")
        bad_statuses = set(appointments.status.astype(str).str.upper()) - VALID_STATUSES
        if bad_statuses: errors.append(f"Unknown appointment statuses: {sorted(bad_statuses)}")
        try:
            priority = backend.prioritise_patients(patients)
        except (ValueError, KeyError) as exc:
            errors.append(str(exc)); priority = pd.DataFrame()
        try: conflicts = backend.detect_scheduling_conflicts(appointments)
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(f"Could not inspect schedule: {exc}"); conflicts = pd.DataFrame()
        return {"ok": not errors, "errors": errors, "conflicts": conflicts,
                "priority": priority, "patient_count": int(patients.patient_id.nunique()),
                "appointment_count": int(len(appointments))}

class PlannerAgent:
    """Plans a bounded validate/correct workflow from Research output."""
    def run(self, research: dict, max_attempts: int = 3) -> dict:
        if not research.get("ok"):
            return {"action": "STOP", "max_attempts": max_attempts,
                    "reason": "Research validation failed."}
        return {"action": "VALIDATE_AND_CORRECT" if not research["conflicts"].empty else "VALIDATE_ONLY",
                "max_attempts": max(1, min(int(max_attempts), 3)),
                "initial_conflicts": len(research["conflicts"])}

class ExecutorAgent:
    """Runs existing backend schedule proposal logic on a copy of the schedule."""
    def run(self, appointments: pd.DataFrame) -> dict:
        source = appointments.copy(deep=True)
        draft = backend.propose_schedule(source)
        candidate = source.copy(deep=True)
        candidate["start_time"] = draft["proposed_start_time"].values
        changes = draft.loc[draft["changed"], ["appointment_id", "start_time", "proposed_start_time"]].copy()
        return {"schedule": candidate, "changes": changes, "source_unchanged": appointments.equals(source)}

class CriticAgent:
    """Validates schedule integrity and conflicts before human review."""
    def run(self, patients: pd.DataFrame, original: pd.DataFrame, candidate: pd.DataFrame) -> dict:
        errors = []
        missing = REQUIRED_APPOINTMENT_COLUMNS - set(candidate.columns)
        if missing: errors.append(f"Candidate missing columns: {sorted(missing)}")
        if not errors:
            if candidate.appointment_id.duplicated().any(): errors.append("Duplicate appointment IDs.")
            if not set(candidate.patient_id).issubset(set(patients.patient_id)):
                errors.append("Candidate references an unknown patient.")
            if not set(candidate.appointment_id).issubset(set(original.appointment_id)):
                errors.append("Candidate introduces an appointment without an explicit request workflow.")
            original_ids = set(original.appointment_id)
            if set(candidate.appointment_id) != original_ids:
                errors.append("Candidate changed the set of appointment IDs.")
            original_by_id = original.set_index("appointment_id")
            candidate_by_id = candidate.set_index("appointment_id")
            for aid in original_ids & set(candidate.appointment_id):
                old, new = original_by_id.loc[aid], candidate_by_id.loc[aid]
                for col in REQUIRED_APPOINTMENT_COLUMNS - {"appointment_id", "start_time"}:
                    if str(old[col]) != str(new[col]):
                        errors.append(f"Immutable field {col} changed for {aid}.")
                        break
            try:
                conflicts = backend.detect_scheduling_conflicts(candidate)
            except (ValueError, KeyError, TypeError) as exc:
                conflicts = pd.DataFrame(); errors.append(f"Schedule could not be checked: {exc}")
            if not conflicts.empty: errors.append(f"{len(conflicts)} scheduling conflict(s) remain.")
        else:
            conflicts = pd.DataFrame()
        return {"passed": not errors, "errors": errors, "conflicts": conflicts,
                "human_approval_required": True}

def run_agent_workflow(patients: pd.DataFrame, appointments: pd.DataFrame, max_attempts: int = 3) -> WorkflowResult:
    """Run Research -> Planner -> Executor -> Critic with bounded correction attempts."""
    # Deep snapshots protect caller data from any agent mutation.
    original = appointments.copy(deep=True)
    patients_snapshot = patients.copy(deep=True)
    research_agent, planner_agent = ResearchAgent(), PlannerAgent()
    executor_agent, critic_agent = ExecutorAgent(), CriticAgent()
    research = research_agent.run(patients_snapshot, original)
    plan = planner_agent.run(research, max_attempts=max_attempts)
    if not research.get("ok"):
        critic = {"passed": False, "errors": list(research["errors"]),
                  "conflicts": research.get("conflicts", pd.DataFrame()), "human_approval_required": True}
        return WorkflowResult(False, "VALIDATION_FAILED", plan, research, {}, critic, [], None)
    attempts = []
    current = original.copy(deep=True)
    execution = {}
    critic = {}
    for attempt in range(1, plan["max_attempts"] + 1):
        execution = executor_agent.run(current)
        candidate = execution["schedule"]
        critic = critic_agent.run(patients_snapshot, original, candidate)
        attempts.append({"attempt": attempt, "changes": len(execution["changes"]),
                         "passed": critic["passed"], "errors": list(critic["errors"])})
        if critic["passed"]:
            return WorkflowResult(True, "PENDING_HUMAN_APPROVAL", plan, research,
                                  execution, critic, attempts, candidate)
        # Retry by applying another deterministic correction pass to the last candidate.
        current = candidate
        if not execution["changes"].empty and attempt < plan["max_attempts"]:
            continue
        break
    return WorkflowResult(False, "VALIDATION_FAILED", plan, research, execution,
                          critic, attempts, current)
