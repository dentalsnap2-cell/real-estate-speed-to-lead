import os
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from backend.services import get_settings, update_settings, list_leads, set_lead_status

load_dotenv()
st.set_page_config(page_title="Speed-to-Lead | Agency Console", page_icon="🏡", layout="wide")
AGENCY_ID = os.getenv("AGENCY_ID", "default-agency")
API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.getenv("AGENCY_API_KEY", "")

st.markdown("""
<style>
:root { --navy:#123B5D; --gold:#D18B35; }
.block-container { padding-top: 1.6rem; }
.hero { padding: 1.25rem 1.5rem; border-radius: 14px; color: white;
        background: linear-gradient(110deg,#123B5D,#23658A); margin-bottom: 1rem; }
.hero h1 { color:white; margin:0; font-size:2rem; }
.hero p { color:#EAF2F7; margin:.35rem 0 0 0; }
div[data-testid="stMetric"] { background:#F3F7FA; border:1px solid #E1EAF0;
  padding:14px 16px; border-radius:12px; }
</style>
<div class="hero"><h1>Real Estate Speed-to-Lead</h1>
<p>AI-powered enquiry response, qualification and agent follow-up console</p></div>
""", unsafe_allow_html=True)

tab_pipeline, tab_config, tab_simulator = st.tabs(
    ["📈 Live Lead Pipeline", "🧠 AI Brain & Rules", "🧪 Webhook Simulator"]
)

with tab_pipeline:
    st.subheader("Lead performance")
    leads = list_leads(AGENCY_ID)
    df = pd.DataFrame(leads)
    if df.empty:
        st.info("No leads yet. Use the Webhook Simulator or connect your website form.")
    else:
        scores = pd.to_numeric(df.get("lead_score"), errors="coerce")
        avg_score = float(scores.mean()) if scores.notna().any() else 0
        hot_count = int((scores >= 8).sum())
        response = pd.to_numeric(df.get("response_time_ms"), errors="coerce")
        avg_response = float(response.mean()) / 1000 if response.notna().any() else 0
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Leads", len(df))
        c2.metric("Average AI Score", f"{avg_score:.1f}/10")
        c3.metric("Hot Leads", hot_count)
        c4.metric("Avg. Processing Time", f"{avg_response:.1f}s")

        f1, f2 = st.columns(2)
        score_floor = f1.slider("Minimum lead score", 1, 10, 1)
        intents = sorted([x for x in df["intent"].dropna().unique()]) if "intent" in df else []
        selected_intents = f2.multiselect("Intent", intents, default=intents)
        view = df.copy()
        view["lead_score"] = pd.to_numeric(view["lead_score"], errors="coerce")
        view = view[view["lead_score"] >= score_floor]
        if selected_intents and "intent" in view:
            view = view[view["intent"].isin(selected_intents)]
        display_cols = [c for c in ["created_at","full_name","email","phone","intent",
                                    "extracted_budget","extracted_location","lead_score",
                                    "status","email_status","alert_status"] if c in view.columns]
        st.dataframe(view[display_cols], use_container_width=True, hide_index=True)

        st.markdown("#### Update lead status")
        options = {f"{r.get('full_name')} · {r.get('email')} · {r.get('id')}": r.get("id") for r in leads}
        chosen = st.selectbox("Lead", list(options.keys()))
        new_status = st.selectbox("New status", ["New", "Contacted", "Closed"])
        if st.button("Save status", type="primary"):
            set_lead_status(AGENCY_ID, options[chosen], new_status)
            st.success("Lead status updated.")
            st.rerun()

with tab_config:
    st.subheader("Agency qualification and response rules")
    settings = get_settings(AGENCY_ID)
    neighborhoods = settings.get("target_neighborhoods", [])
    if isinstance(neighborhoods, str):
        neighborhoods = [x.strip() for x in neighborhoods.split(",") if x.strip()]
    with st.form("agency_settings_form"):
        agency_name = st.text_input("Agency name", settings.get("agency_name", ""))
        target_locations = st.text_input("Target locations (comma-separated)", ", ".join(neighborhoods))
        minimum_budget = st.number_input("Minimum budget threshold", min_value=0.0,
                                         value=float(settings.get("minimum_budget") or 0), step=10000.0)
        email_signoff = st.text_area("Email sign-off", settings.get("email_signoff", ""))
        system_instructions = st.text_area("AI system instructions", settings.get("system_instructions", ""), height=130)
        brochure_intro = st.text_area("PDF brochure introduction", settings.get("brochure_intro", ""), height=90)
        submitted = st.form_submit_button("Save agency rules", type="primary")
        if submitted:
            update_settings(AGENCY_ID, {
                "agency_name": agency_name,
                "target_neighborhoods": [x.strip() for x in target_locations.split(",") if x.strip()],
                "minimum_budget": minimum_budget,
                "email_signoff": email_signoff,
                "system_instructions": system_instructions,
                "brochure_intro": brochure_intro,
            })
            st.success("Agency settings saved.")
            st.rerun()

with tab_simulator:
    st.subheader("Send a test lead to the live webhook")
    st.caption(f"Endpoint: {API_BASE}/webhook/new-lead")
    with st.form("test_lead_form"):
        name = st.text_input("Full name", "Alex Morgan")
        email = st.text_input("Email", "alex@example.com")
        phone = st.text_input("Phone", "+1 555 010 2000")
        interest = st.text_input("Property interest", "3-bedroom apartment in Downtown")
        message = st.text_area("Inquiry message",
            "I am ready to buy within the next 30 days. My budget is around 650000. Please contact me.")
        send_test = st.form_submit_button("Submit test lead", type="primary")
    if send_test:
        if not API_KEY:
            st.error("AGENCY_API_KEY is missing from the dashboard environment.")
        else:
            try:
                response = requests.post(
                    f"{API_BASE}/webhook/new-lead",
                    headers={"X-API-Key": API_KEY},
                    json={"full_name": name, "email": email, "phone": phone,
                          "property_interest": interest, "inquiry_message": message},
                    timeout=20,
                )
                if response.status_code == 202:
                    st.success("Webhook accepted. Processing will run in the FastAPI background task.")
                    st.json(response.json())
                else:
                    st.error(f"Webhook returned {response.status_code}: {response.text}")
            except requests.RequestException as exc:
                st.error(f"Could not reach FastAPI: {exc}")

st.caption("Starter deployment: protect dashboard access before sharing it publicly. Never expose Supabase service-role or webhook secrets in client-side code.")
