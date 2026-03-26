from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from .utils import dec_round, to_decimal


_SPECIAL_CODE_MAP: dict[str, tuple[str, str]] = {
    "sumArbeidsgiveravgift": ("aga", "AGA"),
    "sumForskuddstrekk": ("forskuddstrekk", "Forskuddstrekk"),
    "sumSkattetrekk": ("skattetrekk", "Skattetrekk"),
    "sumFinansskattLoenn": ("finansskattloenn", "FinansskattLoenn"),
}

_AGA_GRUNNLAG_EXTRAS_MAP: dict[str, tuple[str, str]] = {
    "tilskuddOgPremieTilPensjon": (
        "tilskuddOgPremieTilPensjon",
        "Tilskudd og premie til pensjon",
    ),
    "fradragIGrunnlagetForSone": (
        "sumAvgiftsgrunnlagRefusjon",
        "Sum avgiftsgrunnlag refusjon",
    ),
}


def _get(d: Any, path: list[str], default: Any = None) -> Any:
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
    return default if cur is None else cur


def _add_amount(
    totals: dict[str, Decimal],
    names: dict[str, str],
    code: str,
    name: str,
    amount: Any,
) -> None:
    code = (code or "").strip()
    if not code:
        return

    bel = to_decimal(amount)
    totals[code] = totals.get(code, Decimal("0")) + bel

    nm = (name or "").strip()
    if nm and code not in names:
        names[code] = nm
    elif code not in names:
        names[code] = code


def _extract_income_nodes_altinn(data: dict[str, Any]) -> list[dict[str, Any]]:
    oppgave = _get(data, ["mottatt", "oppgave"], {}) or {}
    if not isinstance(oppgave, dict):
        return []

    opps = oppgave.get("oppsummerteVirksomheter") or {}
    if isinstance(opps, dict):
        inntekt = opps.get("inntekt")
        if isinstance(inntekt, list) and inntekt:
            return [x for x in inntekt if isinstance(x, dict)]

    virksomheter = oppgave.get("virksomhet")
    out: list[dict[str, Any]] = []
    if isinstance(virksomheter, list):
        for v in virksomheter:
            if not isinstance(v, dict):
                continue
            inn = v.get("inntekt")
            if isinstance(inn, list):
                out.extend([x for x in inn if isinstance(x, dict)])

    return out


def _sum_avgiftsgrunnlag_beloep(items: Any) -> Decimal:
    if not isinstance(items, list):
        return Decimal("0")

    total = Decimal("0")
    for it in items:
        if not isinstance(it, dict):
            continue
        v = it.get("avgiftsgrunnlagBeloep")
        if v is None:
            continue
        total += to_decimal(v)
    return total


def _extract_aga_grunnlag_extras(
    oppsummerte_virksomheter: Any,
) -> tuple[dict[str, Decimal], dict[str, str]]:
    totals: dict[str, Decimal] = {}
    names: dict[str, str] = {}

    if not isinstance(oppsummerte_virksomheter, dict):
        return totals, names

    aga = oppsummerte_virksomheter.get("arbeidsgiveravgift")
    if not isinstance(aga, dict):
        return totals, names

    for json_key, (code, label) in _AGA_GRUNNLAG_EXTRAS_MAP.items():
        val = _sum_avgiftsgrunnlag_beloep(aga.get(json_key))
        if val != 0:
            totals[code] = val
            names[code] = label

    return totals, names


def parse_a07_json(
    path_or_data: str | Path | dict[str, Any],
    top_n: int | None = None,
    include_special_codes: bool = True,
    include_aga_grunnlag_extras: bool = True,
) -> pd.DataFrame:
    if isinstance(path_or_data, (str, Path)):
        data = json.loads(Path(path_or_data).read_text(encoding="utf-8"))
    elif isinstance(path_or_data, dict):
        data = path_or_data
    else:
        raise TypeError("parse_a07_json expects path (str/Path) or dict")

    totals: dict[str, Decimal] = {}
    names: dict[str, str] = {}
    special_code_map = _SPECIAL_CODE_MAP if include_special_codes else {}

    inntekter = data.get("inntekter")
    if isinstance(inntekter, list) and inntekter:
        for it in inntekter:
            if not isinstance(it, dict):
                continue
            li = it.get("loennsinntekt") or {}
            if not isinstance(li, dict):
                li = {}
            code = str(li.get("type") or li.get("beskrivelse") or "").strip()
            name = str(li.get("beskrivelse") or code).strip()
            _add_amount(totals, names, code, name, it.get("beloep"))

        per = data.get("periode")
        if isinstance(per, dict):
            tot = per.get("mottattAvgiftOgTrekkTotalt")
            if isinstance(tot, dict):
                for field, (code, name) in special_code_map.items():
                    if field in tot:
                        _add_amount(totals, names, code, name, tot.get(field))
    else:
        for it in _extract_income_nodes_altinn(data):
            li = it.get("loennsinntekt") or {}
            if not isinstance(li, dict):
                li = {}
            code = str(li.get("type") or li.get("beskrivelse") or "").strip()
            name = str(li.get("beskrivelse") or code).strip()
            _add_amount(totals, names, code, name, it.get("beloep"))

        pay = _get(data, ["mottatt", "oppgave", "betalingsinformasjon"], {})
        if isinstance(pay, dict):
            for field, (code, name) in special_code_map.items():
                if field in pay:
                    _add_amount(totals, names, code, name, pay.get(field))

    if include_special_codes:
        oppsum = _get(data, ["mottatt", "oppgave", "oppsummerteVirksomheter"], {})
        if isinstance(oppsum, dict):
            fallback_lists: dict[str, tuple[str, str]] = {
                "forskuddstrekk": ("forskuddstrekk", "Forskuddstrekk"),
                "arbeidsgiveravgift": ("aga", "AGA"),
            }
            for key, (code, name) in fallback_lists.items():
                if totals.get(code, Decimal("0")) != Decimal("0"):
                    continue
                items = oppsum.get(key)
                if not isinstance(items, list):
                    continue
                amt = Decimal("0")
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    v = it.get("beloep")
                    if v is None:
                        continue
                    try:
                        amt += abs(to_decimal(v))
                    except Exception:
                        continue
                if amt != Decimal("0"):
                    _add_amount(totals, names, code, name, amt)

            if include_aga_grunnlag_extras:
                extra_totals, extra_names = _extract_aga_grunnlag_extras(oppsum)
                for c, amt in extra_totals.items():
                    _add_amount(totals, names, c, extra_names.get(c, c), amt)

    rows: list[dict[str, Any]] = []
    for code, bel in totals.items():
        rows.append(
            {
                "Kode": code,
                "Navn": names.get(code, code),
                "Belop": dec_round(bel),
                "Diff": Decimal("0"),
            }
        )

    rows = sorted(rows, key=lambda r: abs(r["Belop"]), reverse=True)
    if top_n is not None:
        try:
            n = int(top_n)
        except Exception:
            n = 0
        if n > 0:
            rows = rows[:n]

    return pd.DataFrame(rows, columns=["Kode", "Navn", "Belop", "Diff"])


def build_monthly_summary(path: str | Path) -> pd.DataFrame:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    innsendinger = _get(payload, ["mottatt", "opplysningspliktig", "innsendinger"], [])
    rows: list[dict[str, Any]] = []

    if isinstance(innsendinger, list):
        for inn in innsendinger:
            if not isinstance(inn, dict):
                continue
            maaned = str(inn.get("kalendermaaned") or "").strip()
            if not maaned:
                continue

            status = str(inn.get("status") or "").strip().upper()
            if status and status != "GODKJENT":
                continue

            totals = inn.get("mottattAvgiftOgTrekkTotalt") or {}
            rows.append(
                {
                    "kalendermaaned": maaned,
                    "innsendinger": 1,
                    "antallInntektsmottakere": int(inn.get("antallInntektsmottakere") or 0),
                    "sumArbeidsgiveravgift": dec_round(to_decimal(_get(totals, ["sumArbeidsgiveravgift"], 0))),
                    "sumForskuddstrekk": dec_round(to_decimal(_get(totals, ["sumForskuddstrekk"], 0))),
                    "sumSkattetrekk": dec_round(to_decimal(_get(totals, ["sumSkattetrekk"], 0))),
                    "sumFinansskattLoenn": dec_round(to_decimal(_get(totals, ["sumFinansskattLoenn"], 0))),
                }
            )

    if not rows:
        per = payload.get("periode")
        if isinstance(per, dict):
            maaned = str(per.get("kalendermaaned") or "").strip()
            totals = per.get("mottattAvgiftOgTrekkTotalt") or {}
            if maaned and isinstance(totals, dict):
                rows.append(
                    {
                        "kalendermaaned": maaned,
                        "innsendinger": 1,
                        "antallInntektsmottakere": 0,
                        "sumArbeidsgiveravgift": dec_round(to_decimal(_get(totals, ["sumArbeidsgiveravgift"], 0))),
                        "sumForskuddstrekk": dec_round(to_decimal(_get(totals, ["sumForskuddstrekk"], 0))),
                        "sumSkattetrekk": dec_round(to_decimal(_get(totals, ["sumSkattetrekk"], 0))),
                        "sumFinansskattLoenn": dec_round(to_decimal(_get(totals, ["sumFinansskattLoenn"], 0))),
                    }
                )

    if not rows:
        return pd.DataFrame(
            columns=[
                "kalendermaaned",
                "sumArbeidsgiveravgift",
                "sumForskuddstrekk",
                "sumSkattetrekk",
                "sumFinansskattLoenn",
                "antallInntektsmottakere",
                "innsendinger",
                "Maaned",
                "AGA",
                "Forskuddstrekk",
                "Skattetrekk",
                "FinansskattLoenn",
            ]
        )

    df = pd.DataFrame(rows)
    grouped = (
        df.groupby("kalendermaaned", as_index=False)
        .agg(
            innsendinger=("innsendinger", "sum"),
            antallInntektsmottakere=("antallInntektsmottakere", "max"),
            sumArbeidsgiveravgift=("sumArbeidsgiveravgift", "sum"),
            sumForskuddstrekk=("sumForskuddstrekk", "sum"),
            sumSkattetrekk=("sumSkattetrekk", "sum"),
            sumFinansskattLoenn=("sumFinansskattLoenn", "sum"),
        )
        .sort_values("kalendermaaned")
        .reset_index(drop=True)
    )

    for c in (
        "sumArbeidsgiveravgift",
        "sumForskuddstrekk",
        "sumSkattetrekk",
        "sumFinansskattLoenn",
    ):
        grouped[c] = grouped[c].map(to_decimal).map(dec_round)

    grouped["Maaned"] = grouped["kalendermaaned"]
    grouped["AGA"] = grouped["sumArbeidsgiveravgift"]
    grouped["Forskuddstrekk"] = grouped["sumForskuddstrekk"]
    grouped["Skattetrekk"] = grouped["sumSkattetrekk"]
    grouped["FinansskattLoenn"] = grouped["sumFinansskattLoenn"]
    return grouped
