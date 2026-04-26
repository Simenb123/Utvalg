"""rl_mapping_drift.py — kontroll for ulik RL-mapping år↔fjor.

Ren beregningsmodul — ingen GUI-avhengigheter. Finner kontoer hvor
regnskapslinje-mappingen avviker mellom inneværende år og fjoråret,
enten fordi intervallene er endret, fordi klient-overrides er endret,
eller fordi kontoen kun finnes i ett av årene.

Brukes av analysefanens mapping-varsel og egen detaljdialog for å la
revisor se materialitet bak drift-funnene.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

import pandas as pd


DRIFT_CHANGED = "changed_mapping"
DRIFT_ONLY_CURRENT = "only_current"
DRIFT_ONLY_PRIOR = "only_prior"


@dataclass(frozen=True)
class MappingDrift:
    konto: str
    kontonavn: str
    regnr_aar: Optional[int]
    rl_navn_aar: str
    ub_aar: float
    regnr_fjor: Optional[int]
    rl_navn_fjor: str
    ub_fjor: float
    kind: str

    @property
    def materialitet(self) -> float:
        return max(abs(self.ub_aar), abs(self.ub_fjor))


def _norm_konto(v: Any) -> str:
    return str(v or "").strip()


def _to_float(v: Any) -> float:
    try:
        if v is None:
            return 0.0
        if isinstance(v, float) and v != v:  # NaN
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _resolve_sb_cols(df: pd.DataFrame) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in df.columns:
        cl = str(c).strip().lower()
        if cl == "konto" and "konto" not in out:
            out["konto"] = c
        elif cl == "kontonavn" and "kontonavn" not in out:
            out["kontonavn"] = c
        elif cl == "ub" and "ub" not in out:
            out["ub"] = c
    return out


def _build_account_info(
    sb_df: Optional[pd.DataFrame],
) -> tuple[dict[str, float], dict[str, str]]:
    """Returnerer (ub-per-konto, navn-per-konto) fra en SB-DataFrame."""
    ub_map: dict[str, float] = {}
    navn_map: dict[str, str] = {}
    if sb_df is None or not isinstance(sb_df, pd.DataFrame) or sb_df.empty:
        return ub_map, navn_map
    cols = _resolve_sb_cols(sb_df)
    konto_c = cols.get("konto")
    if not konto_c:
        return ub_map, navn_map
    ub_c = cols.get("ub")
    navn_c = cols.get("kontonavn")
    for _, row in sb_df.iterrows():
        konto = _norm_konto(row.get(konto_c))
        if not konto:
            continue
        if ub_c is not None:
            ub_map[konto] = ub_map.get(konto, 0.0) + _to_float(row.get(ub_c))
        if navn_c is not None and konto not in navn_map:
            navn_map[konto] = str(row.get(navn_c) or "")
    return ub_map, navn_map


def detect_mapping_drift(
    *,
    client: str | None,
    year: str | int | None,
    sb_df: Optional[pd.DataFrame] = None,
    sb_prev_df: Optional[pd.DataFrame] = None,
    intervals: Optional[pd.DataFrame] = None,
    regnskapslinjer: Optional[pd.DataFrame] = None,
    current_overrides: Optional[dict[str, int]] = None,
    prior_overrides: Optional[dict[str, int]] = None,
    accepted_drift: Optional[dict[str, dict[str, int | None]]] = None,
) -> list[MappingDrift]:
    """Finn kontoer hvor RL-mapping avviker mellom inneværende og fjor.

    Tre kategorier:
      - ``changed_mapping``: konto finnes i begge år, men regnr er ulik
      - ``only_current``: konto finnes kun i inneværende års SB
      - ``only_prior``: konto finnes kun i fjorårets SB

    Alle argumenter etter ``client``/``year`` kan injiseres for testing.
    Hvis de er ``None`` lastes de via produksjons-API-ene.
    """
    import regnskapslinje_mapping_service as _rl_svc

    year_s = str(year) if year is not None else ""

    if sb_prev_df is None and client and year_s:
        try:
            import previous_year_comparison
            sb_prev_df = previous_year_comparison.load_previous_year_sb(client, year_s)
        except Exception:
            sb_prev_df = None

    if current_overrides is None:
        try:
            import src.shared.regnskap.client_overrides as _rco
            current_overrides = _rco.load_account_overrides(client, year=year_s) if client else {}
        except Exception:
            current_overrides = {}
    if prior_overrides is None:
        try:
            import src.shared.regnskap.client_overrides as _rco
            prior_overrides = _rco.load_prior_year_overrides(client, year_s) if client else {}
        except Exception:
            prior_overrides = {}

    try:
        prev_year_int = str(int(year_s) - 1) if year_s else ""
    except (ValueError, TypeError):
        prev_year_int = ""
    if accepted_drift is None:
        try:
            import src.shared.regnskap.client_overrides as _rco
            if client and year_s and prev_year_int:
                accepted_drift = _rco.load_accepted_mapping_drift(
                    client, year_s, prev_year_int,
                )
            else:
                accepted_drift = {}
        except Exception:
            accepted_drift = {}

    # Bygg begge kontekster. Intervaller/RL er felles; overrides varierer.
    ctx_current = _rl_svc.load_rl_mapping_context(
        client=client, year=year_s,
        intervals=intervals, regnskapslinjer=regnskapslinjer,
        account_overrides=current_overrides,
    )
    try:
        prev_year = str(int(year_s) - 1) if year_s else ""
    except (ValueError, TypeError):
        prev_year = ""
    ctx_prior = _rl_svc.load_rl_mapping_context(
        client=client, year=prev_year or year_s,
        intervals=intervals, regnskapslinjer=regnskapslinjer,
        account_overrides=prior_overrides,
    )

    cur_ub, cur_navn = _build_account_info(sb_df)
    prev_ub, prev_navn = _build_account_info(sb_prev_df)

    accounts = set(cur_ub.keys()) | set(prev_ub.keys())
    if not accounts:
        return []

    resolved_cur = _rl_svc.resolve_accounts_to_rl(list(accounts), context=ctx_current)
    resolved_prev = _rl_svc.resolve_accounts_to_rl(list(accounts), context=ctx_prior)

    def _by_konto(resolved: pd.DataFrame) -> dict[str, tuple[Optional[int], str]]:
        out: dict[str, tuple[Optional[int], str]] = {}
        if resolved is None or resolved.empty:
            return out
        for _, row in resolved.iterrows():
            konto = _norm_konto(row.get("konto"))
            if not konto:
                continue
            status = str(row.get("mapping_status") or "")
            if status == "unmapped":
                out[konto] = (None, "")
                continue
            regnr_raw = row.get("regnr")
            try:
                regnr_int = int(regnr_raw) if pd.notna(regnr_raw) else None
            except (TypeError, ValueError):
                regnr_int = None
            navn = str(row.get("regnskapslinje") or "")
            out[konto] = (regnr_int, navn)
        return out

    cur_map = _by_konto(resolved_cur)
    prev_map = _by_konto(resolved_prev)

    accepted = accepted_drift or {}
    drifts: list[MappingDrift] = []
    for konto in sorted(accounts, key=lambda k: (len(k), k)):
        in_cur = konto in cur_ub
        in_prev = konto in prev_ub
        regnr_cur, rl_cur = cur_map.get(konto, (None, ""))
        regnr_prev, rl_prev = prev_map.get(konto, (None, ""))
        ub_cur = cur_ub.get(konto, 0.0)
        ub_prev = prev_ub.get(konto, 0.0)

        accepted_pair = accepted.get(konto)
        if accepted_pair is not None:
            if (
                accepted_pair.get("regnr_cur") == regnr_cur
                and accepted_pair.get("regnr_prev") == regnr_prev
            ):
                continue
        navn = cur_navn.get(konto) or prev_navn.get(konto) or ""

        if in_cur and in_prev:
            if regnr_cur == regnr_prev:
                continue
            kind = DRIFT_CHANGED
        elif in_cur and not in_prev:
            if abs(ub_cur) < 0.005:
                continue
            # Nye kontoer med gyldig mapping i år er ikke drift — bare nye
            # kontoer. Kun umappede nye kontoer er et reelt problem revisor
            # bør handle på.
            if regnr_cur is not None:
                continue
            kind = DRIFT_ONLY_CURRENT
            regnr_prev, rl_prev = None, ""
        elif in_prev and not in_cur:
            if abs(ub_prev) < 0.005:
                continue
            # Forsvunne kontoer med gyldig mapping i fjor er heller ikke
            # drift — bare avsluttede kontoer. Kun umappede fra fjor tas med.
            if regnr_prev is not None:
                continue
            kind = DRIFT_ONLY_PRIOR
            regnr_cur, rl_cur = None, ""
        else:
            continue

        drifts.append(MappingDrift(
            konto=konto,
            kontonavn=navn,
            regnr_aar=regnr_cur,
            rl_navn_aar=rl_cur,
            ub_aar=ub_cur,
            regnr_fjor=regnr_prev,
            rl_navn_fjor=rl_prev,
            ub_fjor=ub_prev,
            kind=kind,
        ))

    drifts.sort(key=lambda d: (-d.materialitet, d.konto))
    return drifts


def apply_use_prior_mapping(
    *, client: str, year: str | int,
    drifts: Iterable[MappingDrift],
) -> int:
    """Sett årets override[konto] = regnr_fjor for valgte drift-rader.

    Returnerer antall kontoer som ble oppdatert.
    Kontoer uten regnr_fjor (umappet i fjor) hoppes over.
    """
    import src.shared.regnskap.client_overrides as _rco

    year_s = str(year)
    current = _rco.load_account_overrides(client, year=year_s)
    updated = 0
    for d in drifts:
        if d.regnr_fjor is None:
            continue
        if current.get(d.konto) == d.regnr_fjor:
            continue
        current[d.konto] = int(d.regnr_fjor)
        updated += 1
    if updated:
        _rco.save_account_overrides(client, current, year=year_s)
    return updated


def apply_use_current_mapping(
    *, client: str, year: str | int,
    drifts: Iterable[MappingDrift],
) -> int:
    """Sett fjorårets override[konto] = regnr_aar for valgte drift-rader."""
    import src.shared.regnskap.client_overrides as _rco

    try:
        prev_year = str(int(year) - 1)
    except (ValueError, TypeError):
        return 0
    prev = _rco.load_account_overrides(client, year=prev_year)
    updated = 0
    for d in drifts:
        if d.regnr_aar is None:
            continue
        if prev.get(d.konto) == d.regnr_aar:
            continue
        prev[d.konto] = int(d.regnr_aar)
        updated += 1
    if updated:
        _rco.save_account_overrides(client, prev, year=prev_year)
    return updated


def apply_accept_drift(
    *, client: str, year: str | int,
    drifts: Iterable[MappingDrift],
) -> int:
    """Marker valgte drift-rader som aksepterte. Returnerer antall lagret."""
    import src.shared.regnskap.client_overrides as _rco

    try:
        prev_year = str(int(year) - 1)
    except (ValueError, TypeError):
        return 0
    year_s = str(year)
    count = 0
    for d in drifts:
        _rco.set_accepted_mapping_drift(
            client, year_s, prev_year,
            konto=d.konto, regnr_cur=d.regnr_aar, regnr_prev=d.regnr_fjor,
        )
        count += 1
    return count


def summary_text(drifts: Iterable[MappingDrift]) -> str:
    """Kort tekst egnet for mapping-warning-banneret.

    Eksempel: "3 kontoer endret RL-mapping siden fjor (sum 1,2 MNOK)".
    """
    drifts_list = list(drifts)
    if not drifts_list:
        return ""
    n = len(drifts_list)
    total = sum(d.materialitet for d in drifts_list)
    if total >= 1_000_000:
        beloep = f"{total / 1_000_000:.1f} MNOK".replace(".", ",")
    elif total >= 1_000:
        beloep = f"{total / 1_000:.0f} kNOK"
    else:
        beloep = f"{total:.0f} NOK"
    changed = sum(1 for d in drifts_list if d.kind == DRIFT_CHANGED)
    if changed == n:
        return f"{n} kontoer endret RL-mapping siden fjor (sum {beloep})"
    return f"{n} kontoer med mapping-drift siden fjor (sum {beloep})"
