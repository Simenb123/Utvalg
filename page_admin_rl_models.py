from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

import regnskap_config

from page_admin_helpers import (
    _clean_text,
)


@dataclass(frozen=True)
class RLBaselineRow:
    """En felles RL-baseline-rad bygget fra delt JSON-baseline.

    Brukes som viewmodel for ``Regnskapslinjer``-fanen. Inneholder baseline
    og om kontoen har overlay. Er ikke avhengig av klient/session/SB.
    """

    regnr: str
    regnskapslinje: str
    sumpost: bool
    formel: str
    sumnivaa: str
    delsumnr: str
    delsumlinje: str
    sumnr: str
    sumlinje: str
    sumnr2: str
    sumlinje2: str
    sluttsumnr: str
    sluttsumlinje: str
    resultat_balanse: str
    kontointervall_text: str
    sumtilknytning_text: str
    has_overlay: bool


def _raw_cell_text(value: object) -> str:
    """Normaliser en celleverdi til en lesbar streng."""
    if value is None:
        return ""
    try:
        if pd.isna(value):  # type: ignore[arg-type]
            return ""
    except Exception:
        pass
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    return str(value).strip()


def _format_kontointervall_text(intervals: list[tuple[int, int]]) -> str:
    """Formater liste av (fra, til)-par til lesbar streng: '1000-1019, 1020-1069'."""
    if not intervals:
        return ""
    parts: list[str] = []
    for fra, til in intervals:
        if fra == til:
            parts.append(str(int(fra)))
        else:
            parts.append(f"{int(fra)}-{int(til)}")
    return ", ".join(parts)


def _format_sumtilknytning_text(row: RLBaselineRow) -> str:
    """Bygg en lesbar foreldre-kjede fra hierarkifeltene."""
    chain: list[str] = []
    for nr, linje in (
        (row.delsumnr, row.delsumlinje),
        (row.sumnr, row.sumlinje),
        (row.sumnr2, row.sumlinje2),
        (row.sluttsumnr, row.sluttsumlinje),
    ):
        nr_text = _clean_text(nr)
        if not nr_text:
            continue
        label = _clean_text(linje)
        chain.append(f"{nr_text} {label}".strip() if label else nr_text)
    return " → ".join(chain)


def _format_baseline_source_line(status: Any) -> str:
    """Bygg en lesbar linje for den aktive delte baseline-filen."""
    path = getattr(status, "regnskapslinjer_json_path", None) or getattr(status, "regnskapslinjer_path", None)
    if path is None:
        return "Felles baseline: (ikke funnet i datamappen)"
    return f"Felles baseline: {path}"

def _format_overlay_source_line(path_text: str) -> str:
    return f"Finjustering: {path_text}" if path_text else "Finjustering: (ikke lagret)"


LINJETYPE_SUMPOST = "Sumpost"
LINJETYPE_VANLIG = "Vanlig linje"
_LINJETYPE_VALUES = (LINJETYPE_SUMPOST, LINJETYPE_VANLIG)

RL_FILTER_ALLE = "Alle"
RL_FILTER_VANLIG = "Skjul sumposter"
RL_FILTER_SUMPOST = "Bare sumposter"
RL_FILTER_MED_FIN = "Med finjustering"
RL_FILTER_UTEN_FIN = "Uten finjustering"
RL_FILTER_VALUES = (
    RL_FILTER_ALLE,
    RL_FILTER_VANLIG,
    RL_FILTER_SUMPOST,
    RL_FILTER_MED_FIN,
    RL_FILTER_UTEN_FIN,
)


def _parse_kontointervall_text(text: str) -> tuple[list[tuple[int, int]], list[str]]:
    """Parse multiline kontointervall-tekst til liste av (fra, til) og liste over ugyldige tokens.

    Tillatt format per linje: '1000' eller '1000-1099'. Whitespace ignoreres.
    Hvis fra > til snus paret automatisk.
    """

    intervals: list[tuple[int, int]] = []
    errors: list[str] = []
    for raw in (text or "").splitlines():
        token = _clean_text(raw)
        if not token:
            continue
        if "-" in token:
            left, _, right = token.partition("-")
            try:
                fra = int(left.strip())
                til = int(right.strip())
            except ValueError:
                errors.append(token)
                continue
        else:
            try:
                fra = int(token)
            except ValueError:
                errors.append(token)
                continue
            til = fra
        if fra > til:
            fra, til = til, fra
        intervals.append((fra, til))
    return intervals, errors


def _rl_row_matches_filter(*, sumpost: bool, has_overlay: bool, mode: str) -> bool:
    if mode == RL_FILTER_VANLIG:
        return not sumpost
    if mode == RL_FILTER_SUMPOST:
        return sumpost
    if mode == RL_FILTER_MED_FIN:
        return has_overlay
    if mode == RL_FILTER_UTEN_FIN:
        return not has_overlay
    return True


def build_rl_baseline_rows(
    *,
    overlay_regnrs: set[str] | None = None,
) -> list[RLBaselineRow]:
    """Bygg felles RL-baseline-rader fra delt JSON-baseline.

    Leser ``regnskapslinjer.json`` og ``kontoplan_mapping.json`` og
    returnerer én rad per regnskapslinje — inkludert sumposter — med
    baseline-felter, lesbart kontointervall og flagg for overlay-treff.
    """
    overlay_set = {_clean_text(r) for r in (overlay_regnrs or set())}

    try:
        df_rl = regnskap_config.load_regnskapslinjer()
    except Exception:
        return []

    intervals_by_regnr: dict[str, list[tuple[int, int]]] = {}
    try:
        from regnskap_mapping import normalize_intervals

        df_km = regnskap_config.load_kontoplan_mapping()
        df_km_norm = normalize_intervals(df_km)
        for _, ir in df_km_norm.iterrows():
            key = str(int(ir["regnr"]))
            intervals_by_regnr.setdefault(key, []).append((int(ir["fra"]), int(ir["til"])))
        for key in intervals_by_regnr:
            intervals_by_regnr[key].sort()
    except Exception:
        intervals_by_regnr = {}

    cols = {str(c).strip().lower(): c for c in df_rl.columns}

    def col(*names: str) -> str | None:
        for name in names:
            if name.lower() in cols:
                return cols[name.lower()]
        return None

    c_nr = col("nr", "regnr", "regnnr")
    c_name = col("regnskapslinje", "linje", "tekst")
    c_sum = col("sumpost", "sum")
    c_formula = col("formel", "formula")
    c_sumnivaa = col("sumnivå", "sumnivaa")
    c_delsumnr = col("delsumnr")
    c_delsumlinje = col("delsumlinje")
    c_sumnr = col("sumnr")
    c_sumlinje = col("sumlinje")
    c_sumnr2 = col("sumnr2")
    c_sumlinje2 = col("sumlinje2")
    c_sluttsumnr = col("sluttsumnr")
    c_sluttsumlinje = col("sluttsumlinje")
    c_rb = col("resultat/balanse", "resultat_balanse", "rb")

    rows: list[RLBaselineRow] = []
    for _, raw in df_rl.iterrows():
        regnr_text = _raw_cell_text(raw.get(c_nr)) if c_nr else ""
        if not regnr_text:
            continue
        try:
            regnr_int = int(float(regnr_text))
        except Exception:
            continue
        regnr_str = str(regnr_int)
        sumpost_raw = _raw_cell_text(raw.get(c_sum)) if c_sum else ""
        sumpost = sumpost_raw.strip().lower() in {"ja", "yes", "true", "1"}

        partial = RLBaselineRow(
            regnr=regnr_str,
            regnskapslinje=_raw_cell_text(raw.get(c_name)) if c_name else "",
            sumpost=sumpost,
            formel=_raw_cell_text(raw.get(c_formula)) if c_formula else "",
            sumnivaa=_raw_cell_text(raw.get(c_sumnivaa)) if c_sumnivaa else "",
            delsumnr=_raw_cell_text(raw.get(c_delsumnr)) if c_delsumnr else "",
            delsumlinje=_raw_cell_text(raw.get(c_delsumlinje)) if c_delsumlinje else "",
            sumnr=_raw_cell_text(raw.get(c_sumnr)) if c_sumnr else "",
            sumlinje=_raw_cell_text(raw.get(c_sumlinje)) if c_sumlinje else "",
            sumnr2=_raw_cell_text(raw.get(c_sumnr2)) if c_sumnr2 else "",
            sumlinje2=_raw_cell_text(raw.get(c_sumlinje2)) if c_sumlinje2 else "",
            sluttsumnr=_raw_cell_text(raw.get(c_sluttsumnr)) if c_sluttsumnr else "",
            sluttsumlinje=_raw_cell_text(raw.get(c_sluttsumlinje)) if c_sluttsumlinje else "",
            resultat_balanse=_raw_cell_text(raw.get(c_rb)) if c_rb else "",
            kontointervall_text=_format_kontointervall_text(intervals_by_regnr.get(regnr_str, [])),
            sumtilknytning_text="",
            has_overlay=regnr_str in overlay_set,
        )
        sumtilknytning_text = _format_sumtilknytning_text(partial)
        rows.append(
            RLBaselineRow(
                regnr=partial.regnr,
                regnskapslinje=partial.regnskapslinje,
                sumpost=partial.sumpost,
                formel=partial.formel,
                sumnivaa=partial.sumnivaa,
                delsumnr=partial.delsumnr,
                delsumlinje=partial.delsumlinje,
                sumnr=partial.sumnr,
                sumlinje=partial.sumlinje,
                sumnr2=partial.sumnr2,
                sumlinje2=partial.sumlinje2,
                sluttsumnr=partial.sluttsumnr,
                sluttsumlinje=partial.sluttsumlinje,
                resultat_balanse=partial.resultat_balanse,
                kontointervall_text=partial.kontointervall_text,
                sumtilknytning_text=sumtilknytning_text,
                has_overlay=partial.has_overlay,
            )
        )

    try:
        rows.sort(key=lambda r: int(r.regnr))
    except Exception:
        rows.sort(key=lambda r: r.regnr)
    return rows
