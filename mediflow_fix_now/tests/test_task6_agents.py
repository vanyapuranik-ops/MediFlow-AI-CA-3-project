import hashlib
import pandas as pd
import pytest
import backend
from agents import ResearchAgent, PlannerAgent, ExecutorAgent, CriticAgent, run_agent_workflow


def data(): return backend.load_data()

def test_four_agents_exchange_real_outputs_and_produce_valid_draft():
    p, a = data()
    result = run_agent_workflow(p, a)
    assert result.research["ok"] is True
    assert result.plan["action"] == "VALIDATE_AND_CORRECT"
    assert "schedule" in result.execution and "changes" in result.execution
    assert result.critic["passed"] is True
    assert result.status == "PENDING_HUMAN_APPROVAL"
    assert result.critic["human_approval_required"] is True
    assert backend.validate_schedule(result.final_schedule)[0]
    assert len(result.attempts) <= 3

def test_original_inputs_unchanged():
    p, a = data(); p0, a0 = p.copy(deep=True), a.copy(deep=True)
    run_agent_workflow(p, a)
    pd.testing.assert_frame_equal(p, p0)
    pd.testing.assert_frame_equal(a, a0)

def test_critic_rejects_remaining_overlap():
    p, a = data()
    critic = CriticAgent().run(p, a, a.copy())
    assert critic["passed"] is False
    assert any("conflict" in e.lower() for e in critic["errors"])

def test_critic_rejects_unknown_patient():
    p, a = data(); candidate = a.copy(); candidate.loc[0, "patient_id"] = "UNKNOWN"
    result = CriticAgent().run(p, a, candidate)
    assert not result["passed"]
    assert any("unknown patient" in e.lower() for e in result["errors"])

def test_critic_rejects_changed_immutable_field():
    p, a = data(); candidate = a.copy(); candidate.loc[0, "doctor_id"] = "D99"
    result = CriticAgent().run(p, a, candidate)
    assert not result["passed"]
    assert any("immutable field doctor_id" in e.lower() for e in result["errors"])

def test_research_rejects_duplicate_ids():
    p, a = data(); bad = pd.concat([a, a.iloc[[0]]], ignore_index=True)
    result = ResearchAgent().run(p, bad)
    assert not result["ok"]
    assert any("duplicate appointment_id" in e.lower() for e in result["errors"])

def test_research_rejects_invalid_duration():
    p, a = data(); bad = a.copy(); bad.loc[0, "duration_min"] = -5
    result = ResearchAgent().run(p, bad)
    assert not result["ok"]
    assert any("durations" in e.lower() for e in result["errors"])

def test_research_rejects_unknown_priority():
    p, a = data(); p.loc[0, "priority_flag"] = "URGENT"
    result = ResearchAgent().run(p, a)
    assert not result["ok"]
    assert any("unknown priority" in e.lower() for e in result["errors"])

def test_planner_bounds_retry_count():
    p, a = data(); research = ResearchAgent().run(p, a)
    assert PlannerAgent().run(research, 100)["max_attempts"] == 3
    assert PlannerAgent().run(research, 0)["max_attempts"] == 1

def test_cancelled_appointments_do_not_create_conflicts():
    p, a = data(); a.loc[a.appointment_id == "A104", "status"] = "CANCELLED"
    result = run_agent_workflow(p, a)
    assert result.research["ok"]
    assert result.research["conflicts"].empty
    assert result.status == "PENDING_HUMAN_APPROVAL"

def test_clean_schedule_needs_no_correction():
    p, a = data(); a.loc[a.appointment_id == "A104", "start_time"] = "09:30"
    result = run_agent_workflow(p, a)
    assert result.passed
    assert result.plan["action"] == "VALIDATE_ONLY"
    assert len(result.attempts) == 1

def test_invalid_research_stops_before_execution():
    p, a = data(); a.loc[0, "patient_id"] = "NO_SUCH_PATIENT"
    result = run_agent_workflow(p, a)
    assert not result.passed
    assert result.status == "VALIDATION_FAILED"
    assert result.final_schedule is None
    assert result.execution == {}

def test_different_doctors_and_dates_are_not_conflicts():
    _, a = data()
    base = a.iloc[[0]].copy()
    other_doctor = base.copy(); other_doctor.loc[:, "appointment_id"] = "X1"; other_doctor.loc[:, "doctor_id"] = "D99"
    other_date = base.copy(); other_date.loc[:, "appointment_id"] = "X2"; other_date.loc[:, "date"] = "2026-10-21"
    combined = pd.concat([base, other_doctor, other_date], ignore_index=True)
    assert backend.detect_scheduling_conflicts(combined).empty

def test_adjacent_appointments_are_not_conflicts():
    _, a = data(); row = a.iloc[[0]].copy()
    row.loc[:, "appointment_id"] = "ADJ"; row.loc[:, "start_time"] = "09:30"
    row.loc[:, "duration_min"] = 20
    combined = pd.concat([a, row], ignore_index=True)
    conflicts = backend.detect_scheduling_conflicts(combined)
    assert not ((conflicts.appointment_id_1 == "ADJ") | (conflicts.appointment_id_2 == "ADJ")).any()

def test_critic_rejects_duplicate_candidate_ids():
    p, a = data(); candidate = pd.concat([a, a.iloc[[0]]], ignore_index=True)
    result = CriticAgent().run(p, a, candidate)
    assert not result["passed"]
    assert any("duplicate appointment" in e.lower() for e in result["errors"])

def test_retry_limit_stops_after_three_failed_critic_attempts(monkeypatch):
    import agents
    p, a = data()
    def always_fail(self, patients, original, candidate):
        return {"passed": False, "errors": ["forced test failure"],
                "conflicts": pd.DataFrame(), "human_approval_required": True}
    monkeypatch.setattr(agents.CriticAgent, "run", always_fail)
    result = run_agent_workflow(p, a, max_attempts=99)
    assert not result.passed
    assert result.status == "VALIDATION_FAILED"
    assert 1 <= len(result.attempts) <= 3
    assert all(not item["passed"] for item in result.attempts)
