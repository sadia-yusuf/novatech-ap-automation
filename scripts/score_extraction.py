"""Score the n8n extraction output against the answer key.

Compares results/extraction_results.csv with sample_invoices/expected_results.csv, matched by source file,
on vendor, invoice number, invoice date and stated total. Case and whitespace are normalised; totals match
within 0.01. Writes results/extraction_accuracy.csv and prints per-field accuracy.

    python novatech/ap-automation/scripts/score_extraction.py
"""
from __future__ import annotations

import csv
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

AP = Path(__file__).resolve().parents[1]
EXPECTED = AP / "sample_invoices" / "expected_results.csv"
EXTRACTED = AP / "results" / "extraction_results.csv"
OUT = AP / "results" / "extraction_accuracy.csv"
TOLERANCE = Decimal("0.01")

# (field, key in expected_results.csv, key in extraction_results.csv)
FIELDS = [("vendor", "vendor", "vendor_name"), ("invoice_number", "invoice_no", "invoice_number"),
          ("invoice_date", "invoice_date", "invoice_date"), ("total", "total", "stated_total")]


def norm(s: str | None) -> str:
    return " ".join((s or "").split()).casefold()


def dec(s: str | None) -> Decimal | None:
    try:
        return Decimal((s or "").replace(",", "").replace("$", "").strip())
    except InvalidOperation:
        return None


def same(field: str, exp: str, got: str | None) -> bool:
    if field == "total":
        e, g = dec(exp), dec(got)
        return e is not None and g is not None and abs(e - g) <= TOLERANCE
    return norm(exp) == norm(got)


def read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main() -> int:
    expected = read(EXPECTED)
    got = {r["source_file"].strip(): r for r in read(EXTRACTED)}
    rows, passes = [], {f: 0 for f, _, _ in FIELDS}
    for e in expected:
        g = got.get(e["file"])
        row = {"source_file": e["file"], "scenario": e["scenario"], "extracted": "yes" if g else "MISSING"}
        ok_all = g is not None
        for field, ekey, gkey in FIELDS:
            ok = g is not None and same(field, e[ekey], g.get(gkey))
            passes[field] += ok
            ok_all &= ok
            row[f"{field}_result"] = "PASS" if ok else "FAIL"
            row[f"{field}_expected"] = e[ekey]
            row[f"{field}_extracted"] = g.get(gkey, "") if g else ""
        row["all_fields"] = "PASS" if ok_all else "FAIL"
        row["footing_ok"] = g.get("footing_ok", "") if g else ""
        rows.append(row)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    n = len(expected)
    print(f"Scored {n} invoices ({EXTRACTED.name} vs {EXPECTED.name}) -> {OUT.relative_to(AP.parent.parent)}")
    for field, _, _ in FIELDS:
        print(f"  {field:<15} {passes[field]:>2}/{n}  {100 * passes[field] / n:5.1f}%")
    full = sum(r["all_fields"] == "PASS" for r in rows)
    print(f"  {'all 4 fields':<15} {full:>2}/{n}  {100 * full / n:5.1f}%")
    for r in rows:
        bad = [f for f, _, _ in FIELDS if r[f"{f}_result"] == "FAIL"]
        if bad:
            detail = "; ".join(f"{f}: expected {r[f + '_expected']!r}, got {r[f + '_extracted']!r}" for f in bad)
            print(f"  FAIL {r['source_file']}: {detail}")
    extra = sorted(set(got) - {e["file"] for e in expected})
    if extra:
        print(f"  note: {len(extra)} extracted file(s) not in the answer key: {', '.join(extra)}")
    foot_bad = [r["source_file"] for r in rows if (r["footing_ok"].upper() == "FALSE") != (r["scenario"] == "lines_do_not_foot")]
    print("  footing control: " + ("OK - only the lines_do_not_foot invoice has footing_ok = FALSE"
                                   if not foot_bad else "UNEXPECTED: " + ", ".join(foot_bad)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
