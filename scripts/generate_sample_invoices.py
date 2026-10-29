"""Project 6 - generate the 18 sample vendor-invoice PDFs and the answer key.

Synthetic data only. Deterministic: no randomness, PDF metadata pinned (invariant=1), so re-running
produces identical files. Needs reportlab (pip install -e ".[ap-demo]").

    python novatech/ap-automation/generate_sample_invoices.py
"""
from __future__ import annotations

import csv
import datetime as dt
from decimal import Decimal as D
from pathlib import Path

from reportlab.lib.colors import Color, HexColor, black, white
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

HERE = Path(__file__).resolve().parent
OUT = HERE / "sample_invoices"
VENDORS_CSV = HERE.parent / "data" / "vendors.csv"

BILL_TO = ["NovaTech Consulting LLC", "400 Delaware Avenue, Suite 210", "Wilmington, DE 19801"]
APPROVAL_THRESHOLD = D("2500.00")
CENTS = D("0.01")

# Fictional remit-to details (names come from vendors.csv; addresses are invented).
ADDR = {
    "Comcast Business": ["Business Services Billing", "PO Box 4417", "Philadelphia, PA 19101"],
    "Hartwell & Price LLP": ["Attorneys at Law", "88 Chestnut Row, Floor 12", "Wilmington, DE 19899"],
    "Keller Rowe CPAs": ["Certified Public Accountants", "2150 Market Square, Suite 600", "Philadelphia, PA 19103"],
    "CoreTech Hardware Supply": ["1700 Industrial Parkway", "Newark, NJ 07105"],
    "OfficeMart Supply": ["Remittance Dept", "900 Commerce Drive", "Columbus, OH 43215"],
    "HubSpot": ["Accounts Receivable", "25 First Street", "Cambridge, MA 02141"],
    "Google Workspace": ["Billing Operations", "1600 Amphitheatre Pkwy", "Mountain View, CA 94043"],
    "Slack Technologies": ["Billing Team", "500 Howard Street", "San Francisco, CA 94105"],
    "Amazon Web Services": ["AWS Billing", "410 Terry Ave North", "Seattle, WA 98109"],
    "Gusto": ["Accounts Receivable", "525 20th Street", "San Francisco, CA 94107"],
    "Skyward Travel Partners": ["Skyward Travel Partners", "310 Harbor Blvd", "Boston, MA 02110"],
    "Delaware Division of Corporations": ["Division of Corporations", "401 Federal Street, Suite 4", "Dover, DE 19901"],
    "Mateo Alvarez Dev LLC": ["Mateo Alvarez Dev LLC", "47 Larkspur Lane", "Austin, TX 78704"],
    "Brightline Data Services LLC": ["Brightline Data Services LLC", "3300 Quarry Road, Unit 5", "Raleigh, NC 27609"],
}

FIELDS = ["file", "scenario", "vendor", "invoice_no", "invoice_date", "due_date", "total", "gl_account",
          "gl_account_name", "expected_outcome", "control_expected_to_catch", "notes"]


def money(x: D) -> str:
    return f"{x:,.2f}"


def load_vendors() -> dict[str, dict]:
    with VENDORS_CSV.open(newline="", encoding="utf-8") as f:
        return {r["name"]: r for r in csv.DictReader(f)}


# --- invoice model -----------------------------------------------------------------------------------
def L(desc: str, qty: str, rate: str) -> dict:
    q, r = D(qty), D(rate)
    return {"desc": desc, "qty": q, "rate": r, "amount": (q * r).quantize(CENTS)}


def F(desc: str, amount: str) -> dict:
    return {"desc": desc, "qty": None, "rate": None, "amount": D(amount)}


def inv(key, vendor, no, date, lines, style, *, qty_hdr="Qty", rate_hdr="Unit price", total=None, extra=None):
    lines_sum = sum((x["amount"] for x in lines), D("0"))
    return {"key": key, "vendor": vendor, "no": no, "date": dt.date.fromisoformat(date), "lines": lines,
            "lines_sum": lines_sum, "total": D(total) if total else lines_sum, "style": style,
            "qty_hdr": qty_hdr, "rate_hdr": rate_hdr, "extra": extra or {}}


def build() -> list[dict]:
    comcast = inv("comcast_business", "Comcast Business", "CB-8841-0226", "2026-02-03", [
        F("Business Internet 500/100 Mbps - Feb 2026", "399.00"), F("Static IP block (/29)", "25.00"),
        F("Equipment rental - gateway", "18.50"), F("Regulatory recovery fee", "7.49")], "classic")
    slack = inv("slack_technologies", "Slack Technologies", "SLK-INV-4471920", "2026-02-04", [
        L("Slack Pro - active members (Feb 2026)", "12", "15.00"),
        L("Slack Pro - added members, prorated", "2", "15.00")], "band", qty_hdr="Seats", rate_hdr="Rate")
    hubspot = inv("hubspot", "HubSpot", "HS-INV-20260209-77", "2026-02-09", [
        L("Sales Hub Professional - seats, monthly", "2", "360.00"), F("Onboarding add-on", "80.00")],
        "band2", qty_hdr="Seats", rate_hdr="Price")
    officemart = inv("officemart_supply", "OfficeMart Supply", "OM-0226-33017", "2026-02-17", [
        L("Copy paper, 10-ream case", "4", "38.50"), L("Toner cartridge, black", "2", "96.25"),
        L("Desk organizer set", "6", "14.75"), F("Shipping & handling", "12.00")], "sidebar")
    return [
        comcast,
        inv("hartwell_price", "Hartwell & Price LLP", "HP-2026-0214", "2026-02-10", [
            L("Review of customer master services agreement (partner)", "3.50", "425.00"),
            L("Amendment to LLC operating agreement (partner)", "1.25", "425.00"),
            L("Document preparation (paralegal)", "2.00", "185.00"),
            F("Filing disbursement - Delaware", "75.00")], "serif", qty_hdr="Hours", rate_hdr="Rate"),
        inv("keller_rowe_cpas", "Keller Rowe CPAs", "KR-26-0107", "2026-02-12", [
            F("Q4 2025 estimated-tax review and bookkeeping tie-out (fixed fee)", "1800.00"),
            F("Multi-state nexus memorandum", "350.00")], "serif2"),
        inv("coretech_hardware", "CoreTech Hardware Supply", "CT-INV-558210", "2026-02-05", [
            L("Business laptop 14in, 32GB / 1TB", "1", "1349.00"), L("USB-C docking station", "1", "189.00"),
            F("Freight", "24.50")], "mono", extra={"cap_note": "laptop line is capitalisable"}),
        officemart,
        hubspot,
        inv("google_workspace", "Google Workspace", "GW-5530021947", "2026-02-02", [
            L("Business Standard - users (Feb 2026)", "12", "14.40"), L("Vault add-on - users", "8", "5.00"),
            L("Additional storage 2 TB - pooled", "2", "43.60")], "minimal", qty_hdr="Units", rate_hdr="Rate"),
        slack,
        inv("amazon_web_services", "Amazon Web Services", "AWS-INV-2026-02-4417821", "2026-02-03", [
            F("Amazon EC2 - compute", "1158.56"), F("Amazon RDS - database", "438.15"),
            F("Amazon S3 - storage", "96.72"), F("Data transfer out", "211.38"),
            F("Amazon CloudWatch", "41.35")], "statement"),
        inv("gusto", "Gusto", "GST-0226-10-88231", "2026-02-02", [
            F("Platform base fee", "80.00"), L("Per-employee fee", "8", "12.00"),
            L("Per-contractor fee", "1", "6.00")], "classic2", qty_hdr="Qty", rate_hdr="Rate"),
        inv("skyward_travel", "Skyward Travel Partners", "SKY-TR-20260218-0391", "2026-02-18", [
            F("Airfare ORD-BOS round trip", "342.60"), L("Hotel - Boston (nights)", "2", "189.00"),
            F("Booking fee", "25.00")], "receipt"),
        inv("delaware_division_of_corporations", "Delaware Division of Corporations", "DE-DOC-2026-0225-1180",
            "2026-02-24", [F("Certified copy of certificate of formation", "50.00"),
                           F("24-hour expedited service", "100.00"), F("Certificate of good standing", "50.00")],
            "minimal2"),
        # --- exceptions ---
        {**comcast, "key": "comcast_business_resend"},                      # 13 exact duplicate
        {**slack, "key": "slack_technologies_resend"},                      # 14 exact duplicate
        inv("hubspot_second", "HubSpot", "HS-INV-20260223-91", "2026-02-23", hubspot["lines"], "band2",
            qty_hdr="Seats", rate_hdr="Price"),                              # 15 same amount, new number
        inv("officemart_supply_b", "OfficeMart Supply", "OM-0226-33902", "2026-02-20", [
            L("Mobile whiteboard 36x24in", "1", "119.00"), L("Label printer tape", "5", "22.35"),
            L("3-ring binders, 2in", "10", "13.10")], "sidebar", total="391.75"),  # 16 lines != total
        inv("brightline_data_services", "Brightline Data Services LLC", "BDS-2291", "2026-02-19", [
            F("Data enrichment subscription - Feb 2026", "1250.00"), F("One-time setup", "150.00")], "minimal2"),
        inv("mateo_alvarez_dev", "Mateo Alvarez Dev LLC", "MAD-2026-02", "2026-02-26", [
            L("Platform integration development", "100", "80.00"), L("QA and production support", "40", "80.00")],
            "plain", qty_hdr="Hours", rate_hdr="Rate"),                       # 18 needs approval
    ]


# --- drawing helpers ---------------------------------------------------------------------------------
def fmt_date(d: dt.date, kind: str) -> str:
    return {"long": f"{d:%B} {d.day}, {d.year}", "iso": d.isoformat(), "us": f"{d:%m/%d/%Y}",
            "dmy": f"{d.day} {d:%B %Y}", "mon": f"{d:%d-%b-%Y}"}[kind]


def text(c, x, y, s, font="Helvetica", size=10, color=black, align="l", max_w=None):
    if max_w is not None:
        assert stringWidth(s, font, size) <= max_w, f"text too wide: {s!r}"
    c.setFont(font, size)
    c.setFillColor(color)
    {"l": c.drawString, "r": c.drawRightString, "c": c.drawCentredString}[align](x, y, s)


def block(c, x, y, lines, font="Helvetica", size=9.5, lead=13, color=black, align="l"):
    for s in lines:
        text(c, x, y, s, font, size, color, align)
        y -= lead
    return y


def has_qty(i):
    return any(x["qty"] is not None for x in i["lines"])


def line_table(c, i, x, y, w, *, font, bold, size=9.5, grid=False, head_fill=None, head_color=black,
               zebra=None, rule=True, row_h=18, dec_qty=None):
    """Draw the line-item table; returns y below the last row."""
    qty = has_qty(i)
    cols = [("Description", 0.0, "l")]
    if qty:
        cols += [(i["qty_hdr"], 0.62, "r"), (i["rate_hdr"], 0.78, "r")]
    cols += [("Amount", 1.0, "r")]
    pad = 6
    if head_fill is not None:
        c.setFillColor(head_fill)
        c.rect(x, y - row_h + 5, w, row_h, stroke=0, fill=1)
    ty = y - row_h + 10
    for name, frac, al in cols:
        text(c, x + pad if al == "l" else x + w * frac - pad, ty, name, bold, size, head_color, al)
    y -= row_h
    top = y + row_h + 5
    desc_w = w * (0.60 if qty else 0.75)
    for n, ln in enumerate(i["lines"]):
        if zebra is not None and n % 2 == 1:
            c.setFillColor(zebra)
            c.rect(x, y - row_h + 5, w, row_h, stroke=0, fill=1)
        ty = y - row_h + 10
        text(c, x + pad, ty, ln["desc"], font, size, max_w=desc_w - pad)
        if qty and ln["qty"] is not None:
            q = ln["qty"]
            text(c, x + w * 0.62 - pad, ty, f"{q:,.2f}".rstrip("0").rstrip(".") if q % 1 else f"{int(q)}", font, size, align="r")
            text(c, x + w * 0.78 - pad, ty, money(ln["rate"]), font, size, align="r")
        text(c, x + w - pad, ty, money(ln["amount"]), font, size, align="r")
        y -= row_h
        if rule and not grid:
            c.setStrokeColor(HexColor("#BBBBBB"))
            c.setLineWidth(0.4)
            c.line(x, y + 5, x + w, y + 5)
    if grid:
        c.setStrokeColor(black)
        c.setLineWidth(0.7)
        c.rect(x, y + 5, w, top - (y + 5), stroke=1, fill=0)
        c.line(x, top - row_h, x + w, top - row_h)
        for _, frac, al in cols[1:]:
            xv = x + w * (frac - (0.16 if frac < 1 else 0.14))
            c.line(xv, y + 5, xv, top)
    return y


def meta_pairs(i, labels, kind):
    due = i["due"]
    return [(labels[0], i["no"]), (labels[1], fmt_date(i["date"], kind)), (labels[2], fmt_date(due, kind))]


def footer(c, i, w, font="Helvetica", size=8, y=40, x=None):
    terms = i["terms"]
    s = f"{terms}. Please quote {i['no']} with payment." if terms != "Due on receipt" else \
        f"Due on receipt. Please quote {i['no']} with payment."
    text(c, x if x is not None else 54, y, s, font, size, HexColor("#555555"))


# --- layouts -----------------------------------------------------------------------------------------
def classic(c, i, st):
    W, H = 612, 792
    col = HexColor(st.get("color", "#0B3D91"))
    text(c, 54, H - 70, i["vendor"], "Helvetica-Bold", 20, col)
    block(c, 54, H - 88, ADDR[i["vendor"]], size=9, lead=11)
    text(c, W - 54, H - 70, "INVOICE", "Helvetica-Bold", 22, align="r")
    y = H - 96
    for lab, val in meta_pairs(i, st["labels"], st["date"]):
        text(c, W - 160, y, lab, "Helvetica-Bold", 9, align="r")
        text(c, W - 54, y, val, "Helvetica", 9, align="r")
        y -= 13
    text(c, 54, H - 170, "BILL TO", "Helvetica-Bold", 9, col)
    block(c, 54, H - 183, BILL_TO)
    y = line_table(c, i, 54, H - 250, W - 108, font="Helvetica", bold="Helvetica-Bold", grid=True, head_fill=HexColor("#E8EEF8"))
    total_box(c, i, W - 54, y - 14, "Helvetica", "Helvetica-Bold", "TOTAL DUE")
    footer(c, i, W)


def total_box(c, i, xr, y, font, bold, label, boxed=True, size=11):
    if boxed:
        c.setStrokeColor(black)
        c.setLineWidth(1)
        c.rect(xr - 190, y - 8, 190, 24, stroke=1, fill=0)
    text(c, xr - 180, y, label, bold, size)
    text(c, xr - 8, y, "$" + money(i["total"]), bold, size, align="r")


def serif(c, i, st):
    W, H = 612, 792
    text(c, W / 2, H - 62, i["vendor"], "Times-Bold", 22, align="c")
    block(c, W / 2, H - 80, ADDR[i["vendor"]], "Times-Roman", 10, 12, align="c")
    c.setLineWidth(1.5)
    c.line(54, H - 118, W - 54, H - 118)
    text(c, 54, H - 145, "Invoice", "Times-Italic", 16)
    y = H - 165
    for lab, val in meta_pairs(i, st["labels"], st["date"]):
        text(c, 54, y, lab + ":", "Times-Bold", 10.5)
        text(c, 150, y, val, "Times-Roman", 10.5)
        y -= 14
    text(c, 340, H - 165, "Client:", "Times-Bold", 10.5)
    block(c, 340, H - 179, BILL_TO, "Times-Roman", 10.5, 13)
    y = line_table(c, i, 54, H - 260, W - 108, font="Times-Roman", bold="Times-Bold", size=10.5, rule=True)
    c.setLineWidth(0.8)
    c.line(W - 250, y + 2, W - 54, y + 2)
    text(c, W - 240, y - 14, "Total due", "Times-Bold", 12)
    text(c, W - 60, y - 14, "$" + money(i["total"]), "Times-Bold", 12, align="r")
    c.line(W - 250, y - 20, W - 54, y - 20)
    c.line(W - 250, y - 23, W - 54, y - 23)
    footer(c, i, W, "Times-Italic", 9)


def serif2(c, i, st):
    W, H = 612, 792
    text(c, 54, H - 64, i["vendor"], "Times-Bold", 20)
    block(c, 54, H - 80, ADDR[i["vendor"]], "Times-Roman", 9.5, 11.5)
    text(c, W - 54, H - 64, "STATEMENT OF FEES", "Times-Bold", 13, align="r")
    y = H - 82
    for lab, val in meta_pairs(i, st["labels"], st["date"]):
        text(c, W - 54, y, f"{lab} {val}", "Times-Roman", 10, align="r")
        y -= 13
    text(c, 54, H - 160, "Prepared for", "Times-Italic", 10)
    block(c, 54, H - 174, BILL_TO, "Times-Bold", 10.5, 13)
    y = line_table(c, i, 54, H - 250, W - 108, font="Times-Roman", bold="Times-Bold", size=10.5,
                   head_fill=HexColor("#EFEBE0"), rule=False)
    text(c, W - 54, y - 14, "Balance due  $" + money(i["total"]), "Times-Bold", 13, align="r")
    footer(c, i, W, "Times-Italic", 9)


def band(c, i, st):
    W, H = 612, 792
    col = HexColor(st.get("color", "#E8590C"))
    c.setFillColor(col)
    c.rect(0, H - 90, W, 90, stroke=0, fill=1)
    text(c, 40, H - 56, i["vendor"], "Helvetica-Bold", 24, white)
    text(c, W - 40, H - 56, "INVOICE", "Helvetica", 18, white, align="r")
    y = H - 118
    for lab, val in meta_pairs(i, st["labels"], st["date"]):
        text(c, W - 40, y, f"{lab}: {val}", "Helvetica", 9.5, align="r")
        y -= 13
    block(c, 40, H - 118, ["Billed to"], "Helvetica-Bold", 9, color=col)
    block(c, 40, H - 131, BILL_TO)
    block(c, 40, H - 180, ["From"], "Helvetica-Bold", 9, color=col)
    block(c, 40, H - 193, ADDR[i["vendor"]], size=9, lead=11)
    y = line_table(c, i, 40, H - 260, W - 80, font="Helvetica", bold="Helvetica-Bold", head_fill=col, head_color=white,
                   zebra=HexColor("#F4F4F4"), rule=False)
    c.setFillColor(col)
    c.rect(W - 230, y - 28, 190, 26, stroke=0, fill=1)
    text(c, W - 220, y - 20, "Amount due (USD)", "Helvetica-Bold", 9, white)
    text(c, W - 48, y - 20, "$" + money(i["total"]), "Helvetica-Bold", 12, white, align="r")
    footer(c, i, W, "Helvetica", 8, 40, 40)


def sidebar(c, i, st):
    W, H = 612, 792
    col = HexColor(st.get("color", "#1B5E4B"))
    c.setFillColor(col)
    c.rect(0, 0, 170, H, stroke=0, fill=1)
    text(c, 18, H - 60, i["vendor"].replace(" ", "\n").split("\n")[0].upper(), "Helvetica-Bold", 16, white)
    text(c, 18, H - 78, " ".join(i["vendor"].split()[1:]).upper(), "Helvetica-Bold", 16, white)
    block(c, 18, H - 100, ADDR[i["vendor"]], size=8, lead=10.5, color=white)
    y = H - 200
    for lab, val in meta_pairs(i, st["labels"], st["date"]):
        text(c, 18, y, lab.upper(), "Helvetica-Bold", 7.5, HexColor("#BFE3D6"))
        text(c, 18, y - 12, val, "Helvetica", 9, white, max_w=140)
        y -= 34
    text(c, 195, H - 60, "Invoice", "Helvetica-Bold", 26, col)
    text(c, 195, H - 95, "Ship / bill to", "Helvetica-Bold", 9, col)
    block(c, 195, H - 108, BILL_TO)
    y = line_table(c, i, 195, H - 190, W - 195 - 40, font="Helvetica", bold="Helvetica-Bold", size=9, rule=True)
    text(c, W - 48, y - 16, "Total  $" + money(i["total"]), "Helvetica-Bold", 13, col, align="r")
    footer(c, i, W, "Helvetica", 8, 40, 195)


def mono(c, i, st):
    W, H = 612, 792
    f = "Courier"
    y = H - 60
    text(c, 54, y, i["vendor"].upper(), "Courier-Bold", 14)
    y = block(c, 54, y - 14, ADDR[i["vendor"]], f, 9, 11)
    y -= 6
    text(c, 54, y, "=" * 72, f, 9)
    y -= 14
    for lab, val in meta_pairs(i, st["labels"], st["date"]):
        text(c, 54, y, f"{lab:<14}{val}", f, 10)
        y -= 13
    y -= 4
    text(c, 54, y, "SOLD TO: " + BILL_TO[0], f, 10)
    y = block(c, 54, y - 13, ["         " + s for s in BILL_TO[1:]], f, 10, 13)
    y -= 6
    text(c, 54, y, "-" * 72, f, 9)
    y -= 13
    text(c, 54, y, f"{'ITEM':<38}{'QTY':>5}{'UNIT':>12}{'EXT':>13}", "Courier-Bold", 9)
    y -= 12
    for ln in i["lines"]:
        q = "" if ln["qty"] is None else str(int(ln["qty"]))
        u = "" if ln["rate"] is None else money(ln["rate"])
        text(c, 54, y, f"{ln['desc'][:37]:<38}{q:>5}{u:>12}{money(ln['amount']):>13}", f, 9)
        y -= 13
    text(c, 54, y, "-" * 72, f, 9)
    y -= 15
    text(c, 54, y, f"{'TOTAL USD':<55}{money(i['total']):>16}", "Courier-Bold", 11)
    text(c, 54, 50, i["terms"].upper() + " - THANK YOU FOR YOUR BUSINESS", f, 8)


def receipt(c, i, st):
    W, H = c._pagesize
    x = W / 2
    text(c, x, H - 40, i["vendor"].upper(), "Helvetica-Bold", 13, align="c")
    block(c, x, H - 55, ADDR[i["vendor"]], size=8, lead=10, align="c")
    text(c, x, H - 100, "TRAVEL INVOICE / RECEIPT", "Helvetica-Bold", 9, align="c")
    y = H - 120
    for lab, val in meta_pairs(i, st["labels"], st["date"]):
        text(c, 20, y, lab, "Helvetica", 8)
        text(c, W - 20, y, val, "Helvetica-Bold", 8, align="r")
        y -= 12
    text(c, 20, y, "Traveller / account", "Helvetica", 8)
    text(c, W - 20, y, "NovaTech Consulting LLC", "Helvetica-Bold", 8, align="r")
    y -= 14
    c.setDash(2, 2)
    c.line(20, y, W - 20, y)
    c.setDash()
    y -= 14
    for ln in i["lines"]:
        if ln["qty"] is not None:
            text(c, 20, y, f"{ln['desc']} x{int(ln['qty'])}", "Helvetica", 8.5, max_w=180)
        else:
            text(c, 20, y, ln["desc"], "Helvetica", 8.5, max_w=180)
        text(c, W - 20, y, money(ln["amount"]), "Helvetica", 8.5, align="r")
        y -= 13
    c.setDash(2, 2)
    c.line(20, y, W - 20, y)
    c.setDash()
    y -= 16
    text(c, 20, y, "TOTAL (USD)", "Helvetica-Bold", 11)
    text(c, W - 20, y, money(i["total"]), "Helvetica-Bold", 11, align="r")
    text(c, x, y - 28, "Charged to corporate card on file", "Helvetica-Oblique", 7.5, align="c")


def statement(c, i, st):
    W, H = 612, 792
    col = HexColor("#232F3E")
    text(c, 48, H - 60, "amazon web services", "Helvetica-Bold", 18, col)
    text(c, 48, H - 76, "Invoice for usage and services", "Helvetica", 9, HexColor("#555555"))
    # summary box
    c.setStrokeColor(col)
    c.rect(W - 270, H - 130, 222, 80, stroke=1, fill=0)
    rows = [("Invoice Number:", i["no"]), ("Invoice Date:", fmt_date(i["date"], st["date"])),
            ("Billing period:", "Jan 1 - Jan 31, 2026"), ("Account ID:", "7421-0098-3316")]
    y = H - 66
    for a, b in rows:
        text(c, W - 262, y, a, "Helvetica-Bold", 8.5)
        text(c, W - 56, y, b, "Helvetica", 8.5, align="r", max_w=130)
        y -= 16
    text(c, 48, H - 120, "Bill to address", "Helvetica-Bold", 9)
    block(c, 48, H - 133, BILL_TO, size=9, lead=11)
    block(c, 48, H - 175, ["Remit to:"] + ADDR[i["vendor"]], size=8.5, lead=10.5)
    text(c, 48, H - 235, "Charges by service", "Helvetica-Bold", 12, col)
    c.setFillColor(col)
    c.rect(48, H - 262, W - 96, 18, stroke=0, fill=1)
    text(c, 56, H - 257, "Service", "Helvetica-Bold", 9, white)
    text(c, W - 56, H - 257, "Charges (USD)", "Helvetica-Bold", 9, white, align="r")
    y = H - 280
    for ln in i["lines"]:
        text(c, 56, y, ln["desc"], "Helvetica", 9.5)
        text(c, W - 56, y, money(ln["amount"]), "Helvetica", 9.5, align="r")
        y -= 17
    c.line(48, y + 8, W - 48, y + 8)
    text(c, 56, y - 8, "Total pre-tax charges", "Helvetica", 9.5)
    text(c, W - 56, y - 8, money(i["total"]), "Helvetica", 9.5, align="r")
    text(c, 56, y - 24, "Estimated tax collected", "Helvetica", 9.5)
    text(c, W - 56, y - 24, "0.00", "Helvetica", 9.5, align="r")
    text(c, 56, y - 46, "TOTAL AMOUNT DUE", "Helvetica-Bold", 12, col)
    text(c, W - 56, y - 46, "$" + money(i["total"]), "Helvetica-Bold", 12, col, align="r")


def minimal(c, i, st):
    W, H = 612, 792
    f, b = "Helvetica-Oblique", "Helvetica-Bold"
    text(c, 72, H - 80, i["vendor"], b, 15)
    block(c, 72, H - 96, ADDR[i["vendor"]], f, 8.5, 10.5, color=HexColor("#444444"))
    text(c, 72, H - 150, "Invoice", "Helvetica", 11, HexColor("#888888"))
    y = H - 170
    for lab, val in meta_pairs(i, st["labels"], st["date"]):
        text(c, 72, y, lab, f, 9.5)
        text(c, 190, y, val, "Helvetica", 9.5)
        y -= 14
    text(c, 72, y - 6, "Customer", f, 9.5)
    block(c, 190, y - 6, BILL_TO, "Helvetica", 9.5, 12)
    y = line_table(c, i, 72, y - 70, W - 144, font="Helvetica", bold=b, size=9.5, rule=False)
    text(c, W - 78, y - 18, "Total payable " + "USD " + money(i["total"]), b, 11, align="r")
    footer(c, i, W, f, 8, 60, 72)


def plain(c, i, st):
    W, H = 612, 792
    text(c, 60, H - 70, i["vendor"], "Helvetica-Bold", 17)
    block(c, 60, H - 86, ADDR[i["vendor"]][1:], size=9, lead=11)
    text(c, 60, H - 125, "INVOICE", "Helvetica-Bold", 12)
    y = H - 142
    for lab, val in meta_pairs(i, st["labels"], st["date"]):
        text(c, 60, y, lab, "Helvetica", 10)
        text(c, 150, y, val, "Helvetica-Bold", 10)
        y -= 14
    text(c, 340, H - 125, "TO", "Helvetica-Bold", 10)
    block(c, 340, H - 140, BILL_TO)
    text(c, 60, y - 14, "Contract services - February 2026 sprint (SOW 2026-02)", "Helvetica-Oblique", 9.5)
    y = line_table(c, i, 60, y - 30, W - 120, font="Helvetica", bold="Helvetica-Bold", grid=False, head_fill=HexColor("#DDDDDD"))
    text(c, W - 66, y - 18, "Please remit:  $" + money(i["total"]), "Helvetica-Bold", 13, align="r")
    footer(c, i, W, "Helvetica", 8, 50, 60)


LAYOUT = {"classic": classic, "classic2": classic, "serif": serif, "serif2": serif2, "band": band, "band2": band,
          "sidebar": sidebar, "mono": mono, "receipt": receipt, "statement": statement, "minimal": minimal,
          "minimal2": minimal, "plain": plain}
STYLE = {   # per-style label sets / date formats / accent colours
    "classic": dict(labels=("Invoice #", "Invoice date", "Due date"), date="long", color="#0B3D91"),
    "classic2": dict(labels=("Inv No.", "Date", "Pay by"), date="us", color="#E4572E"),
    "serif": dict(labels=("Invoice No", "Date", "Due"), date="dmy"),
    "serif2": dict(labels=("Reference", "Issued", "Payable by"), date="long"),
    "band": dict(labels=("Invoice", "Date", "Due"), date="long", color="#4A154B"),
    "band2": dict(labels=("Invoice number", "Invoice date", "Due date"), date="mon", color="#E8590C"),
    "sidebar": dict(labels=("Invoice no.", "Date", "Due"), date="us", color="#1B5E4B"),
    "mono": dict(labels=("INVOICE NO", "DATE", "DUE"), date="iso"),
    "receipt": dict(labels=("Doc no.", "Date", "Due"), date="mon"),
    "statement": dict(labels=("", "", ""), date="long"),
    "minimal": dict(labels=("Document No.", "Issued", "Due"), date="long"),
    "minimal2": dict(labels=("Invoice ref", "Date", "Due"), date="iso"),
    "plain": dict(labels=("Invoice #", "Date", "Due date"), date="long"),
}


def render(i: dict, path: Path) -> None:
    size = (320, 560) if i["style"] == "receipt" else (612, 792)
    c = Canvas(str(path), pagesize=size, invariant=1)
    c.setTitle(f"Invoice {i['no']}")
    c.setAuthor(i["vendor"])
    LAYOUT[i["style"]](c, i, STYLE[i["style"]])
    c.showPage()
    c.save()


# --- answer key --------------------------------------------------------------------------------------
def expected_row(n: int, i: dict, vendors: dict, firsts: dict) -> dict:
    v = vendors.get(i["vendor"])
    row = {"file": i["file"], "vendor": i["vendor"], "invoice_no": i["no"], "invoice_date": i["date"].isoformat(),
           "total": money(i["total"]).replace(",", ""),
           "gl_account": v["default_account"] if v else "", "gl_account_name": v["default_account_name"] if v else ""}
    days = int(v["terms_days"]) if v else 30
    i["terms"] = v["terms"] if v else "Net 30"
    i["due"] = i["date"] + dt.timedelta(days=days)
    row["due_date"] = i["due"].isoformat()
    key = (i["vendor"], i["no"])
    notes = ""
    if i["key"].endswith("_resend"):
        orig = firsts[key]
        row.update(scenario="exact_duplicate", expected_outcome="reject_duplicate",
                   control_expected_to_catch="Duplicate check: vendor + invoice number already processed (idempotency key)")
        notes = f"Exact re-send of {orig}; must not create a second bill"
    elif i["key"] == "hubspot_second":
        row.update(scenario="same_amount_new_number", expected_outcome="hold_possible_duplicate",
                   control_expected_to_catch="Fuzzy duplicate check: same vendor + same amount within 30 days, different invoice number")
        notes = f"Same vendor and total as {firsts[('HubSpot', 'HS-INV-20260209-77')]}; reviewer decides (could be a genuine second charge)"
    elif i["lines_sum"] != i["total"]:
        row.update(scenario="lines_do_not_foot", expected_outcome="hold_total_mismatch",
                   control_expected_to_catch="Arithmetic check: sum of line items must equal invoice total")
        notes = f"Line items sum to {money(i['lines_sum']).replace(',', '')} but stated total is {row['total']}"
    elif not v:
        row.update(scenario="unknown_vendor", expected_outcome="hold_unknown_vendor",
                   control_expected_to_catch="Vendor master match: vendor not in vendors.csv / QBO; never auto-create vendors")
        notes = "No default GL account; a human onboards the vendor and chooses the account (AI may only suggest)"
    elif i["total"] > APPROVAL_THRESHOLD:
        row.update(scenario="needs_approval", expected_outcome="hold_for_approval",
                   control_expected_to_catch="Approval threshold: bills above $2,500 need human approval before creation")
        notes = "Otherwise clean: known vendor, foots, not a duplicate"
    else:
        row.update(scenario="clean", expected_outcome="pass_to_draft_bill",
                   control_expected_to_catch="None - passes all controls")
        if i["key"] == "coretech_hardware":
            row.update(gl_account="1510; 6910",
                       gl_account_name="Computer Equipment; Office Supplies & Small Equipment",
                       expected_outcome="pass_to_draft_bill_capex_review",
                       control_expected_to_catch="Capex review: line over capitalisation threshold ($1,000)")
            notes = ("Split coding: laptop 1,349.00 + freight 24.50 = 1,373.50 -> 1510 Computer Equipment "
                     "(laptop line over the $1,000 capitalisation threshold; freight capitalised with the asset); "
                     "docking station 189.00 -> 6910 Office Supplies & Small Equipment (under threshold)")
        if i["vendor"] == "Amazon Web Services":
            row.update(expected_outcome="hold_service_period_review",
                       control_expected_to_catch="Cut-off check: service period (Jan 2026) before posting month; "
                                                 "duplicate check vs Jan Amex charge")
            notes = ("Hold: service period (Jan 2026) before posting month; possible duplicate of Jan Amex charge "
                     "1,946.16 (2026-01-03 AWS, already coded to 6310 via the Amex statement) - do not bill "
                     "without confirming the charge was not already booked")
    row["notes"] = notes
    firsts.setdefault(key, i["file"])
    return row


def main() -> None:
    vendors = load_vendors()
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("INV*.pdf"):
        old.unlink()
    invoices = build()
    assert len(invoices) == 18
    rows, firsts = [], {}
    for n, i in enumerate(invoices, 1):
        i["file"] = f"INV{n:02d}_{i['key']}.pdf"
        rows.append(expected_row(n, i, vendors, firsts))
        render(i, OUT / i["file"])
    with (OUT / "expected_results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} invoices + expected_results.csv to {OUT}")


if __name__ == "__main__":
    main()
