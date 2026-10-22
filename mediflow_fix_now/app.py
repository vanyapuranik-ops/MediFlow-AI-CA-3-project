"""MediFlow AI Task 5: Streamlit dashboard. Run: streamlit run app.py
Synthetic data only. Approvals change an in-memory simulated schedule, never a real hospital system
and never the CSV files."""
import pandas as pd
import streamlit as st

import backend
import workflow as wf
import agents

st.set_page_config(page_title="MediFlow AI", page_icon="🏥", layout="wide", initial_sidebar_state="collapsed")

# Polished dashboard theme; keeps all Streamlit controls and workflows native.
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
:root { --mf-ink:#162b3a; --mf-muted:#688092; --mf-teal:#0d9488; --mf-line:#dce8ed; }
.stApp { background: linear-gradient(180deg,#f3f8fa 0%,#f8fbfc 45%,#f3f7fa 100%); color:var(--mf-ink); font-family:'DM Sans',sans-serif; }
.block-container { max-width:1500px; padding-top:1.5rem; padding-bottom:3rem; }
[data-testid="stHeader"] { background:rgba(243,248,250,.85); }
.mf-hero { padding:26px 30px; border-radius:22px; background:linear-gradient(120deg,#102f43 0%,#155e66 60%,#0d9488 100%); color:white; margin-bottom:18px; box-shadow:0 14px 34px rgba(18,65,78,.14); position:relative; overflow:hidden; }
.mf-hero:after { content:'✚'; position:absolute; right:32px; top:-34px; font-size:160px; color:rgba(255,255,255,.07); font-weight:800; }
.mf-eyebrow { text-transform:uppercase; letter-spacing:2px; font-size:11px; font-weight:700; color:#a7f3d0; margin-bottom:8px; }
.mf-title { font-family:'Manrope',sans-serif; font-size:clamp(25px,3vw,36px); font-weight:800; letter-spacing:-1.2px; line-height:1.15; margin:0 0 10px; }
.mf-sub { color:#d3e8ed; font-size:14px; margin:0; max-width:750px; }
.mf-pills { display:flex; gap:8px; flex-wrap:wrap; margin-top:18px; }
.mf-pill { border:1px solid rgba(255,255,255,.22); background:rgba(255,255,255,.09); border-radius:30px; padding:6px 11px; color:#f1fafa; font-size:11px; font-weight:600; }
h1,h2,h3,[data-testid="stMetricLabel"] { font-family:'Manrope',sans-serif !important; }
h2 { letter-spacing:-.5px; }
[data-testid="stMetric"] { background:white; border:1px solid var(--mf-line); padding:18px 20px; border-radius:16px; box-shadow:0 5px 18px rgba(31,67,83,.045); }
[data-testid="stMetricLabel"] { color:var(--mf-muted); font-size:12px; font-weight:700; }
[data-testid="stMetricValue"] { color:var(--mf-ink); font-weight:800; }
.stTabs [data-baseweb="tab-list"] { gap:7px; background:#e8f0f3; border-radius:14px; padding:6px; }
.stTabs [data-baseweb="tab"] { border-radius:10px; padding:10px 15px; height:auto; font-weight:650; color:#567080; }
.stTabs [aria-selected="true"] { background:white !important; color:#087f78 !important; box-shadow:0 2px 8px rgba(24,57,72,.08); }
.stButton > button, .stDownloadButton > button { border-radius:10px; font-weight:700; min-height:42px; border:1px solid #c9dce2; transition:all .15s ease; }
.stButton > button[kind="primary"] { background:linear-gradient(110deg,#0d9488,#087f78); border:0; color:white; box-shadow:0 5px 12px rgba(13,148,136,.18); }
.stButton > button:hover, .stDownloadButton > button:hover { border-color:#0d9488; transform:translateY(-1px); }
[data-testid="stDataFrame"], [data-testid="stTable"] { border:1px solid var(--mf-line); border-radius:12px; overflow:hidden; }
[data-testid="stExpander"] { background:white; border:1px solid var(--mf-line); border-radius:13px; margin-bottom:10px; }
[data-testid="stAlert"] { border-radius:12px; }
.stCaption { color:var(--mf-muted); }
hr { border-color:var(--mf-line); }
@media (max-width: 700px) { .block-container{padding:1rem .8rem 2rem;} .mf-hero{padding:22px 20px;} .stTabs [data-baseweb="tab"]{padding:8px 10px;} }
</style>""", unsafe_allow_html=True)

BADGE = {wf.PENDING: "🟡 PENDING", wf.APPROVED: "🟢 APPROVED",
         wf.REJECTED: "⚫ REJECTED", wf.VALIDATION_FAILED: "🔴 VALIDATION FAILED"}


def init_state():
    if "working" in st.session_state:
        return True
    p, a, err = wf.load_safely()
    if err:
        st.error(err)
        return False
    working, loaded, warning = wf.load_working_schedule(a)
    st.session_state.update(patients=p, original=a, working=working, proposals=[],
                            audit=[], counter=0, last_check=None,
                            working_loaded_from_disk=loaded, agent_workflow_result=None)
    if warning:
        st.warning(warning)
    elif loaded:
        st.info("Restored the previously approved working schedule from working_appointments.csv.")
    return True


def log(msg):
    st.session_state.audit.append({"time": pd.Timestamp.now().strftime("%H:%M:%S"), "event": msg})


def new_pid():
    st.session_state.counter += 1
    return f"PR{st.session_state.counter:03d}"


def conflict_banner(df, label):
    if df.empty:
        st.success(f"{label}: no scheduling conflicts.")
    else:
        st.error(f"{label}: {len(df)} conflict pair(s) detected.")
        st.dataframe(df, use_container_width=True, hide_index=True)


def tab_overview(p, orig, work):
    s_o, s_w = backend.summarise_workflow(p, orig), backend.summarise_workflow(p, work)
    c = st.columns(4)
    c[0].metric("Patients", s_w["patients"])
    c[1].metric("Active appointments", s_w["active_appointments"],
                s_w["active_appointments"] - s_o["active_appointments"] or None)
    c[2].metric("Doctors", s_w["doctors"])
    c[3].metric("Conflict pairs (working)", s_w["conflict_pairs"],
                s_w["conflict_pairs"] - s_o["conflict_pairs"] or None, delta_color="inverse")
    st.subheader("Workflow status")
    passed, rem = backend.validate_schedule(work)
    n_pending = sum(x.status == wf.PENDING for x in st.session_state.proposals)
    rows = [
        ("Planner", "agents.PlannerAgent via Agentic Workflow tab", "Connected"),
        ("Research", "agents.ResearchAgent inspects synthetic records and conflicts", "Connected"),
        ("Executor", "agents.ExecutorAgent proposes changes on a copy", "Connected"),
        ("Critic", "agents.CriticAgent validates the candidate before approval",
         "✅ Working schedule passes" if passed else f"❌ {len(rem)} conflict(s)"),
        ("Human review", "Approval queue", f"{n_pending} pending"),
    ]
    st.dataframe(pd.DataFrame(rows, columns=["Stage", "Backed by", "Status"]),
                 use_container_width=True, hide_index=True)
    conflict_banner(rem, "Working schedule")


def tab_request(p, work):
    st.caption("Request is checked by the backend conflict detector. Nothing is booked until a reviewer approves it.")
    c1, c2 = st.columns(2)
    pid = c1.selectbox("Patient", p.patient_id,
                       format_func=lambda x: f"{x} - {p.set_index('patient_id').patient_name[x]}")
    doc = c2.selectbox("Doctor", sorted(work.doctor_id.unique()))
    c3, c4, c5 = st.columns(3)
    date = c3.date_input("Date", value=pd.to_datetime(work.date).min().date())
    start = c4.text_input("Start time (HH:MM)", "09:00")
    dur = c5.number_input("Duration (min)", 5, 120, 20, step=5)
    if st.button("Check request", type="primary"):
        res = wf.check_new_request(p, work, pid, doc, str(date), start.strip(), dur)
        st.session_state.last_check = res
    res = st.session_state.last_check
    if res is None:
        return
    if res["row"] is None:
        for e in res["errors"]:
            st.error(e)
        return
    if res["ok"]:
        st.success(f"Slot is free. Proposed ID {res['row']['appointment_id']}.")
    else:
        st.error(res["errors"][0])
        st.dataframe(res["conflicts"], use_container_width=True, hide_index=True)
    st.write("**Recommended free slots** (15-min grid, demo clinic hours 08:00-17:00):",
             ", ".join(res["recommended_slots"]) or "none available that day")
    if st.button("Submit to approval queue"):
        prop = wf.proposal_from_request(res, new_pid())
        st.session_state.proposals.insert(0, prop)
        log(f"{prop.proposal_id} submitted: {prop.summary} (validation {'passed' if res['ok'] else 'FAILED'})")
        st.session_state.last_check = None
        st.rerun()



def tab_patient_registration():
    """Register a fictional demo patient and persist it to patients.csv."""
    st.subheader("Register a patient")
    st.caption("Demo environment: use fictional data only. New patients are saved to patients.csv and become selectable for appointment requests.")
    with st.form("patient_registration_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        patient_name = c1.text_input("Patient name", max_chars=100)
        age = c2.number_input("Age", min_value=0, max_value=120, value=25, step=1)
        c3, c4 = st.columns(2)
        department = c3.selectbox("Department", ["General Medicine", "Cardiology", "Orthopedics", "Dermatology", "Neurology", "Other"])
        priority = c4.selectbox("Administrative priority flag", ["ROUTINE", "MEDIUM", "HIGH"])
        reason = st.text_input("Administrative reason", value="Routine consultation", max_chars=200)
        submitted = st.form_submit_button("Register patient", type="primary")

    if not submitted:
        return
    name = patient_name.strip()
    if not name:
        st.error("Enter a patient name.")
        return
    if not reason.strip():
        st.error("Enter an administrative reason.")
        return
    try:
        path = backend.ROOT / "patients.csv"
        current = pd.read_csv(path, dtype={"patient_id": str})
        existing_ids = set(current["patient_id"].astype(str))
        nums = [int(x[1:]) for x in existing_ids if x.startswith("P") and x[1:].isdigit()]
        next_num = max(nums, default=0) + 1
        patient_id = f"P{next_num:03d}"
        while patient_id in existing_ids:
            next_num += 1
            patient_id = f"P{next_num:03d}"
        new_patient = pd.DataFrame([{
            "patient_id": patient_id,
            "patient_name": name,
            "age": int(age),
            "department": department,
            "priority_flag": priority,
            "reason": reason.strip(),
        }], columns=current.columns)
        updated = pd.concat([current, new_patient], ignore_index=True)
        updated.to_csv(path, index=False)
        st.session_state.patients = updated
        log(f"Patient {patient_id} registered in patients.csv")
        st.success(f"Patient registered successfully: {patient_id} — {name}. They are now available in New request.")
        st.rerun()
    except Exception as exc:
        st.error(f"Could not save patient: {type(exc).__name__}: {exc}")

def tab_data(p, orig, work):
    st.subheader("Patients (synthetic)")
    st.dataframe(p, use_container_width=True, hide_index=True)
    st.subheader("Appointments")
    which = st.radio("View", ["Working (simulated)", "Original CSV (never modified)"], horizontal=True)
    df = work if which.startswith("Working") else orig
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("Download working schedule CSV", work.to_csv(index=False),
                       "working_schedule.csv", "text/csv")


def tab_conflicts(orig, work):
    conflict_banner(backend.detect_scheduling_conflicts(orig), "Original data")
    conflict_banner(backend.detect_scheduling_conflicts(work), "Working schedule")


def tab_priority(p, work):
    st.caption("Administrative flags only; not clinical triage.")
    try:
        st.dataframe(backend.prioritise_patients(p), use_container_width=True, hide_index=True)
        st.subheader("Active appointments by priority")
        st.dataframe(wf.priority_for_appointments(p, work), use_container_width=True, hide_index=True)
    except ValueError as e:
        st.error(f"Prioritisation failed: {e}")


def tab_reschedule(work):
    st.caption("Creates a draft, validates it, and shows the result here. The working schedule changes only after human approval.")
    if st.button("Generate reschedule proposal", type="primary", key="generate_reschedule_proposal"):
        try:
            prop = wf.plan_reschedule(work.copy(), new_pid())
            st.session_state.last_reschedule_result = prop
            if prop is None:
                st.session_state.last_reschedule_message = "No conflicts in the working schedule; nothing to propose."
                log("Reschedule requested: no conflicts to correct")
            else:
                st.session_state.proposals.insert(0, prop)
                st.session_state.last_reschedule_message = None
                log(f"{prop.proposal_id} generated: {prop.summary} (validation {'passed' if prop.validation_passed else 'FAILED'})")
        except Exception as e:
            st.session_state.last_reschedule_result = None
            st.session_state.last_reschedule_message = f"Reschedule failed: {type(e).__name__}: {e}"
            log(f"Reschedule failed: {type(e).__name__}: {e}")
    msg = st.session_state.get("last_reschedule_message")
    if msg:
        st.info(msg)
    prop = st.session_state.get("last_reschedule_result")
    if prop is not None:
        st.subheader(f"Proposal {prop.proposal_id}")
        st.write(prop.summary)

        # Human review actions appear beside the draft. Approval remains gated
        # by Critic validation and re-validates against the current schedule.
        if prop.status == wf.PENDING:
            approve_col, reject_col = st.columns(2)
            can_approve = bool(prop.validation_passed and not prop.changes.empty)

            if approve_col.button(
                "Approve",
                key=f"reschedule_approve_{prop.proposal_id}",
                disabled=not can_approve,
            ):
                new_work, updated_prop = wf.approve(
                    prop, st.session_state.working
                )

                if updated_prop.status == wf.APPROVED:
                    try:
                        wf.save_working_schedule(new_work)
                    except Exception as exc:
                        updated_prop.status = wf.VALIDATION_FAILED
                        updated_prop.validation_passed = False
                        updated_prop.reasons = [
                            f"Could not persist approved schedule; "
                            f"working schedule unchanged: {exc}"
                        ]
                        log(f"{updated_prop.proposal_id} save failed: {exc}")
                    else:
                        st.session_state.working = new_work
                        st.session_state.working_loaded_from_disk = True

                log(f"{updated_prop.proposal_id} {updated_prop.status}")
                st.rerun()

            if reject_col.button(
                "Reject",
                key=f"reschedule_reject_{prop.proposal_id}",
            ):
                wf.reject(prop)
                log(f"{prop.proposal_id} {prop.status}")
                st.rerun()

        if prop.changes.empty:
            st.warning("The scheduling function returned no changes. Do not approve this proposal.")
        else:
            st.dataframe(prop.changes, use_container_width=True, hide_index=True)
        st.write("Correction attempts")
        st.dataframe(pd.DataFrame(prop.attempts), use_container_width=True, hide_index=True)
        if prop.validation_passed:
            st.success("Critic validation passed. This is still a draft; approve it in the Approvals tab.")
        else:
            st.error("Critic validation failed. This proposal must not be approved.")
            if not prop.validation_conflicts.empty:
                st.dataframe(prop.validation_conflicts, use_container_width=True, hide_index=True)
            for reason in prop.reasons:
                st.error(reason)
        st.caption("The Conflicts tab shows the current working schedule. It will show zero conflicts only after a validated proposal is approved.")


def tab_agentic_workflow(work):
    """Run the actual Research -> Planner -> Executor -> Critic workflow and queue its draft."""
    st.subheader("Four-agent scheduling workflow")
    st.caption("Deterministic software agents using synthetic records. No appointment changes are applied until human approval.")
    st.markdown("**Sequence:** Research records → Plan next action → Execute a draft on a copy → Critic validates → Human reviews.")
    if st.button("Run four-agent workflow", type="primary", key="run_agentic_workflow"):
        try:
            result = agents.run_agent_workflow(
                st.session_state.patients.copy(deep=True),
                work.copy(deep=True),
                max_attempts=3,
            )
            st.session_state.agent_workflow_result = result
            if result.passed and result.final_schedule is not None:
                before = work.set_index("appointment_id")["start_time"]
                after = result.final_schedule.set_index("appointment_id")["start_time"]
                changes = [
                    {"appointment_id": aid, "field": "start_time", "old": before[aid], "new": after[aid]}
                    for aid in before.index.intersection(after.index) if str(before[aid]) != str(after[aid])
                ]
                # Queue only meaningful, validated drafts. Approval uses the existing
                # workflow's stale-proposal check and revalidation before persistence.
                if changes:
                    prop = wf.Proposal(
                        proposal_id=new_pid(),
                        kind="RESCHEDULE_DRAFT",
                        changes=pd.DataFrame(changes, columns=["appointment_id", "field", "old", "new"]),
                        summary="Agentic workflow proposal: " + ", ".join(
                            f"{c['appointment_id']} {c['old']} → {c['new']}" for c in changes),
                        validation_passed=bool(result.critic.get("passed")),
                        validation_conflicts=result.critic.get("conflicts", pd.DataFrame()),
                        attempts=result.attempts,
                        reasons=list(result.critic.get("errors", [])),
                    )
                    st.session_state.proposals.insert(0, prop)
                    log(f"{prop.proposal_id} created by four-agent workflow; pending human approval")
                else:
                    st.info("Agents completed successfully. No schedule changes were needed.")
            else:
                log("Four-agent workflow finished with validation failure; no proposal was queued.")
        except Exception as exc:
            st.session_state.agent_workflow_result = None
            st.error(f"Agent workflow failed safely: {type(exc).__name__}: {exc}")
            log(f"Agent workflow failed: {type(exc).__name__}: {exc}")

    result = st.session_state.get("agent_workflow_result")
    if result is None:
        st.info("Click **Run four-agent workflow** to execute the actual agents and see their outputs.")
        return

    st.divider()
    st.subheader("Execution trace")
    stage_cols = st.columns(4)
    stage_data = [
        ("1 · Research", bool(result.research.get("ok")), "Records and conflicts inspected"),
        ("2 · Planner", result.plan.get("action") != "STOP", result.plan.get("action", "No action")),
        ("3 · Executor", bool(result.execution), "Draft created on a copy" if result.execution else "Not run"),
        ("4 · Critic", bool(result.critic.get("passed")), "Validation passed" if result.critic.get("passed") else "Validation failed"),
    ]
    for col, (name, ok, detail) in zip(stage_cols, stage_data):
        col.metric(name, "PASS" if ok else "CHECK", detail)

    with st.expander("Research Agent output", expanded=True):
        st.write("Validation:", "Passed" if result.research.get("ok") else "Failed")
        st.write("Synthetic patients researched:", result.research.get("patient_count", "—"))
        st.write("Appointments inspected:", result.research.get("appointment_count", "—"))
        conflicts = result.research.get("conflicts", pd.DataFrame())
        st.write("Initial scheduling conflicts:", len(conflicts))
        if not conflicts.empty:
            st.dataframe(conflicts, use_container_width=True, hide_index=True)
        for err in result.research.get("errors", []):
            st.error(err)

    with st.expander("Planner Agent output", expanded=True):
        st.json({k: v for k, v in result.plan.items() if k != "initial_conflicts"} | {"initial_conflicts": result.plan.get("initial_conflicts", 0)})

    with st.expander("Executor Agent output", expanded=True):
        if result.execution:
            st.write("Changes proposed (not yet applied):")
            changes = result.execution.get("changes", pd.DataFrame())
            if changes.empty:
                st.info("Executor did not need to move any appointments.")
            else:
                st.dataframe(changes, use_container_width=True, hide_index=True)
            st.write("Source input remained unchanged:", result.execution.get("source_unchanged", False))
        else:
            st.info("Execution was skipped because Research validation failed.")

    with st.expander("Critic Agent output", expanded=True):
        st.write("Validation passed:", bool(result.critic.get("passed")))
        st.write("Human approval required:", bool(result.critic.get("human_approval_required", True)))
        errors = result.critic.get("errors", [])
        if errors:
            for err in errors:
                st.error(err)
        else:
            st.success("Critic found no remaining scheduling conflicts or integrity errors.")

    st.subheader("Correction / retry history")
    if result.attempts:
        st.dataframe(pd.DataFrame(result.attempts), use_container_width=True, hide_index=True)
    else:
        st.info("No execution attempts were made because research validation failed.")
    st.write("Final workflow status:", result.status)
    if result.passed:
        st.success("Agent workflow passed. Any proposed change is still pending human approval in the Approvals tab.")
        st.info("Open **Approvals** to approve or reject the queued proposal. Approval revalidates against the latest working schedule.")
    else:
        st.error("Agent workflow did not pass validation. No change was queued for approval.")


def tab_approvals(work):
    props = st.session_state.proposals
    if not props:
        st.info("No proposals yet. Generate one from 'Reschedule' or 'New request'.")
        return
    st.warning("Simulation only: approved changes are saved to working_appointments.csv. The original appointments.csv and any real hospital system are never changed.")
    for pr in props:
        with st.expander(f"{pr.proposal_id} · {pr.kind} · {BADGE[pr.status]} · {pr.created}",
                         expanded=pr.status == wf.PENDING):
            st.write(pr.summary)
            st.dataframe(pr.changes, use_container_width=True, hide_index=True)
            if pr.validation_passed:
                st.success("Critic validation at creation: passed")
            else:
                st.error("Critic validation at creation: failed")
                st.dataframe(pr.validation_conflicts, use_container_width=True, hide_index=True)
            if pr.attempts:
                st.write("Retry / correction attempts")
                st.dataframe(pd.DataFrame(pr.attempts), use_container_width=True, hide_index=True)
            for r in pr.reasons:
                st.error(r) if pr.status in (wf.VALIDATION_FAILED, wf.REJECTED) or not pr.validation_passed else st.info(r)
            if pr.status == wf.PENDING:
                a, b = st.columns(2)
                if a.button("Approve (re-validates)", key=f"ap_{pr.proposal_id}"):
                    new_work, pr = wf.approve(pr, st.session_state.working)
                    if pr.status == wf.APPROVED:
                        try:
                            wf.save_working_schedule(new_work)
                        except Exception as exc:
                            pr.status = wf.VALIDATION_FAILED
                            pr.validation_passed = False
                            pr.reasons = [f"Could not persist approved schedule; working schedule unchanged: {exc}"]
                            log(f"{pr.proposal_id} SAVE FAILED: {type(exc).__name__}: {exc}")
                        else:
                            st.session_state.working = new_work
                            st.session_state.working_loaded_from_disk = True
                    log(f"{pr.proposal_id} {pr.status}")
                    st.rerun()
                if b.button("Reject", key=f"rj_{pr.proposal_id}"):
                    wf.reject(pr)
                    log(f"{pr.proposal_id} REJECTED")
                    st.rerun()


def tab_audit():
    a = st.session_state.audit
    st.dataframe(pd.DataFrame(a, columns=["time", "event"]) if a else pd.DataFrame(columns=["time", "event"]),
                 use_container_width=True, hide_index=True)
    st.caption("The working schedule persists in working_appointments.csv. Reset deletes that simulated file and restores the original CSV schedule.")
    if st.button("Reset session and restore original schedule"):
        try:
            wf.reset_working_schedule()
        except OSError as exc:
            st.error(f"Could not remove saved working schedule: {exc}")
            return
        for k in ("working", "original", "proposals", "audit", "counter", "last_check", "patients",
                  "working_loaded_from_disk", "last_reschedule_result", "last_reschedule_message", "agent_workflow_result"):
            st.session_state.pop(k, None)
        st.rerun()


def main():
    st.markdown("""<section class="mf-hero">
      <div class="mf-eyebrow">MEDIFLOW AI · CARE OPERATIONS</div>
      <div class="mf-title">Clinic made simpler</div>
      <p class="mf-sub">Use the steps below to register a patient, request an appointment, and review proposed changes.</p>
      <div class="mf-pills"><span class="mf-pill">● Demo application</span><span class="mf-pill">Fictional data only</span><span class="mf-pill">Changes need approval</span></div>
    </section>""", unsafe_allow_html=True)
    if not init_state():
        return
    p, orig, work = st.session_state.patients, st.session_state.original, st.session_state.working
    st.info("**Quick start:** 1. Add or choose a patient → 2. Check an appointment time → 3. Submit it → 4. Review it under Approvals. Nothing is booked until approved.")
    tabs = st.tabs(["🏠 Home", "👤 Patients", "📅 Appointments", "🤖 Agentic Workflow", "✅ Approvals", "🛠 More tools"])
    with tabs[0]:
        tab_overview(p, orig, work)
        st.caption("Start with Patients if the person is not listed yet. Use Appointments to request a time.")
    with tabs[1]:
        patient_tabs = st.tabs(["➕ Add a patient", "📋 Patient list"])
        with patient_tabs[0]: tab_patient_registration()
        with patient_tabs[1]:
            st.subheader("Registered patients")
            st.caption("Patients added here are saved in patients.csv and become available for appointment requests.")
            st.dataframe(st.session_state.patients, use_container_width=True, hide_index=True)
    with tabs[2]:
        st.subheader("Request an appointment")
        st.caption("Choose a patient, doctor, date and time. Check the slot first, then submit it for approval.")
        tab_request(st.session_state.patients, work)
    with tabs[3]:
        tab_agentic_workflow(work)
    with tabs[4]:
        st.subheader("Review appointment changes")
        st.caption("Approve only proposals that look correct. Approval re-checks for conflicts before saving the simulated schedule.")
        tab_approvals(work)
    with tabs[5]:
        tool_tabs = st.tabs(["Schedule repair", "Conflicts", "Priority", "All data", "Activity log"])
        with tool_tabs[0]: tab_reschedule(work)
        with tool_tabs[1]: tab_conflicts(orig, work)
        with tool_tabs[2]: tab_priority(st.session_state.patients, work)
        with tool_tabs[3]: tab_data(st.session_state.patients, orig, work)
        with tool_tabs[4]: tab_audit()


main()
