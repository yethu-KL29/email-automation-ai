import json

import httpx
import streamlit as st

from job_outreach.config import settings

st.set_page_config(page_title="Job Outreach", page_icon="✉️", layout="wide")
config = settings()


def api(method, path, **kwargs):
    try:
        with httpx.Client(
            base_url=config.api_url,
            timeout=180,
            headers={"Authorization": "Bearer " + config.api_token.get_secret_value()},
        ) as client:
            response = client.request(method, "/api/v1" + path, **kwargs)
        if response.status_code >= 400:
            st.error(response.json().get("detail", "Request failed"))
            st.stop()
        return response.json()
    except httpx.HTTPError:
        st.error("API unavailable. Start the API and initialize the database using the README.")
        st.stop()


def action(label, path, key=None):
    if st.button(label, key=key):
        result = api("POST", path)
        st.success(result)
        return True
    return False


st.title("Job discovery & outreach")
st.caption("Review your profile, discover roles, and approve each application.")
stats = api("GET", "/stats")
if stats["dry_run"]:
    st.info("Preview mode: no emails are sent and no Gmail drafts are created.")
if st.sidebar.button("Stop all sending", type="primary"):
    api("POST", "/sending/stop")
    st.sidebar.success("Sending stopped. Review operations guide to re-enable.")
page = st.sidebar.radio(
    "Workspace",
    ["Overview", "Resume & profile", "Search & sources", "Jobs", "Draft review", "History"],
)

if page == "Overview":
    columns = st.columns(4)
    for column, label, value in zip(
        columns,
        ["Discovered", "Verified recent", "Verified contacts", "Matches"],
        [stats["jobs"], stats["verified_recent"], stats["verified_contacts"], stats["matches"]],
    ):
        column.metric(label, value)
    st.subheader("Application pipeline")
    st.json(stats["pipeline"])
    action("Discover jobs now", "/discovery/run")
    action("Match jobs to resume", "/matches/run")
    st.caption(
        "Optional AI assessment sends reviewed facts and job descriptions to your configured provider within the per-run limit."
    )
    action("Run configured AI assessment", "/matches/assess")

elif page == "Resume & profile":
    upload = st.file_uploader("Upload resume", type=["pdf", "docx"])
    if upload and st.button("Extract resume"):
        result = api(
            "POST", "/resumes", files={"file": (upload.name, upload.getvalue(), upload.type)}
        )
        st.success(f"Saved resume version {result['version']}")
        if "extracted_text" in result:
            st.text_area(
                "Extracted text — review for accuracy", result["extracted_text"], height=240
            )
    profile = api("GET", "/profile")
    with st.form("profile"):
        name = st.text_input("Full name", profile.get("name", ""))
        email = st.text_input("Candidate email", profile.get("email", ""))
        skills = st.text_input("Skills (comma separated)", ", ".join(profile.get("skills", [])))
        facts = st.text_area(
            "Verified achievements and experience (one statement per line)",
            "\n".join(profile.get("facts", [])),
            height=180,
            help="Only write statements supported by your resume. These may appear verbatim in emails.",
        )
        years = st.text_input(
            "Total experience in years (leave blank if unknown)",
            str(profile.get("experience_years") or ""),
        )
        signature = st.text_area("Email signature", profile.get("signature", ""))
        authorization = st.text_input(
            "Work authorization", profile.get("work_authorization", "unknown")
        )
        verified = st.checkbox(
            "I reviewed these facts against my resume", value=profile.get("verified", False)
        )
        if st.form_submit_button("Save reviewed profile"):
            try:
                experience = float(years) if years else None
            except ValueError:
                st.error("Experience must be a number")
                st.stop()
            api(
                "PUT",
                "/profile",
                json={
                    "name": name,
                    "email": email,
                    "skills": [s.strip() for s in skills.split(",") if s.strip()],
                    "facts": [f.strip() for f in facts.splitlines() if f.strip()],
                    "experience_years": experience,
                    "signature": signature,
                    "work_authorization": authorization,
                    "verified": verified,
                },
            )
            st.success("Profile saved")
    st.dataframe(api("GET", "/resumes"))

elif page == "Search & sources":
    st.subheader("Job preferences")
    search = api("GET", "/search")
    st.caption("Use JSON to set role lists, locations, keywords, minimum score, and limits.")
    value = st.text_area("Search settings", json.dumps(search, indent=2), height=360)
    if st.button("Save search settings"):
        try:
            parsed = json.loads(value)
        except ValueError:
            st.error("Invalid JSON")
            st.stop()
        api("PUT", "/search", json=parsed)
        st.success("Search updated")
    st.subheader("Company job boards")
    st.caption(
        'Add verified company boards: {"source":"ashby", "board":"company-board", "company":"Company", "domain":"company.com", "enabled":true}. Supported sources: ashby, greenhouse, lever.'
    )
    value = st.text_area("Sources", json.dumps(api("GET", "/sources"), indent=2), height=240)
    if st.button("Save sources"):
        try:
            parsed = json.loads(value)
        except ValueError:
            st.error("Invalid JSON")
            st.stop()
        api("PUT", "/sources", json=parsed)
        st.success("Sources updated")

elif page == "Jobs":
    status = st.selectbox(
        "Posting date", ["", "VERIFIED_RECENT", "POSTING_DATE_UNKNOWN", "VERIFIED_OLDER"]
    )
    q = st.text_input("Title contains")
    offset = st.number_input("Start at record", min_value=0, step=50)
    jobs = api("GET", "/jobs", params={"freshness_filter": status, "q": q, "offset": offset})
    st.caption(f"{jobs['total']} jobs in this view")
    matches = {m["job_id"]: m for m in api("GET", "/matches")}
    resumes = api("GET", "/resumes")
    for job in jobs["items"]:
        data = job["data"]
        with st.expander(f"{data['company']} · {data['title']} · {data.get('location', '')}"):
            st.write(f"Posting: {data.get('posting_date') or 'Unknown'} · {job['freshness']}")
            st.write(f"Source: {job['source']} · Salary: {data.get('salary') or 'Not supplied'}")
            st.link_button("Original application page", data["apply_url"])
            st.text(data["description"])
            if job["id"] in matches:
                st.json(matches[job["id"]]["result"])
            action(
                "Find recruiting contacts",
                f"/jobs/{job['id']}/contacts",
                key=f"contacts-{job['id']}",
            )
            contacts = api("GET", "/contacts", params={"job_id": job["id"]})
            if not contacts:
                st.caption("No recruiting contact found. Use the original application portal.")
            for contact in contacts:
                st.write(contact["email"] + " · " + contact["contact_type"])
                st.write(contact["evidence"])
                st.link_button(
                    "Contact source", contact["source_url"], key=f"source-{contact['id']}"
                )
                if not contact["verified_at"]:
                    proof = st.text_area(
                        "Published evidence including this email",
                        contact["evidence"],
                        key=f"proof-{contact['id']}",
                    )
                    if st.button(
                        "I verified this recruiting contact", key=f"verify-{contact['id']}"
                    ):
                        api(
                            "POST",
                            f"/contacts/{contact['id']}/verify",
                            json={"source_url": contact["source_url"], "evidence": proof},
                        )
                        st.rerun()
                if resumes and contact["verified_at"]:
                    resume_id = st.selectbox(
                        "Resume version", [r["id"] for r in resumes], key=f"resume-{contact['id']}"
                    )
                    if st.button("Create application", key=f"create-{contact['id']}"):
                        api(
                            "POST",
                            "/outreach",
                            json={
                                "job_id": job["id"],
                                "contact_id": contact["id"],
                                "resume_id": resume_id,
                            },
                        )
                        st.success("Application created. Open Draft review.")

elif page == "Draft review":
    for row in api("GET", "/outreach"):
        with st.expander(f"#{row['id']} · {row['recipient']} · {row['status']}"):
            st.caption(f"Resume ID: {row['resume_id']} · Job ID: {row['job_id']}")
            if row["status"] not in [
                "SENT",
                "SENDING",
                "SEND_UNCERTAIN",
                "REPLIED",
                "INTERVIEW",
                "CLOSED",
            ]:
                if action(
                    "Generate draft", f"/outreach/{row['id']}/draft", key=f"generate-{row['id']}"
                ):
                    st.rerun()
                subject = st.text_input("Subject", row["subject"], key=f"subject-{row['id']}")
                body = st.text_area("Email", row["body"], height=300, key=f"body-{row['id']}")
                if st.button("Save edits", key=f"edit-{row['id']}"):
                    api("PATCH", f"/outreach/{row['id']}", json={"subject": subject, "body": body})
                    st.rerun()
                confirmed = st.checkbox(
                    "I reviewed the saved recipient, content, and resume",
                    key=f"confirm-{row['id']}",
                )
                if st.button(
                    "Approve saved draft",
                    disabled=not confirmed or subject != row["subject"] or body != row["body"],
                    key=f"approve-{row['id']}",
                ):
                    api("POST", f"/outreach/{row['id']}/approve")
                    st.rerun()
                action("Reject", f"/outreach/{row['id']}/reject", key=f"reject-{row['id']}")
                action(
                    "Create Gmail draft",
                    f"/outreach/{row['id']}/gmail-draft",
                    key=f"gmail-{row['id']}",
                )
                action(
                    "Queue approved send / dry run",
                    f"/outreach/{row['id']}/send",
                    key=f"send-{row['id']}",
                )
            else:
                st.write(row["subject"])
                st.text(row["body"])
                st.write("Gmail message: " + (row["gmail_message_id"] or "Not confirmed"))
                if row["status"] == "SEND_UNCERTAIN":
                    action(
                        "Reconcile sent messages (requires read permission)",
                        f"/outreach/{row['id']}/reconcile",
                        key=f"reconcile-{row['id']}",
                    )

elif page == "History":
    st.dataframe(api("GET", "/discovery/runs"))
    st.dataframe(api("GET", "/outreach"))
    with httpx.Client(
        headers={"Authorization": "Bearer " + config.api_token.get_secret_value()}
    ) as client:
        result = client.get(config.api_url + "/api/v1/export")
    if result.is_success:
        st.download_button(
            "Export jobs to CSV", result.content, file_name="jobs.csv", mime="text/csv"
        )
