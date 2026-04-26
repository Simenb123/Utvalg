"""reskontro_open_items.py -- Beregning av apne poster og faktura-matching.

Ekstrahert fra page_reskontro.py.  Rene beregningsfunksjoner uten GUI-kobling.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Tekst-klassifisering
# ---------------------------------------------------------------------------

def _is_invoice_tekst(tekst: str) -> bool:
    t = tekst.lower()
    return any(k in t for k in ("faktura", "invoice", "kreditnota", "credit note"))


def _is_payment_tekst(tekst: str) -> bool:
    t = tekst.lower()
    return any(k in t for k in (
        "betaling", "innbetaling", "betalt", "payment", "avregning",
        "utbetaling", "remittering",
    ))


def _is_non_invoice_tekst(tekst: str) -> bool:
    """Return True for journal entries that are NOT invoices/payments."""
    t = tekst.lower()
    return any(k in t for k in (
        "periodisering", "avskrivning", "korreksjon", "ompostering",
        "avsetning", "avsatt", "overføring", "reklassifisering",
        "nedskrivning", "reversering", "saldooverføring",
    ))


_RE_FAKTURA_NR = re.compile(
    r'(?:faktura\s+(?:nummer\s+)?|kreditnota\s+|invoice\s+(?:number\s+)?)(\d{4,})',
    re.IGNORECASE,
)


def _extract_faktura_nr(tekst: str) -> str | None:
    """Trekk ut faktura-nummeret fra en tekst-streng.

    Eksempler:
      "Faktura nummer 23660 til Veidekke..."  -> "23660"
      "Betaling for faktura 23660 kontonummer..." -> "23660"
      "Kreditnota 12345"                      -> "12345"
    Returnerer None hvis ingen match.
    """
    m = _RE_FAKTURA_NR.search(tekst)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Apne poster (FIFO)
# ---------------------------------------------------------------------------

def _compute_open_items(
    df: pd.DataFrame, *, nr: str, mode: str, ub: float,
) -> pd.DataFrame:
    """Identifiser apne (ubetalte) fakturaer for en kunde/leverandor.

    Bruker FIFO-prinsippet: eldste fakturaer antas betalt forst.
    De nyeste fakturaene som til sammen utgjor UB er apne poster.
    Dette garanterer at sum(Gjenstar) = UB.

    Returnerer DataFrame med en rad per faktura-bilag:
      Bilag, FakturaNr, Dato, Tekst, Fakturabelop, Betalt (i ar), Gjenstar, Status
    """
    nr_col = "Kundenr" if mode == "kunder" else "Leverandørnr"
    if nr_col not in df.columns:
        return pd.DataFrame()
    sub = df[df[nr_col].astype(str).str.strip() == nr].copy()
    if sub.empty:
        return pd.DataFrame()

    sub["__belop__"] = pd.to_numeric(
        sub["Beløp"] if "Beløp" in sub.columns else 0,
        errors="coerce").fillna(0.0)
    sub["__bilag__"] = (sub["Bilag"].astype(str).str.strip()
                        if "Bilag" in sub.columns else "")
    sub["__tekst__"] = (sub["Tekst"].fillna("").astype(str)
                        if "Tekst" in sub.columns else "")
    sub["__dato__"]  = (sub["Dato"].astype(str).str[:10]
                        if "Dato" in sub.columns else "")
    sub["__fnr__"]   = sub["__tekst__"].apply(_extract_faktura_nr)

    is_pay = sub["__tekst__"].apply(_is_payment_tekst)
    is_inv = sub["__tekst__"].apply(_is_invoice_tekst)
    is_non_inv = sub["__tekst__"].apply(_is_non_invoice_tekst)

    if mode == "kunder":
        inv_sign = sub["__belop__"] > 0.01
    else:
        inv_sign = sub["__belop__"] < -0.01

    is_credit = sub["__tekst__"].str.lower().str.contains(
        "kreditnota|credit note", regex=True, na=False)

    # Invoice rows: correct sign, not payment, not non-invoice, not credit note
    inv_mask = ((is_inv & inv_sign & ~is_credit)
                | (inv_sign & ~is_pay & ~is_non_inv & ~is_credit))

    invoice_rows = sub[inv_mask]

    # --- Group invoice rows by bilag ---
    inv_by_bilag: dict[str, dict] = {}
    for _, ir in invoice_rows.iterrows():
        bilag = ir["__bilag__"]
        if bilag not in inv_by_bilag:
            _fnr = ir["__fnr__"]
            inv_by_bilag[bilag] = {
                "bilag": bilag,
                "dato":  ir["__dato__"],
                "tekst": ir["__tekst__"],
                "fnr":   _fnr if pd.notna(_fnr) else None,
                "total": 0.0,
            }
        inv_by_bilag[bilag]["total"] += float(ir["__belop__"])
        if inv_by_bilag[bilag]["fnr"] is None and pd.notna(ir["__fnr__"]):
            inv_by_bilag[bilag]["fnr"] = ir["__fnr__"]

    if not inv_by_bilag:
        return pd.DataFrame()

    # --- FIFO: newest invoices totaling to UB are open ---
    # Customers: invoices positive, UB > 0 = open items
    # Suppliers: invoices negative, UB < 0 = open items
    if mode == "kunder":
        has_open = ub > 0.01
        sign = 1.0
    else:
        has_open = ub < -0.01
        sign = -1.0

    # Sort newest first for FIFO assignment
    sorted_invoices = sorted(
        inv_by_bilag.values(), key=lambda x: x["dato"], reverse=True)

    abs_remaining = abs(ub) if has_open else 0.0
    rows: list[dict] = []

    for inv in sorted_invoices:
        abs_inv = abs(inv["total"])

        if abs_remaining >= abs_inv - 0.005:
            # Fully open
            gjenstar = inv["total"]
            abs_remaining -= abs_inv
            status = "\u2717 \u00c5pen"
        elif abs_remaining > 0.01:
            # Partially open -- only the remaining portion
            gjenstar = sign * abs_remaining
            abs_remaining = 0.0
            status = "~ Delvis betalt"
        else:
            # Fully paid (FIFO: older invoices paid first)
            gjenstar = 0.0
            status = "\u2713 Betalt"

        paid = inv["total"] - gjenstar

        rows.append({
            "Bilag":         inv["bilag"],
            "FakturaNr":     inv["fnr"] or "",
            "Dato":          inv["dato"],
            "Tekst":         inv["tekst"],
            "Fakturabel\u00f8p":  inv["total"],
            "Betalt (i \u00e5r)": paid if abs(paid) > 0.001 else None,
            "Gjenstår":      gjenstar,
            "Status":        status,
        })

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    order  = {"\u2717 \u00c5pen": 0, "~ Delvis betalt": 1, "\u2713 Betalt": 2}
    result["__sort__"] = result["Status"].map(order).fillna(3)
    return result.sort_values(["__sort__", "Dato"]).drop(columns="__sort__").reset_index(drop=True)


def _compute_open_items_with_confidence(
    df: pd.DataFrame, *, nr: str, mode: str,
    ub: float | None = None, ib: float | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Wrapper around _compute_open_items that adds confidence info.

    With FIFO, sum(Gjenstar) = UB by construction.  The confidence flag
    instead indicates whether all open items could be identified from
    this period's invoices, or if some of the UB must stem from prior
    years (IB).
    """
    confidence: dict = {"level": "ukjent", "symbol": "?", "message": ""}
    if ub is None:
        return pd.DataFrame(), confidence

    result = _compute_open_items(df, nr=nr, mode=mode, ub=ub)

    abs_ub = abs(ub)
    if abs_ub < 0.01:
        confidence = {"level": "h\u00f8y", "symbol": "\u2713", "message": "UB \u2248 0, ingen \u00e5pne poster"}
        return result, confidence

    if result.empty:
        ib_val = ib if ib is not None else 0.0
        if abs(ib_val) > 0.01:
            confidence = {"level": "middels", "symbol": "~",
                          "message": f"Ingen fakturaer funnet \u2014 UB ({ub:,.0f}) stammer trolig fra IB ({ib_val:,.0f})"}
        else:
            confidence = {"level": "lav", "symbol": "\u26a0",
                          "message": f"Ingen fakturaer funnet, men UB = {ub:,.0f}"}
        return result, confidence

    # Check if UB exceeded sum of invoices (remaining from prior years)
    sum_inv = float(result["Fakturabel\u00f8p"].sum())
    abs_sum_inv = abs(sum_inv)
    ib_val = ib if ib is not None else 0.0

    if abs_ub <= abs_sum_inv + 0.01:
        # All open items identified from this year's invoices
        confidence = {"level": "h\u00f8y", "symbol": "\u2713",
                      "message": f"FIFO \u2014 sum \u00e5pne = UB ({ub:,.0f})"}
    elif abs(ib_val) > 0.01:
        # UB > sum invoices, but IB explains the gap
        gap = abs_ub - abs_sum_inv
        confidence = {"level": "middels", "symbol": "~",
                      "message": (f"FIFO \u2014 alle \u00e5rets fakturaer er \u00e5pne, "
                                  f"{gap:,.0f} stammer fra IB ({ib_val:,.0f})")}
    else:
        confidence = {"level": "middels", "symbol": "~",
                      "message": f"FIFO \u2014 UB ({ub:,.0f}) > sum fakturaer ({sum_inv:,.0f})"}

    return result, confidence


# ---------------------------------------------------------------------------
# Aldersfordeling
# ---------------------------------------------------------------------------

def _compute_aging_buckets(
    open_items: list[dict], *, reference_date: str,
) -> list[tuple[str, float, int]]:
    """Beregn aldersfordeling basert pa fakturadato.

    Returnerer [(bucket_label, sum_gjenstar, antall), ...].
    """
    from datetime import datetime

    try:
        ref = datetime.strptime(reference_date[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return []

    labels = ["0\u201330 d", "31\u201360 d", "61\u201390 d", "91\u2013180 d", ">180 d"]
    sums = [0.0] * 5
    counts = [0] * 5

    for item in open_items:
        if item.get("Status") == "\u2713 Betalt":
            continue
        try:
            inv_date = datetime.strptime(str(item["Dato"])[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        days = (ref - inv_date).days
        gjenstar = float(item.get("Gjenstår", 0))
        if days <= 30:
            idx = 0
        elif days <= 60:
            idx = 1
        elif days <= 90:
            idx = 2
        elif days <= 180:
            idx = 3
        else:
            idx = 4
        sums[idx] += gjenstar
        counts[idx] += 1

    return [(labels[i], sums[i], counts[i]) for i in range(5)]


# ---------------------------------------------------------------------------
# Matching mot etterfølgende periode
# ---------------------------------------------------------------------------

def _match_open_against_period(
    open_invoices: pd.DataFrame,
    subseq_df: pd.DataFrame,
    *,
    nr: str,
    mode: str,
) -> pd.DataFrame:
    """Match apne fakturaer (fra _compute_open_items) mot etterfølgende periode.

    Kun fakturaer med Status = 'Apen' tas med.
    Matching mot etterfølgende periode:
      a) Betalings Referanse = faktura-bilag
      b) Faktura-bilag finnes i betalingens Tekst

    Returnerer DataFrame:
      Status, Bilag, Dato, Tekst, Gjenstar (ar N),
      Betalt dato, Betalt belop, Resterende
    """
    if open_invoices.empty:
        return pd.DataFrame()

    open_only = open_invoices[open_invoices["Status"] == "\u2717 \u00c5pen"]
    if open_only.empty:
        return pd.DataFrame()

    nr_col = "Kundenr" if mode == "kunder" else "Leverandørnr"
    if nr_col not in subseq_df.columns:
        subseq_sub = subseq_df.copy()
    else:
        subseq_sub = subseq_df[
            subseq_df[nr_col].astype(str).str.strip() == str(nr)].copy()

    subseq_sub["__s_belop__"] = pd.to_numeric(
        subseq_sub["Beløp"] if "Beløp" in subseq_sub.columns else 0,
        errors="coerce").fillna(0.0)
    subseq_sub["__s_ref__"]  = (
        subseq_sub["Referanse"].fillna("").astype(str).str.strip()
        if "Referanse" in subseq_sub.columns else "")
    subseq_sub["__s_tekst__"] = (
        subseq_sub["Tekst"].fillna("").astype(str)
        if "Tekst" in subseq_sub.columns else "")
    subseq_sub["__s_dato__"]  = (
        subseq_sub["Dato"].astype(str).str[:10]
        if "Dato" in subseq_sub.columns else "")
    subseq_sub["__s_bilag__"] = (
        subseq_sub["Bilag"].fillna("").astype(str).str.strip()
        if "Bilag" in subseq_sub.columns else "")

    # Pre-compute faktura_nr for all subsequent rows
    subseq_sub["__s_fnr__"] = subseq_sub["__s_tekst__"].apply(_extract_faktura_nr)

    rows: list[dict] = []
    for _, inv_row in open_only.iterrows():
        inv_bilag  = str(inv_row["Bilag"])
        inv_fnr    = str(inv_row.get("FakturaNr", "") or "")
        gjenstar_n = float(inv_row["Gjenstår"])

        paid = pd.DataFrame()
        if not subseq_sub.empty:
            candidates = pd.DataFrame()

            # a) Match via faktura-nr fra tekst
            if inv_fnr:
                m_fnr = subseq_sub[subseq_sub["__s_fnr__"] == inv_fnr]
                candidates = pd.concat([candidates, m_fnr])

            # b) Referanse-felt = faktura-bilag eller faktura-nr
            if inv_fnr:
                m_ref = subseq_sub[subseq_sub["__s_ref__"] == inv_fnr]
                candidates = pd.concat([candidates, m_ref])
            m_ref2 = subseq_sub[subseq_sub["__s_ref__"] == inv_bilag]
            candidates = pd.concat([candidates, m_ref2])

            # c) Fallback: faktura-bilag i tekst
            if len(inv_bilag) >= 4:
                m_txt = subseq_sub[
                    subseq_sub["__s_tekst__"].str.contains(
                        inv_bilag, na=False, regex=False)]
                candidates = pd.concat([candidates, m_txt])

            if not candidates.empty:
                candidates = candidates.drop_duplicates()
                paid = candidates[candidates["__s_tekst__"].apply(_is_payment_tekst)]

        paid_belop = float(paid["__s_belop__"].sum()) if not paid.empty else 0.0
        paid_dato  = (str(paid["__s_dato__"].min())
                      if not paid.empty else "")
        # Ta første matchende betalings-bilag (etter tidligste dato) som
        # representativ referanse når det finnes flere.
        paid_bilag = ""
        if not paid.empty and "__s_bilag__" in paid.columns:
            try:
                first_paid = paid.sort_values("__s_dato__").iloc[0]
                paid_bilag = str(first_paid.get("__s_bilag__", "") or "")
            except Exception:
                paid_bilag = ""
        resterende = gjenstar_n + paid_belop

        if abs(resterende) < 0.01:
            status = "\u2713 Betalt"
        elif abs(paid_belop) > 0.001:
            status = "~ Delvis betalt"
        else:
            status = "\u2717 Fortsatt \u00e5pen"

        rows.append({
            "Status":          status,
            "Bilag":           inv_bilag,
            "FakturaNr":       inv_fnr,
            "Dato":            str(inv_row.get("Dato", ""))[:10],
            "Tekst":           str(inv_row.get("Tekst", "")),
            "Gjenstår (år N)": gjenstar_n,
            "Betalt dato":     paid_dato,
            "Betalt bilag":    paid_bilag,
            "Betalt beløp":    paid_belop if abs(paid_belop) > 0.001 else None,
            "Resterende":      resterende,
        })

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    order  = {"\u2717 Fortsatt \u00e5pen": 0, "~ Delvis betalt": 1, "\u2713 Betalt": 2}
    result["__sort__"] = result["Status"].map(order).fillna(3)
    return result.sort_values(["__sort__", "Dato"]).drop(columns="__sort__")
