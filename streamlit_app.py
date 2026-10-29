"""
NovaTech AP Invoice Automation — showcase app.

An interactive portfolio showcase for an AI-assisted accounts-payable automation.
Runs entirely on the committed synthetic run data — no API keys, no secrets.

Deploy free on Streamlit Community Cloud (share.streamlit.io) from this repo.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

BASE = Path(__file__).parent
RESULTS = BASE / "results"
SAMPLES = BASE / "sample_invoices"

# ---- controls configuration (mirrors the n8n Controls node) ----
APPROVAL_LIMIT = 2500
MAX_AGE_DAYS = 90
CAPEX_MIN = 1000
AS_OF = date(2026, 2, 28)  # the processing date the run treats as "today"

STATUS_COLORS = {
    "READY": "#1a9850",
    "NEEDS_APPROVAL": "#f1c40f",
    "HOLD": "#e67e22",
    "EXCEPTION": "#d73027",
}

st.set_page_config(
    page_title="AP Invoice Automation",
    page_icon="🧾",
    layout="wide",
)


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
@st.cache_data
def load_data():
    controls = pd.read_csv(RESULTS / "extraction_controls.csv")
    expected = pd.read_csv(SAMPLES / "expected_results.csv")
    accuracy = pd.read_csv(RESULTS / "extraction_accuracy.csv")
    # tidy
    controls["stated_total"] = pd.to_numeric(controls["stated_total"], errors="coerce")
    controls["display_vendor"] = controls["qbo_vendor_name"].fillna("").where(
        controls["qbo_vendor_name"].notna() & (controls["qbo_vendor_name"].astype(str) != ""),
        controls["vendor_name"],
    )
    return controls, expected, accuracy


def exception_type(reason: str) -> str:
    """First keyword of an exception_reason, e.g. 'EXACT_DUPLICATE of X' -> 'EXACT_DUPLICATE'."""
    if not isinstance(reason, str) or not reason.strip():
        return ""
    first = reason.split("|")[0].strip()
    return first.split()[0] if first else ""


controls, expected, accuracy = load_data()

KNOWN_VENDORS = sorted(
    controls.loc[controls["qbo_vendor_id"].notna(), "qbo_vendor_name"].dropna().unique().tolist()
)

# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("🧾 AP Invoice Automation")
    st.caption(
        "An AI-assisted accounts-payable pipeline: read an invoice from email, "
        "apply accounting controls, then auto-post to QuickBooks or route for review."
    )
    st.markdown("**Stack:** n8n · QuickBooks Online · Google Sheets · OpenAI")
    st.markdown("[View the code on GitHub ↗](https://github.com/sadia-yusuf/novatech-ap-automation)")
    st.divider()
    st.caption(
        "Built around a fictional client, **NovaTech Consulting LLC**, on entirely "
        "synthetic data. Design principle: **AI proposes, rules constrain, humans approve.**"
    )


# --------------------------------------------------------------------------- #
# Header + KPIs
# --------------------------------------------------------------------------- #
st.title("Accounts-Payable Invoice Automation")
st.markdown(
    "The hard part of AP isn't *reading* an invoice — it's deciding what **not** to do with it. "
    "This pipeline applies a full set of accounting controls to every invoice and only auto-posts "
    "the ones that are genuinely clean. Everything doubtful is escalated; nothing is silently fixed."
)

total = len(controls)
posted = int((controls["status"] == "READY").sum())
flagged = total - posted
acc_rate = (accuracy["all_fields"].astype(str).str.upper() == "PASS").mean() * 100 if "all_fields" in accuracy else float("nan")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Invoices processed", total)
k2.metric("Auto-posted to QuickBooks", posted)
k3.metric("Held for review", flagged)
k4.metric("Extraction accuracy", f"{acc_rate:.0f}%")

st.divider()

tab_overview, tab_run, tab_sim, tab_how = st.tabs(
    ["📊 The run", "🔎 Results explorer", "🧪 Try the controls", "⚙️ How it works"]
)

# --------------------------------------------------------------------------- #
# Tab: The run
# --------------------------------------------------------------------------- #
with tab_overview:
    st.subheader("What happened to each invoice")
    st.caption(
        "Every invoice is assigned a status. **READY** auto-posts a bill to QuickBooks; "
        "everything else triggers a review email and is never posted."
    )

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Status breakdown**")
        status_counts = (
            controls["status"].value_counts().rename_axis("status").reset_index(name="count")
        )
        chart = (
            alt.Chart(status_counts)
            .mark_bar()
            .encode(
                x=alt.X("count:Q", title="Invoices"),
                y=alt.Y("status:N", sort="-x", title=None),
                color=alt.Color(
                    "status:N",
                    scale=alt.Scale(
                        domain=list(STATUS_COLORS.keys()),
                        range=list(STATUS_COLORS.values()),
                    ),
                    legend=None,
                ),
                tooltip=["status", "count"],
            )
            .properties(height=200)
        )
        st.altair_chart(chart, width="stretch")

    with c2:
        st.markdown("**Why invoices were stopped**")
        ex = controls.loc[controls["status"] == "EXCEPTION", "exception_reason"].apply(exception_type)
        ex = ex[ex != ""]
        if len(ex):
            ex_counts = ex.value_counts().rename_axis("reason").reset_index(name="count")
            chart2 = (
                alt.Chart(ex_counts)
                .mark_bar(color="#d73027")
                .encode(
                    x=alt.X("count:Q", title="Invoices"),
                    y=alt.Y("reason:N", sort="-x", title=None),
                    tooltip=["reason", "count"],
                )
                .properties(height=200)
            )
            st.altair_chart(chart2, width="stretch")
        else:
            st.info("No exceptions in this run.")

    st.markdown("**The takeaway**")
    st.success(
        f"Of {total} invoices, **{posted} posted automatically** and **{flagged} were correctly "
        "stopped** before posting — duplicates, unknown vendors, footing mismatches, an over-limit "
        "approval, and an accrual hold. That second number is the whole point: automation that posts "
        "everything is a liability."
    )
    st.caption(
        "Audit note: `status = READY` means *approved to post*, not *posted*. The proof a bill "
        "reached QuickBooks is a non-empty `qbo_bill_id` in the audit log."
    )

# --------------------------------------------------------------------------- #
# Tab: Results explorer
# --------------------------------------------------------------------------- #
with tab_run:
    st.subheader("Every invoice, and the controls' verdict")
    statuses = st.multiselect(
        "Filter by status",
        options=list(STATUS_COLORS.keys()),
        default=list(STATUS_COLORS.keys()),
    )
    view = controls[controls["status"].isin(statuses)].copy()

    show = view[
        ["display_vendor", "invoice_number", "stated_total", "status", "exception_reason", "review_notes"]
    ].rename(
        columns={
            "display_vendor": "Vendor",
            "invoice_number": "Invoice #",
            "stated_total": "Amount",
            "status": "Status",
            "exception_reason": "Exception reason",
            "review_notes": "Notes",
        }
    )

    def _style(row):
        color = STATUS_COLORS.get(row["Status"], "#999999")
        return [f"color: {color}; font-weight: 600" if c == "Status" else "" for c in row.index]

    st.dataframe(
        show.style.apply(_style, axis=1).format({"Amount": "${:,.2f}"}),
        width="stretch",
        hide_index=True,
    )
    st.caption(f"{len(view)} of {total} invoices shown.")

    with st.expander("See a single invoice's extracted line items"):
        pick = st.selectbox("Invoice", view["invoice_number"].tolist())
        row = view[view["invoice_number"] == pick].iloc[0]
        try:
            lines = json.loads(row["lines_json"])
            st.table(pd.DataFrame(lines))
        except Exception:
            st.write("No line-item detail available.")

# --------------------------------------------------------------------------- #
# Tab: Try the controls
# --------------------------------------------------------------------------- #
def run_controls(vendor_known, amount, inv_date, footing_ok, is_duplicate, service_prior_month):
    blocking, notes = [], []
    hold = needs_approval = False

    if not vendor_known:
        blocking.append("UNKNOWN_VENDOR")
    if is_duplicate:
        blocking.append("EXACT_DUPLICATE")
    if not footing_ok:
        blocking.append("FOOTING_MISMATCH")

    age = (AS_OF - inv_date).days
    if age < 0:
        blocking.append("FUTURE_DATED")
    elif age > MAX_AGE_DAYS:
        blocking.append(f"STALE_INVOICE ({age} days)")

    if service_prior_month:
        hold = True
        notes.append("SERVICE_PERIOD_REVIEW")
    if amount > APPROVAL_LIMIT:
        needs_approval = True
        notes.append(f"OVER_APPROVAL_LIMIT (> ${APPROVAL_LIMIT:,})")

    if blocking:
        status = "EXCEPTION"
    elif hold:
        status = "HOLD"
    elif needs_approval:
        status = "NEEDS_APPROVAL"
    else:
        status = "READY"
    return status, blocking, notes


GL_RULES = [
    (["slack", "hubspot", "zoom", "adobe", "subscription", "software", "licen"], "Software Subscriptions"),
    (["aws", "azure", "cloud", "hosting", "server"], "Cloud Hosting"),
    (["comcast", "internet", "utilit", "phone", "telecom"], "Utilities & Internet"),
    (["airfare", "flight", "hotel", "airline", "travel", "skyward"], "Travel"),
    (["meal", "restaurant", "catering"], "Travel Meals"),
    (["marketing", "advertis", "ads", "campaign"], "Marketing & Advertising"),
    (["accounting", "audit", "cpa", "tax"], "Accounting & Tax Fees"),
    (["legal", "attorney", "law"], "Legal Fees"),
    (["office", "supplies", "equipment", "toner"], "Office Supplies & Small Equipment"),
    (["rent", "lease"], "Rent"),
]


def map_gl(vendor, description=""):
    hay = f"{vendor} {description}".lower()
    for kws, acct in GL_RULES:
        if any(k in hay for k in kws):
            return acct
    return "Uncategorized Expense"


with tab_sim:
    st.subheader("Run an invoice through the controls")
    st.caption(
        "Change the inputs and watch the engine decide — this is the exact control logic "
        "from the workflow, running live in Python (no API, no AI)."
    )

    col_in, col_out = st.columns([1, 1])
    with col_in:
        vendor_choice = st.selectbox(
            "Vendor", KNOWN_VENDORS + ["(a vendor not on the approved list)"]
        )
        vendor_known = vendor_choice in KNOWN_VENDORS
        vendor_name = vendor_choice if vendor_known else "Unknown Vendor Co"
        amount = st.number_input("Invoice total ($)", min_value=0.0, value=850.0, step=50.0)
        inv_date = st.date_input("Invoice date", value=date(2026, 2, 20))
        footing_ok = st.toggle("Line items + tax tie to the stated total", value=True)
        is_duplicate = st.toggle("Same invoice already in the register (duplicate)", value=False)
        service_prior_month = st.toggle("Service period is in an earlier month (accrual)", value=False)

    status, blocking, notes = run_controls(
        vendor_known, amount, inv_date, footing_ok, is_duplicate, service_prior_month
    )

    with col_out:
        color = STATUS_COLORS[status]
        st.markdown(
            f"<div style='padding:18px;border-radius:10px;background:{color}22;"
            f"border:1px solid {color}'><span style='font-size:13px;color:#555'>RESULT</span><br>"
            f"<span style='font-size:30px;font-weight:700;color:{color}'>{status}</span></div>",
            unsafe_allow_html=True,
        )
        st.write("")
        if status == "READY":
            st.success(
                f"✅ Posts a bill to QuickBooks automatically, coded to "
                f"**{map_gl(vendor_name)}**."
            )
        else:
            st.warning("⛔ Routed to a human for review — no bill is created.")

        if blocking:
            st.markdown("**Blocking issues:**")
            for b in blocking:
                st.markdown(f"- 🔴 {b}")
        if notes:
            st.markdown("**Flags / notes:**")
            for n in notes:
                st.markdown(f"- 🟠 {n}")
        if not blocking and not notes:
            st.markdown("Clean on every control.")

    st.caption(
        f"Thresholds: approval limit **${APPROVAL_LIMIT:,}**, stale after **{MAX_AGE_DAYS} days**, "
        f"processing date **{AS_OF:%d %b %Y}**."
    )

# --------------------------------------------------------------------------- #
# Tab: How it works
# --------------------------------------------------------------------------- #
with tab_how:
    st.subheader("The pipeline")
    st.graphviz_chart(
        """
        digraph {
          rankdir=LR;
          node [shape=box, style="rounded,filled", fillcolor="#f5f5f5", fontname="Helvetica", fontsize=10];
          email [label="Invoice email"];
          intake [label="Normalise intake"];
          extract [label="Extract + AI read"];
          checks [label="Arithmetic checks"];
          controls [label="Controls", fillcolor="#e8f0fe"];
          reg [label="Register"];
          sw [label="Route by status", shape=diamond, fillcolor="#fff3cd"];
          bill [label="Post QBO bill", fillcolor="#d4edda"];
          mail [label="Review email", fillcolor="#f8d7da"];
          audit [label="Audit log", fillcolor="#e8f0fe"];
          email -> intake -> extract -> checks -> controls -> reg -> sw;
          sw -> bill [label="READY"];
          sw -> mail [label="else"];
          bill -> audit;
          mail -> audit;
        }
        """
    )

    st.subheader("The controls")
    st.table(
        pd.DataFrame(
            {
                "Control": [
                    "Vendor match", "Exact duplicate", "Possible duplicate", "Footing",
                    "Data quality", "Date sanity", "Service-period / accrual",
                    "Capitalisation", "Approval limit",
                ],
                "Catches": [
                    "Vendor not on the approved QuickBooks list",
                    "Same vendor + invoice number already processed (double-payment)",
                    "Same vendor + amount, different number, within a window",
                    "Line items + tax don't tie to the stated total",
                    "Missing/invalid invoice number, date, or line items",
                    "Future-dated (blocked) or stale beyond the age limit",
                    "Service in an earlier month → cut-off / accrual review",
                    f"Asset-like spend over ${CAPEX_MIN:,} → capitalise-vs-expense review",
                    f"Total over ${APPROVAL_LIMIT:,} → routed for sign-off",
                ],
            }
        )
    )

    st.subheader("Design rules")
    st.markdown(
        "- **AI proposes, rules constrain, humans approve** — no AI step posts to the ledger.\n"
        "- **Flag, never fix** — problems are recorded, never silently corrected.\n"
        "- **Every write is idempotent and logged** — checked by natural key, appended to an audit log.\n"
        "- **Synthetic data only; no secrets in Git.**"
    )
    st.markdown(
        "[Full build & operations guide ↗](https://github.com/sadia-yusuf/novatech-ap-automation/blob/main/docs/build-and-operations-guide.md)"
    )
