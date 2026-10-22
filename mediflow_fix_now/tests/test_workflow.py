import pandas as pd
import pytest
import backend, workflow as wf

def data():
    return backend.load_data()

def test_invalid_inputs():
    p, a = data()
    for args, frag in [(("P999","D01","2026-10-21","09:00",20),"Unknown patient"),
                       (("P001","D99","2026-10-21","09:00",20),"not in the synthetic"),
                       (("P001","D01","2026-13-40","09:00",20),"Invalid date"),
                       (("P001","D01","2026-10-24","09:00",20),"weekend"),
                       (("P001","D01","2026-10-21","99:00",20),"Invalid time"),
                       (("P001","D01","2026-10-21","16:50",30),"clinic hours"),
                       (("P001","D01","2026-10-21","09:00",0),"Duration")]:
        errs = wf.validate_request_input(p, a, *args)
        assert any(frag in e for e in errs), (args, errs)

def test_request_conflict_and_free_slot():
    p, a = data()
    bad = wf.check_new_request(p, a, "P002", "D02", "2026-10-20", "09:40", 20)
    assert not bad["ok"] and not bad["conflicts"].empty
    assert "09:40" not in bad["recommended_slots"]
    ok = wf.check_new_request(p, a, "P002", "D02", "2026-10-20", "14:00", 20)
    assert ok["ok"] and ok["row"]["appointment_id"] == "A106"

def test_recommended_slots_are_conflict_free():
    _, a = data()
    for s in wf.recommend_slots(a, "D01", "2026-10-20", 30, limit=20):
        row = dict(appointment_id="X", patient_id="P001", department="c", doctor_id="D01",
                   date="2026-10-20", start_time=s, duration_min=30, status="BOOKED")
        t = pd.concat([a, pd.DataFrame([row])])
        c = backend.detect_scheduling_conflicts(t)
        assert c[(c.appointment_id_1=="X")|(c.appointment_id_2=="X")].empty

def test_reschedule_approve_preserves_original():
    _, a = data()
    snap = a.copy()
    prop = wf.plan_reschedule(a, "PR001")
    assert prop.validation_passed and prop.attempts
    new, prop = wf.approve(prop, a.copy())
    assert prop.status == wf.APPROVED and backend.validate_schedule(new)[0]
    pd.testing.assert_frame_equal(a, snap)         # input untouched

def test_no_proposal_when_clean():
    _, a = data()
    clean = a.copy(); clean.loc[clean.appointment_id=="A104","start_time"] = "09:30"
    assert wf.plan_reschedule(clean, "PR1") is None

def test_approval_never_bypasses_validation():
    p, a = data()
    chk = wf.check_new_request(p, a, "P002", "D02", "2026-10-20", "14:00", 20)
    prop = wf.proposal_from_request(chk, "PR2")
    # schedule changes after proposal creation -> slot now taken
    taken = pd.concat([a, pd.DataFrame([dict(appointment_id="A200", patient_id="P003", department="x",
            doctor_id="D02", date="2026-10-20", start_time="14:00", duration_min=20, status="BOOKED")])],
            ignore_index=True)
    out, prop = wf.approve(prop, taken)
    assert prop.status == wf.VALIDATION_FAILED and len(out) == len(taken)

def test_stale_reschedule_and_double_approve():
    _, a = data()
    prop = wf.plan_reschedule(a, "PR3")
    changed = a.copy(); changed.loc[changed.appointment_id=="A104","start_time"] = "15:00"
    _, p2 = wf.approve(prop, changed)
    assert p2.status == wf.VALIDATION_FAILED and "stale" in p2.reasons[0]
    p4 = wf.plan_reschedule(a, "PR4"); wf.reject(p4)
    _, p4 = wf.approve(p4, a)
    assert p4.status == wf.REJECTED

def test_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(backend, "ROOT", tmp_path)
    p, a, err = wf.load_safely()
    assert p is None and "Missing data file" in err

def test_priority_join():
    p, a = data()
    j = wf.priority_for_appointments(p, a)
    assert j.priority_rank.is_monotonic_increasing


def test_persisted_schedule_survives_reload_and_keeps_original_unchanged(tmp_path, monkeypatch):
    _, original = data()
    source_snapshot = original.copy(deep=True)
    monkeypatch.setattr(backend, "ROOT", tmp_path)
    prop = wf.plan_reschedule(original, "PR-PERSIST")
    corrected, prop = wf.approve(prop, original.copy())
    assert prop.status == wf.APPROVED
    wf.save_working_schedule(corrected)
    restored, loaded, warning = wf.load_working_schedule(original)
    assert loaded and warning is None
    assert backend.validate_schedule(restored)[0]
    assert restored.loc[restored.appointment_id == "A104", "start_time"].iloc[0] == "09:30"
    pd.testing.assert_frame_equal(original, source_snapshot)


def test_persistence_refuses_conflicting_schedule(tmp_path, monkeypatch):
    _, original = data()
    monkeypatch.setattr(backend, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="Refusing to save an invalid schedule"):
        wf.save_working_schedule(original)
    assert not (tmp_path / "working_appointments.csv").exists()

def test_reset_removes_persisted_working_schedule(tmp_path, monkeypatch):
    _, original = data()
    monkeypatch.setattr(backend, "ROOT", tmp_path)
    clean = original.copy()
    clean.loc[clean.appointment_id == "A104", "start_time"] = "09:30"
    wf.save_working_schedule(clean)
    assert (tmp_path / "working_appointments.csv").exists()
    wf.reset_working_schedule()
    assert not (tmp_path / "working_appointments.csv").exists()
