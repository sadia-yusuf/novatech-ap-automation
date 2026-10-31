#  AP Invoice Automation

An AI-assisted **accounts-payable automation** built in [n8n](https://n8n.io). A vendor invoice (PDF) arrives by email; the workflow reads it, runs a full set of accounting controls over it, and then **either posts a bill to QuickBooks Online automatically or routes it to a human for review** — logging every decision to an append-only audit trail.

Built around a fictional client, **NovaTech Consulting LLC**, using entirely synthetic data. The guiding principle throughout: **AI proposes, rules constrain, humans approve** — no AI step is ever allowed to post to the ledger on its own.

> This is a portfolio project demonstrating finance-automation and internal-control design, authored by a Chartered Accountant (ICAI).

---

## Why it's built this way

Reading an invoice with AI is the easy part now. The hard — and valuable — part is deciding what **not** to do with it. An automation that simply posts every invoice is a liability: duplicate payments, wrong-period postings, and unapproved spend all slip straight through.

So the design goal was never "do AP faster." It was: **apply the controls a careful AP clerk applies, every time, consistently, and auto-post only the invoices that are genuinely clean.** Everything doubtful is escalated, and nothing is ever silently corrected.

---

## How it works

```
Invoice email arrives
      │
      ▼
[Gmail Trigger] → [Normalise intake] → [Extract from File] → [AI extraction]
                                                                    │
                                                                    ▼
                                                          [Arithmetic checks]
                                                                    │
                            [QBO vendors] → [Read register] → [Controls]
                                                                    │
                                                          [Append to register]
                                                                    │
                                                        [Preserve Invoice Data]
                                                                    │
                                                               [Switch] ── status?
                                      READY │                           │ NEEDS_APPROVAL / HOLD / EXCEPTION
                                            ▼                           ▼
                                  [Map GL account]            [Send Approval Email]
                                            ▼                           │
                                  [Create QBO bill] ─────────┬──────────┘
                                                             ▼
                                                   [Append to audit log]
```

A separate **Error Trigger → Send Error Alert** path emails on any outright failure, so nothing fails silently.

---

## The controls

Every invoice is checked against the approved vendor master and the full history of what's been processed before. Thresholds live in a single `CONFIG` block for easy tuning:

| Control | What it catches |
|---|---|
| **Vendor match** | Vendor not on the approved QuickBooks list (names normalised for suffixes/case) |
| **Exact duplicate** | Same vendor + invoice number already processed → prevents double-payment |
| **Possible duplicate** | Same vendor + amount within a window, different number → re-issued/altered invoices |
| **Footing** | Line items + tax don't tie to the stated total |
| **Data quality** | Missing/invalid invoice number, date, or line items |
| **Date sanity** | Future-dated (blocked) or stale beyond the age limit |
| **Service-period / accrual** | Service relates to an earlier month → cut-off/accrual review (HOLD) |
| **Capitalisation** | Asset-like spend over the capex threshold → capitalise-vs-expense review |
| **Approval limit** | Total over the approval threshold → routed for sign-off |

Each invoice is assigned one status, which drives the routing:

| Status | Meaning | Outcome |
|---|---|---|
| **READY** | Passed every control | Bill auto-posted to QuickBooks, coded to a mapped expense account |
| **NEEDS_APPROVAL** | Clean but over the approval limit | Review email, no posting |
| **HOLD** | Needs an accrual / cut-off decision | Review email, no posting |
| **EXCEPTION** | A blocking problem was found | Review email, no posting |

---

## Results from a live run

A deliberately messy batch of 19 test invoices was processed end to end, untouched:

- **12 auto-posted** to QuickBooks, each coded to the correct expense account
- **7 correctly stopped** before posting:
  - 2 unknown vendors
  - 2 exact duplicates (the "resend" that quietly causes double-payments)
  - 1 footing mismatch
  - 1 over the approval limit → routed for sign-off
  - 1 prior-period service date → held for an accrual decision

See [`results/`](results/) for the extraction accuracy, controls output, and run detail.

> **Audit note:** in this system `status = READY` means *approved to post*, not *posted*. The proof a bill actually reached QuickBooks is a non-empty `qbo_bill_id` in the audit log. If it's blank, nothing posted — whatever the status says.

---

## Stack

- **n8n** (self-hosted) — orchestration
- **QuickBooks Online** (Intuit sandbox) — the ledger; bills posted via the Accounting API
- **Google Sheets** — the invoice register and the append-only audit log
- **OpenAI** (`gpt-4o-mini`) — invoice field extraction, constrained by a strict schema
- **Python** — synthetic invoice generator and extraction scoring

---

## Repository structure

```
novatech-ap-automation/
├── workflow/
│   └── P6-invoice-extraction.json      # the n8n workflow (import this)
├── prompts/
│   ├── extraction_prompt.md            # the extraction system prompt
│   └── extraction_schema.json          # the structured-output schema
├── scripts/
│   ├── generate_sample_invoices.py     # reproducible synthetic invoices (fixed seed)
│   └── score_extraction.py             # extraction accuracy scoring
├── sample_invoices/
│   └── expected_results.csv            # ground truth for the sample set
├── results/
│   ├── extraction_accuracy.csv
│   ├── extraction_controls.csv
│   └── extraction_results.csv
├── docs/
│   └── build-and-operations-guide.md   # full build + operations walkthrough
├── .env.example
└── README.md
```

---

## Running it yourself

1. **Generate the sample invoices** (reproducible from a fixed seed):
   ```bash
   python scripts/generate_sample_invoices.py
   ```
2. **Import the workflow** into n8n: *Workflows → ⋮ → Import from File* → `workflow/P6-invoice-extraction.json`.
3. **Connect credentials** in n8n: QuickBooks Online, Gmail, Google Sheets, and OpenAI. Copy the variable names in [`.env.example`](.env.example) — never commit real secrets.
4. **Set up the register**: a Google Sheet with two tabs, `register` and `audit_log`.
5. **Publish/activate** the workflow and email an invoice PDF to the AP inbox.

The [build & operations guide](docs/build-and-operations-guide.md) walks through every step, every control, and every exception in detail.

---

## Design rules

- **Synthetic data only** — everything is generated from a fixed seed; no real client, employer, or personal data.
- **No secrets in Git** — credentials live in a git-ignored `.env`; only `.env.example` is committed.
- **AI proposes, rules constrain, humans approve** — no AI step posts to the ledger or moves money.
- **Every write is idempotent and logged** — check by natural key before creating; append to an audit log.
- **Flag, never fix** — the system records problems; it never silently alters a vendor's numbers.

---

*Part of a broader finance-automation portfolio. Built with a configure-manually-first, automate-after discipline — every automation must improve accuracy, control, auditability, or exception handling.*
