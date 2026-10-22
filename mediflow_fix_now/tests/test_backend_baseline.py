"""Characterisation tests added in Task 5 (the supplied ZIP had no tests). They pin existing behaviour."""
import pandas as pd, pytest
import backend

def test_load_and_summary():
    p, a = backend.load_data()
    assert len(p) == 6 and len(a) == 6
    assert backend.summarise_workflow(p, a)["conflict_pairs"] == 1

def test_known_conflict_pair():
    _, a = backend.load_data()
    c = backend.detect_scheduling_conflicts(a)
    assert set(c.loc[0, ["appointment_id_1", "appointment_id_2"]]) == {"A100", "A104"}

def test_propose_resolves_and_validates():
    _, a = backend.load_data()
    d = backend.propose_schedule(a)
    fixed = a.copy(); fixed["start_time"] = d.proposed_start_time
    assert backend.validate_schedule(fixed)[0]

def test_priority_order_and_unknown_flag():
    p, _ = backend.load_data()
    assert backend.prioritise_patients(p).patient_id.iloc[0] == "P005"
    p.loc[0, "priority_flag"] = "URGENT"
    with pytest.raises(ValueError):
        backend.prioritise_patients(p)

def test_bad_time_rejected():
    with pytest.raises(ValueError):
        backend._minutes("25:99")
