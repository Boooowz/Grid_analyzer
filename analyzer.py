"""Υπολογισμός στατιστικών ωραρίου ανά εργαζόμενο από αρχείο Εργάνης."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Optional

import pandas as pd

# Νυχτερινό ωράριο: 22:00 - 06:00
NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 6

SHIFT_RE = re.compile(r"(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})")
WORK_KEYWORD = "ΕΡΓΑΣΙΑ"
NON_WORK_KEYWORDS = ("ΜΗ ΕΡΓΑΣΙΑ", "ΑΝΑΠΑΥΣΗ", "ΡΕΠΟ", "ΑΔΕΙΑ", "ΑΣΘΕΝΕΙΑ")

RESULT_COLUMNS = [
    "ΑΦΜ",
    "Όνομα",
    "Επώνυμο",
    "Ημέρες Εργασίας",
    "Σύνολο Ωρών",
    "Νυχτερινές Ώρες",
    "Ώρες Κυριακής",
    "Νυχτερινές Ώρες Κυριακής",
    "Σύνολο Κυριακών",
]


def parse_shift(text: str, shift_date: date) -> Optional[tuple[datetime, datetime]]:
    """Επιστρέφει (start, end) datetimes για ένα κελί τύπου «ΕΡΓΑΣΙΑ 19:00-03:00»."""
    if not isinstance(text, str):
        return None
    upper = text.upper()
    if WORK_KEYWORD not in upper:
        return None
    if any(kw in upper for kw in NON_WORK_KEYWORDS):
        return None
    m = SHIFT_RE.search(text)
    if not m:
        return None
    sh, sm, eh, em = map(int, m.groups())
    if not (0 <= sh <= 24 and 0 <= eh <= 24 and 0 <= sm < 60 and 0 <= em < 60):
        return None

    start = datetime.combine(shift_date, time(sh % 24, sm))
    if eh == 0 and em == 0:
        end = datetime.combine(shift_date, time(0, 0)) + timedelta(days=1)
    elif eh == 24 and em == 0:
        end = datetime.combine(shift_date, time(0, 0)) + timedelta(days=1)
    else:
        end = datetime.combine(shift_date, time(eh, em))
        if end <= start:
            end += timedelta(days=1)
    return start, end


def _overlap_hours(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> float:
    s = max(a_start, b_start)
    e = min(a_end, b_end)
    if e <= s:
        return 0.0
    return (e - s).total_seconds() / 3600.0


def night_hours_in_segment(seg_start: datetime, seg_end: datetime) -> float:
    """Ώρες ενός intra-day segment που πέφτουν στο [00:00-06:00) ∪ [22:00-24:00)."""
    d = seg_start.date()
    midnight = datetime.combine(d, time(0, 0))
    early_end = midnight + timedelta(hours=NIGHT_END_HOUR)
    late_start = midnight + timedelta(hours=NIGHT_START_HOUR)
    next_midnight = midnight + timedelta(days=1)
    return (
        _overlap_hours(seg_start, seg_end, midnight, early_end)
        + _overlap_hours(seg_start, seg_end, late_start, next_midnight)
    )


def split_by_calendar_day(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Σπάει μια βάρδια σε κομμάτια που ανήκουν σε μία ημέρα το καθένα."""
    segments: list[tuple[datetime, datetime]] = []
    cur = start
    while cur < end:
        next_midnight = datetime.combine(cur.date(), time(0, 0)) + timedelta(days=1)
        seg_end = min(end, next_midnight)
        segments.append((cur, seg_end))
        cur = seg_end
    return segments


def _resolve_columns(df: pd.DataFrame) -> dict[str, str]:
    """Εντοπίζει τις στήλες ΑΦΜ / Όνομα / Επώνυμο / Ημερομηνία / Απασχόληση."""
    cols = list(df.columns)
    if len(cols) < 9:
        raise ValueError(
            f"Το αρχείο πρέπει να έχει τουλάχιστον 9 στήλες, βρέθηκαν {len(cols)}."
        )

    mapping = {
        "afm": cols[1],
        "first_name": cols[2],
        "last_name": cols[3],
        "date": cols[4],
        "employment": cols[8],
    }

    employment_col = mapping["employment"]
    sample = df[employment_col].dropna().astype(str).head(50)
    if not sample.str.contains("ΕΡΓΑΣΙΑ|ΑΝΑΠΑΥΣΗ|ΡΕΠΟ", regex=True).any():
        for c in cols:
            s = df[c].dropna().astype(str).head(50)
            if s.str.contains("ΕΡΓΑΣΙΑ", regex=False).any():
                mapping["employment"] = c
                break
    return mapping


def analyze(df: pd.DataFrame) -> pd.DataFrame:
    """Παράγει στατιστικά ανά ΑΦΜ από το raw dataframe του αρχείου."""
    if df.empty:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    col = _resolve_columns(df)
    dates = pd.to_datetime(df[col["date"]], dayfirst=True, errors="coerce")

    accum: dict[str, dict] = {}
    for idx, row in df.iterrows():
        afm_raw = row[col["afm"]]
        if pd.isna(afm_raw):
            continue
        afm = str(afm_raw).strip()
        if not afm or afm.lower() == "nan":
            continue

        shift_date = dates.iloc[idx]
        if pd.isna(shift_date):
            continue

        employment = row[col["employment"]]
        parsed = parse_shift(employment if isinstance(employment, str) else "", shift_date.date())
        if not parsed:
            continue
        start, end = parsed

        rec = accum.setdefault(afm, {
            "ΑΦΜ": afm,
            "Όνομα": _clean(row[col["first_name"]]),
            "Επώνυμο": _clean(row[col["last_name"]]),
            "Ημέρες Εργασίας": 0,
            "Σύνολο Ωρών": 0.0,
            "Νυχτερινές Ώρες": 0.0,
            "Ώρες Κυριακής": 0.0,
            "Νυχτερινές Ώρες Κυριακής": 0.0,
            "_sundays": set(),
        })
        rec["Ημέρες Εργασίας"] += 1

        for seg_start, seg_end in split_by_calendar_day(start, end):
            seg_hours = (seg_end - seg_start).total_seconds() / 3600.0
            seg_night = night_hours_in_segment(seg_start, seg_end)
            rec["Σύνολο Ωρών"] += seg_hours
            rec["Νυχτερινές Ώρες"] += seg_night
            if seg_start.weekday() == 6:  # Sunday
                rec["Ώρες Κυριακής"] += seg_hours
                rec["Νυχτερινές Ώρες Κυριακής"] += seg_night
                rec["_sundays"].add(seg_start.date())

    rows = []
    for rec in accum.values():
        rec["Σύνολο Κυριακών"] = len(rec.pop("_sundays"))
        for k in ("Σύνολο Ωρών", "Νυχτερινές Ώρες", "Ώρες Κυριακής", "Νυχτερινές Ώρες Κυριακής"):
            rec[k] = round(rec[k], 2)
        rows.append(rec)

    result = pd.DataFrame(rows, columns=RESULT_COLUMNS)
    if not result.empty:
        result = result.sort_values(["Επώνυμο", "Όνομα"], kind="stable").reset_index(drop=True)
    return result


def _clean(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()
