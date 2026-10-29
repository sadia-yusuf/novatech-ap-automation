# NovaTech AP Invoice Automation — End-to-End Build & Operations Guide

An accounts-payable (AP) automation built in n8n. A vendor invoice (PDF) arrives by email, the
system reads it, runs a set of accounting controls over it, and then either **posts a bill to
QuickBooks automatically** or **emails it for human review** — logging every step to an audit trail.

This guide covers the whole thing: setting up n8n, connecting each credential (especially
QuickBooks), the workflow node by node, every control, every exception you can hit, and how to test it.

---

## 1. The big picture (what happens, in order)

```
Invoice email arrives
      │
      ▼
[Gmail Trigger] ─► [Normalise intake] ─► [Extract from File] ─► [AI extraction]
                                                                       │
                                                                       ▼
                                                             [Arithmetic checks]
                                                                       │
                                                [QBO vendors] ─► [Read register] ─► [Controls]
                                                                       │
                                                             [Append to register]
                                                                       │
                                                           [Preserve Invoice Data]
                                                                       │
                                                                  [Switch] ── status?
                                                         ┌─────────────┴─────────────┐
                                                   READY │                           │ NEEDS_APPROVAL / HOLD / EXCEPTION
                                                         ▼                           ▼
                                               [Map GL account]            [Send Approval Email]
                                                         ▼                           │
                                               [Create QBO bill]                     │
                                                         └───────────┬───────────────┘
                                                                     ▼
                                                           [Append to audit log]
```

A separate **Error Trigger → Send Error Alert** path emails you if any run fails outright.

**The core idea:** everything flows through the same pipeline, but the **Controls** node assigns each
invoice a *status*, and the **Switch** routes it. Clean invoices post themselves; anything doubtful
goes to a human. Nothing is ever silently "fixed" — problems are recorded, not corrected.

---

## 2. Setting up n8n (account creation)

n8n is the automation platform the whole thing runs on. On a fresh self-hosted install:

1. Start n8n (e.g. `npx n8n`) and open **http://localhost:5678** in your browser.
2. On first launch it asks you to **create an owner account** — your email and a password.
   This account is **local to your machine only**; it is not an n8n Cloud login and nothing is sent
   to n8n's servers. It simply protects your editor.
3. You land in the **Workflows** area. This is where you'll import the AP workflow JSON
   (⋮ menu → *Import from File*).

Think of this account as the "key to your own n8n" — separate from the *credentials* below, which are
how n8n talks to QuickBooks, Gmail, Google, and OpenAI.

---

## 3. Credentials — connecting the outside services

The workflow needs four connections. Each is created once in n8n under **Credentials**, then selected
on the relevant nodes. For the OAuth ones (QuickBooks, Gmail, Sheets) the pattern is always the same:
*paste a Client ID + Secret → copy the redirect URL n8n shows you → register that URL with the
provider → click Connect and sign in.*

### 3a. QuickBooks (the important one)

This is an **OAuth2** connection to a QuickBooks **Sandbox** company (a free developer test company —
no paid QuickBooks subscription needed).

**On the Intuit Developer side** (developer.intuit.com):
1. You already have an app: **"NovaTech AP Automation"**. Open it.
2. Go to **Keys & credentials**. For sandbox work, use the **Development** keys. Copy the
   **Client ID** and **Client Secret**.
   - ⚠️ The **Client Secret** is sensitive — never paste it into a chat, screenshot, or code repo.
3. Note your sandbox **Company ID (realm ID)** — for NovaTech it's `YOUR_COMPANY_ID`
   (found under *Sandboxes* in the developer dashboard). The workflow doesn't need you to type this,
   but it's what identifies the company behind the connection.

**On the n8n side:**
4. Credentials → **New** → search **QuickBooks OAuth2 API**.
5. Set **Environment = Sandbox**.
6. Paste the **Client ID** and **Client Secret**.
7. n8n shows an **OAuth Redirect URL** (something like `https://<your-n8n>/rest/oauth2-credential/callback`).
   Copy it.
8. Back on Intuit → your app → **Keys & credentials → Redirect URIs** → **Add URI** → paste that URL →
   Save. (This is the step people forget; without it, sign-in fails.)
9. Back in n8n, click **Sign in with Intuit / Connect my account**, choose the sandbox company
   (**NovaTech Consulting LLC**), and authorise. The credential turns green.

> When you move n8n to a new address (e.g. self-hosted at localhost, then later a server), the redirect
> URL changes, so you repeat steps 7–9 with the new URL.

### 3b. Gmail (invoice intake + notifications)

An **OAuth2** connection used both to *receive* invoices (the Gmail Trigger) and to *send* review and
error emails.

1. In **Google Cloud Console**, create a project, enable the **Gmail API**, configure the **OAuth
   consent screen**, then create an **OAuth Client ID** (type: Web application). Copy its Client ID
   and Secret.
2. In n8n: Credentials → **Gmail OAuth2 API** → paste Client ID + Secret → copy the redirect URL.
3. In Google Cloud → your OAuth client → **Authorized redirect URIs** → add that URL → Save.
4. Back in n8n → **Connect** → sign in.
   - ⚠️ Connect the **dedicated AP demo account** (`ap-inbox@example.com`), **not** your personal
     Gmail. The demo account is the "AP inbox" invoices are sent to.

### 3c. Google Sheets (the register + audit log)

Same Google Cloud project as above. Enable the **Google Sheets API** and **Google Drive API**, then
create a **Google Sheets OAuth2 API** credential in n8n the same way (paste keys → redirect URL →
authorise). This lets the workflow read and append to the **"NovaTech AP – Invoice Register"**
spreadsheet, which has two tabs: **register** and **audit_log**.

### 3d. OpenAI (the AI extraction)

The simplest one — no OAuth. Get an **API key** from platform.openai.com, then in n8n create an
**OpenAI** credential and paste the key. This powers the model that reads the invoice text.

---

## 4. The workflow, node by node

### Intake
- **Gmail Trigger** — polls the AP inbox every minute for emails with PDF attachments
  (`has:attachment filename:pdf`) and downloads them. This is the live entry point.
- **On form submission** *(currently disabled)* — an alternative upload form for one-off PDFs. Kept
  as a second channel; turn it on if you want a manual upload option.
- **Normalise intake** — turns whatever arrived into a consistent shape: **one item per PDF**. A single
  email with five attachments becomes five invoices flowing through independently. It records the
  source (email vs form), sender, subject, and filename.

### Reading the invoice
- **Extract from File** — pulls the raw **text** out of the PDF.
- **AI extraction** — three nodes working together:
  - **OpenAI Chat Model** (`gpt-4o-mini`, temperature 0 for consistency)
  - **Basic LLM Chain** — sends the text with strict instructions: *extract only what's printed, never
    guess or calculate, dates as YYYY-MM-DD (read US MM/DD/YYYY), amounts as plain numbers, copy line
    items exactly, use the total as stated even if lines don't add up.*
  - **Structured Output Parser** — forces the result into a fixed schema (vendor, invoice number,
    dates, line items, totals, etc.) so downstream steps get predictable fields.
- **Code in JavaScript** — the first *rules* step (not AI). It cleans the figures and runs the
  **footing check**: do the line items + tax equal the stated total? It records any data-quality
  flags. Crucially, it **flags** problems but never alters the numbers.

### Gathering context for the controls
- **QBO vendors** — pulls the full **vendor master** from QuickBooks (your approved vendor list).
- **Read register** — reads the existing **register** sheet so the controls can check this invoice
  against everything processed before (for duplicates).

### The controls
- **Controls** — the heart of the system (detailed in §5). It compares each invoice against the vendor
  master and history, runs accounting checks, and stamps a **status**: `READY`, `NEEDS_APPROVAL`,
  `HOLD`, or `EXCEPTION`, plus an `exception_reason` and `review_notes`.

### Recording and routing
- **Append to register** — writes the fully-assessed invoice as a row in the **register** (this is the
  permanent record of *everything* that came through, whatever its status).
- **Preserve Invoice Data** — a checkpoint that carries the key fields forward cleanly so later nodes
  can reference them reliably no matter which branch they take.
- **Switch** — routes by status:
  - `READY` → **Map GL account → Create QBO bill**
  - `NEEDS_APPROVAL` / `HOLD` / `EXCEPTION` → **Send Approval Email**

### The two outcomes
- **Map GL account** — for READY invoices only: picks the right **expense account** from the chart of
  accounts based on the vendor and line descriptions (see §7). Defaults to *Uncategorized Expense* if
  it can't tell, so nothing is ever silently miscoded.
- **Create QBO bill** — posts the bill to QuickBooks: vendor, amount, description (the invoice number),
  due date, transaction date, coded to the mapped expense account. QuickBooks returns a **bill ID**.
- **Send Approval Email** — for everything else: emails you a formatted summary (invoice number,
  vendor, amount, date, status, and the reason it was flagged) so a human can decide.

### The audit trail
- **Append to audit log** — writes one row per invoice to the **audit_log** tab recording what
  *happened*: timestamp, invoice number, vendor, status, `action_taken`
  (`BILL_CREATED` or `EMAIL_SENT`), the **`qbo_bill_id`** (for posted bills), who was notified, and a
  note (for posted bills, which account it was coded to; otherwise the exception reason).

### Failure handling
- **Error Trigger → Send Error Alert** — if any node errors and the run fails, this emails you the
  error message so a silent failure never goes unnoticed.

---

## 5. The controls (what's being checked, and why)

All thresholds live in a `CONFIG` block at the top of the **Controls** node, so they're easy to tune:

| Setting | Value | Meaning |
|---|---|---|
| `AS_OF` | 2026-02-28 | The "processing date" the run pretends it's happening on (this is a Feb-2026 simulation). |
| `APPROVAL_LIMIT` | 2,500 | Invoices above this need human approval. |
| `MAX_AGE_DAYS` | 90 | Older than this = flagged as stale. |
| `POSSIBLE_DUP_DAYS` | 30 | Same vendor + same amount within this window = possible duplicate. |
| `CAPEX_MIN` | 1,000 | Asset-type spend at/above this gets a capitalisation review note. |

The checks performed on every invoice:

1. **Vendor match** — is the vendor on the approved QuickBooks list? Names are normalised (case,
   punctuation, and suffixes like *Inc/LLC/Ltd* are ignored) so "Slack" matches "Slack Technologies".
   No match → blocking exception.
2. **Exact duplicate** — same vendor + same invoice number already in the register → block. This is
   what stops the same bill being paid twice.
3. **Possible duplicate** — same vendor + same amount, *different* invoice number, within 30 days →
   block for review (catches re-issued or slightly altered invoices).
4. **Footing** — do the lines + tax equal the stated total? Mismatch → block.
5. **Data quality** — missing invoice number/date, bad date format, or no line items → block.
6. **Date sanity** — future-dated (after the processing date) → block; older than 90 days → stale flag.
7. **Service-period / accrual review** — if the service period starts in an earlier month than the
   invoice date, it's put on **HOLD** for a cut-off/accrual check (proper accrual accounting).
8. **Capex review** — if line descriptions look like assets (laptop, monitor, furniture, server…) and
   total ≥ 1,000, a note flags it for a capitalise-vs-expense decision.
9. **Approval limit** — total above 2,500 → **NEEDS_APPROVAL**.

**How the status is decided (in priority order):**
- Any *blocking* problem → **EXCEPTION**
- else a service-period issue → **HOLD**
- else over the approval limit → **NEEDS_APPROVAL**
- else → **READY**

---

## 6. Statuses and exceptions you can encounter

### The four statuses
| Status | Meaning | What the workflow does |
|---|---|---|
| **READY** | Passed every control | Codes it and **posts a bill to QuickBooks** |
| **NEEDS_APPROVAL** | Clean but over the $2,500 limit | **Emails you** for sign-off |
| **HOLD** | Needs an accrual / cut-off decision | **Emails you** for review |
| **EXCEPTION** | A blocking problem was found | **Emails you**; no bill created |

### The specific flags you may see (in `exception_reason` / `review_notes`)
- **UNKNOWN_VENDOR** — not on the approved QuickBooks vendor list.
- **EXACT_DUPLICATE of …** — this exact invoice number already exists for this vendor.
- **POSSIBLE_DUPLICATE of …** — same vendor and amount as a recent invoice with a different number.
- **FOOTING_MISMATCH** — line items + tax don't equal the stated total.
- **DATA_QUALITY** — missing/invalid invoice number, date, or line items.
- **FUTURE_DATED** — invoice date is after the processing date.
- **STALE_INVOICE (N days)** — older than 90 days.
- **SERVICE_PERIOD_REVIEW** — service relates to an earlier month → accrual check (HOLD).
- **CAPEX_REVIEW** — asset-like spend ≥ $1,000 → capitalisation check (note only).
- **OVER_APPROVAL_LIMIT** — total above $2,500 (drives NEEDS_APPROVAL).
- **CURRENCY_DEFAULTED_USD** — no currency on the invoice, so USD was assumed (note only).

### Operational errors (things that break a run, not controls)
- **"Accounts element id … not found"** — the expense account ID doesn't exist in the QuickBooks
  company (this was the original bug; fixed by mapping to real account IDs).
- **QuickBooks token expired** — the OAuth connection needs re-authorising in n8n.
- **Trial/plan expired (n8n Cloud)** — executions are blocked until you upgrade or self-host.
These trigger the **Send Error Alert** email rather than silently failing.

---

## 7. How bills are coded (GL account mapping)

For READY invoices, **Map GL account** chooses an expense account by scanning the vendor name and line
descriptions against keyword rules (first match wins):

| Looks like… | Posts to |
|---|---|
| Slack, HubSpot, Zoom, Adobe, "subscription/software/license" | Software Subscriptions |
| AWS, Azure, hosting, server | Cloud Hosting – Internal |
| Comcast, internet, utilities, phone | Utilities & Internet |
| Airfare, hotel, airline, travel | Travel |
| Meals, restaurant, catering | Travel Meals |
| Marketing, advertising, ads | Marketing & Advertising |
| Accounting, audit, CPA | Accounting & Tax Fees |
| Legal, attorney | Legal Fees |
| Office supplies, equipment, toner | Office Supplies & Small Equipment |
| Delaware Division, franchise tax, filing fee, license | Taxes & Licenses |
| Bank/wire/processing fees, Stripe | Bank Charges |
| Insurance, premium | Insurance |
| Rent, lease | Rent |
| **anything unrecognised** | **Uncategorized Expense** (so it's caught and recoded) |

---

## 8. The two sheets (and a crucial distinction)

- **register** — every invoice that came through, with its full assessment. This is written *before*
  the bill is attempted, so a row here means "we saw and assessed this", **not** "it posted".
- **audit_log** — what actually *happened* to each invoice (bill created or email sent).

> **Key insight:** `status = READY` means *approved to post*, not *posted*. The real proof a bill
> reached QuickBooks is a non-empty **`qbo_bill_id`** in the audit log. If that column is blank, no bill
> exists in QuickBooks — even if the status says READY. (This is exactly what happened with an earlier
> invoice that showed READY but never posted because the account bug blocked it.)

Also note: duplicate detection checks the **register**, not QuickBooks directly. So if you clear the
register and re-send an invoice that was already posted, the workflow will post it to QuickBooks again.
For a clean test, clear the register *and* delete any matching test bills in QuickBooks.

---

## 9. How to test it (end to end)

1. Make sure the **Gmail Trigger** is active and n8n is running.
2. Email a vendor invoice **PDF** to the AP inbox (`ap-inbox@example.com`), one attachment.
3. For a **READY** result (auto-posts a bill), the invoice needs: a **known** QuickBooks vendor, a
   **new** invoice number, an amount **under $2,500**, lines that **foot**, and a recent date.
4. Within a minute or two, check:
   - **register** — a new row with the assessed status.
   - **audit_log** — `action_taken = BILL_CREATED`, a real `qbo_bill_id`, note "Coded to …".
   - **QuickBooks** — the bill under the vendor (remember it's dated to the invoice date, so it may not
     be at the top of a date-sorted list).
5. To test the **review path**, send something that trips a control (e.g. a duplicate, or an amount
   over $2,500) and confirm you get the review email and **no** bill is created.

---

## 10. Tuning and next steps

**Easy knobs** (in the Controls node's `CONFIG`): approval limit, staleness window, duplicate window,
capex threshold, and the processing date.

**Possible enhancements:**
- Expand the GL mapping, or move it to a lookup table per vendor for precise coding.
- Add a reply-to-approve step so review emails can approve/reject without opening QuickBooks.
- Point it at a production QuickBooks company (switch the credential's Environment to Production and
  re-authorise) when moving beyond the sandbox.
- Group related nodes into sections on the canvas for readability.

---

*Built on n8n with QuickBooks Online (sandbox), Gmail, Google Sheets, and OpenAI. This workflow is the
NovaTech AP automation demo — a portfolio piece for a finance-automation freelance practice.*
