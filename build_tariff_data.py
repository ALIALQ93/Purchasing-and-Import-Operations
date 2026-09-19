# -*- coding: utf-8 -*-
"""Extract customs tariff rates from PDF and valuations from HSC.xlsx."""
import json
import os
import re
import sys
from collections import Counter

import openpyxl
import pymupdf

sys.stdout.reconfigure(encoding="utf-8")

doc = pymupdf.open("Customs duties.pdf")
text = "\n".join(page.get_text() for page in doc)
lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

hs_exact = re.compile(r"^(\d{8})$")
hs_heading = re.compile(r"^(\d{6,8})\*+$")
num_exact = re.compile(r"^(\d+(?:\.\d+)?)$")


def is_noise(s: str) -> bool:
    return (
        "صفحة" in s
        or "اجمالي" in s
        or "إجمالي" in s
        or s.startswith("HS")
        or "بيانات" in s
        or s in ("التعرفة", "الكمركية", "التأمينات", "التامينات", "RUL_COD")
        or s.startswith("9824")
    )


entries = []
i = 0
n = len(lines)
while i < n:
    raw = lines[i].replace("\u200f", "").replace("\u200e", "").strip()
    m = hs_exact.match(raw)
    glued = None
    if not m:
        m2 = re.match(r"^(\d{8})(.+)$", raw)
        if m2 and not hs_heading.match(raw):
            code = m2.group(1)
            glued = m2.group(2).strip()
        else:
            i += 1
            continue
    else:
        code = m.group(1)

    j = i + 1
    desc_parts = []
    prohibited = False
    rates = []

    if glued:
        tm = re.match(r"^(.*?)(\d+(?:\.\d+)?)$", glued)
        if tm and tm.group(1).strip() and float(tm.group(2)) <= 100:
            desc_parts.append(tm.group(1).strip())
            rates.append(float(tm.group(2)))
        elif glued and glued != "PROHIBITED_CODE":
            if "PROHIBITED" in glued:
                prohibited = True
                glued2 = glued.replace("PROHIBITED_CODE", "").strip()
                if glued2:
                    desc_parts.append(glued2)
            else:
                desc_parts.append(glued)

    while j < n and len(rates) < 2:
        cur = lines[j].replace("\u200f", "").replace("\u200e", "").strip()
        if is_noise(cur):
            j += 1
            continue
        if cur == "PROHIBITED_CODE" or (
            cur.endswith("PROHIBITED_CODE") and not re.match(r"^\d", cur)
        ):
            if cur != "PROHIBITED_CODE":
                left = cur.replace("PROHIBITED_CODE", "").strip()
                if left:
                    tm = re.match(r"^(.*?)(\d+(?:\.\d+)?)$", left)
                    if (
                        tm
                        and tm.group(1).strip()
                        and float(tm.group(2)) <= 100
                        and len(rates) < 2
                    ):
                        desc_parts.append(tm.group(1).strip())
                        rates.append(float(tm.group(2)))
                    else:
                        desc_parts.append(left)
            prohibited = True
            j += 1
            continue
        if hs_exact.match(cur) or hs_heading.match(cur):
            break
        if re.match(r"^\d{8}\D", cur):
            break
        if num_exact.match(cur):
            rates.append(float(cur))
            j += 1
            continue
        tm = re.match(r"^(.*?)(\d+(?:\.\d+)?)$", cur)
        if tm and tm.group(1).strip() and not re.match(r"^\d{6}", cur):
            val = float(tm.group(2))
            nxt = lines[j + 1].strip() if j + 1 < n else ""
            nxt_clean = nxt.replace("\u200f", "").replace("\u200e", "")
            if val <= 100 and (
                num_exact.match(nxt_clean)
                or hs_exact.match(nxt_clean)
                or hs_heading.match(nxt_clean)
                or nxt_clean == "PROHIBITED_CODE"
                or not nxt_clean
                or is_noise(nxt_clean)
            ):
                desc_parts.append(tm.group(1).strip())
                rates.append(val)
                j += 1
                continue
        desc_parts.append(cur)
        j += 1
        if len(desc_parts) > 12:
            break

    clean_rates = [r for r in rates if r <= 100]
    if not clean_rates and rates:
        clean_rates = rates[:1]
    if clean_rates:
        duty = clean_rates[0]
        insur = clean_rates[1] if len(clean_rates) > 1 else None
        entries.append(
            {
                "hs": code,
                "desc": " ".join(desc_parts).replace("PROHIBITED_CODE", "").strip()[:240],
                "duty": duty,
                "insur": insur,
                "prohibited": prohibited
                or ("PROHIBITED" in " ".join(desc_parts)),
            }
        )
    i = j if j > i else i + 1

by_hs = {}
for e in entries:
    by_hs[e["hs"]] = e
tariff = list(by_hs.values())
print("tariff unique", len(tariff), "raw", len(entries))
print("duty dist", Counter(e["duty"] for e in tariff).most_common(12))
print("insur dist", Counter(e["insur"] for e in tariff).most_common(8))
print("prohibited", sum(1 for e in tariff if e["prohibited"]))

wb = openpyxl.load_workbook("HSC.xlsx", read_only=True, data_only=True)
ws = wb["ورقة1"]
vals = []
for row in ws.iter_rows(min_row=2, values_only=True):
    code, tsc, desc, title, mn, mx, unit, model, origin = (list(row) + [None] * 9)[:9]
    if not code:
        continue
    code = str(code).strip()
    if not re.fullmatch(r"\d{8}", code):
        code = re.sub(r"\D", "", code)
        if len(code) != 8:
            continue
    vals.append(
        {
            "hs": code,
            "tsc": str(tsc).strip() if tsc is not None else "",
            "desc": str(desc).strip() if desc else "",
            "title": str(title).strip() if title else "",
            "min": float(mn) if isinstance(mn, (int, float)) else None,
            "max": float(mx) if isinstance(mx, (int, float)) else None,
            "unit": str(unit).strip() if unit else "",
            "model": str(model).strip() if model is not None else "",
            "origin": str(origin).strip() if origin else "",
        }
    )
print("valuations", len(vals))
matched = sum(1 for v in vals if v["hs"] in by_hs)
print(
    "hsc with tariff match",
    matched,
    "/",
    len(vals),
    f"({100 * matched / len(vals):.1f}%)",
)

tmap = {
    e["hs"]: [
        e["duty"],
        e["insur"] if e["insur"] is not None else 0,
        1 if e["prohibited"] else 0,
    ]
    for e in tariff
}

vrows = [
    [
        v["hs"],
        v["tsc"],
        v["desc"],
        v["title"],
        v["min"],
        v["max"],
        v["unit"],
        v["model"],
        v["origin"],
    ]
    for v in vals
]

out = {
    "meta": {
        "tariffCount": len(tmap),
        "valuationCount": len(vrows),
        "source": "Customs duties.pdf + HSC.xlsx",
        "note": "duty% and insurance% from tariff schedule; min/max are reference customs values",
    },
    "tariff": tmap,
    "items": vrows,
}

with open("tariff-data.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

with open("tariff-data.js", "w", encoding="utf-8") as f:
    f.write("window.TARIFF_DATA = ")
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    f.write(";\n")

print("json MB", round(os.path.getsize("tariff-data.json") / 1024 / 1024, 2))
print("js MB", round(os.path.getsize("tariff-data.js") / 1024 / 1024, 2))
print("done")
