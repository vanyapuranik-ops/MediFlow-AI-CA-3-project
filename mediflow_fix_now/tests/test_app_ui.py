"""Headless UI tests via streamlit.testing.v1.AppTest (not a real browser)."""
from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")

def fresh():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    return at

def btn(at, label):
    return next(b for b in at.button if b.label.startswith(label))

def test_startup_shows_conflict():
    at = fresh()
    assert any("1 conflict pair" in e.value for e in at.error)

def test_reschedule_then_approve_clears_conflict():
    at = fresh()
    btn(at, "Generate reschedule").click().run()
    assert not at.exception
    btn(at, "Approve").click().run()
    assert not at.exception
    assert at.session_state.proposals[0].status == "APPROVED"
    import backend
    assert backend.validate_schedule(at.session_state.working)[0]
    assert not backend.validate_schedule(at.session_state.original)[0]   # original untouched

def test_reject_leaves_schedule():
    at = fresh()
    btn(at, "Generate reschedule").click().run()
    btn(at, "Reject").click().run()
    assert at.session_state.proposals[0].status == "REJECTED"
    assert len(at.session_state.working) == 6

def test_invalid_time_shows_error():
    at = fresh()
    at.text_input[0].set_value("99:99")
    btn(at, "Check request").click().run()
    assert any("Invalid time" in e.value for e in at.error)

def test_new_request_submit_and_approve():
    at = fresh()

    # The source demo CSV intentionally starts with one conflict (A100/A104).
    # Resolve and approve that conflict first, so the persistence layer can
    # correctly enforce a globally conflict-free working schedule.
    btn(at, "Generate reschedule").click().run()
    assert not at.exception
    btn(at, "Approve").click().run()
    assert not at.exception
    assert at.session_state.proposals[0].status == "APPROVED"

    at.text_input[0].set_value("14:00")
    btn(at, "Check request").click().run()
    assert any("Slot is free" in s.value for s in at.success)
    btn(at, "Submit to approval").click().run()
    assert at.session_state.proposals[0].status == "PENDING"
    btn(at, "Approve").click().run()
    assert at.session_state.proposals[0].status == "APPROVED"
    assert "A106" in set(at.session_state.working.appointment_id)
    assert "A106" not in set(at.session_state.original.appointment_id)
