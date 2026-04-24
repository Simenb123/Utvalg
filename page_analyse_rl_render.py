"""page_analyse_rl_render.py

GUI-rendering av RL-pivot: headings-oppdatering og refresh_rl_pivot
(hovedflyt for å fylle pivot_tree i Regnskapslinje-modus).

Utskilt fra page_analyse_rl.py. Re-eksportert via page_analyse_rl som
fasade for bakoverkompatibilitet.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd

import formatting

from src.shared.columns_vocabulary import heading as _vocab_heading

from page_analyse_rl_data import (
    _load_current_client_account_overrides,
    _resolve_analysis_sb_views,
    ensure_sb_prev_loaded,
)
from page_analyse_rl_drilldown import get_selected_rl_rows
from page_analyse_rl_pivot import (
    _add_adjustment_columns,
    _format_mapping_warning,
    build_rl_pivot,
    get_unmapped_rl_accounts,
)

log = logging.getLogger("app")

# Kolonnenavn brukt i treeview (vises som headings i RL-modus).
# Interne kolonne-IDer er uendret — kun brukerrettet label endres.
# Labels formatteres dynamisk via felles vokabular (heading()) i
# update_pivot_headings/_rl_headings_with_year. Konstanten under er
# "uten år"-fallback som speiler heading()-output når year=None.
RL_PIVOT_HEADINGS = (
    "Nr",
    "Regnskapslinje",
    "",                       # OK — ikke relevant for regnskapslinjer
    "IB",                     # heading("IB")
    "Δ UB-IB",                # heading("Endring")
    "UB",                     # heading("UB")
    "Tilleggspostering",      # heading("AO_belop")
    "UB før ÅO",              # heading("UB_for_ao")
    "UB etter ÅO",            # heading("UB_etter_ao")
    "Antall",                 # heading("Antall")
    "UB i fjor",              # heading("UB_fjor")
    "Δ UB",                   # heading("Endring_fjor")
    "Δ % UB",                 # heading("Endring_pct")
    "BRREG",                  # heading("BRREG")
    "Avvik mot BRREG",        # heading("Avvik_brreg")
    "Avvik % mot BRREG",      # heading("Avvik_brreg_pct")
)
# Standard konto-modus headings (for å tilbakestille)
KONTO_PIVOT_HEADINGS = (
    "Konto", "Kontonavn", "OK", "", "", "Sum", "", "", "", "Antall",
    "", "", "", "", "", "",
)
# HB-konto: ren HB-pivot – heading "HB-bevegelse" istedenfor "Sum"
HB_KONTO_PIVOT_HEADINGS = (
    "Konto", "Kontonavn", "OK", "", "", "HB-bevegelse", "", "", "", "Antall",
    "", "", "", "", "", "",
)


def _resolve_active_year() -> Optional[int]:
    """Les aktivt regnskapsår fra session som heltall når mulig."""
    try:
        import session as _session
        raw = getattr(_session, "year", None)
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _resolve_brreg_year(brreg_data: Any) -> Optional[int]:
    """Hent nyeste BRREG-regnskapsår som int fra _nk_brreg_data."""
    if not isinstance(brreg_data, dict) or not brreg_data:
        return None
    available = brreg_data.get("available_years")
    if isinstance(available, list) and available:
        try:
            return int(available[0])
        except (TypeError, ValueError):
            pass
    raw = brreg_data.get("regnskapsaar")
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _rl_headings_with_year(
    year: Optional[int],
    *,
    brreg_year: Optional[int] = None,
    fjor_source: Optional[str] = None,
) -> tuple[str, ...]:
    """Bygg RL-headings via felles vokabular (heading()).

    Når ``fjor_source == "brreg"`` får UB-fjor-kolonnen suffikset
    ``(BRREG)`` som diskret kildeindikasjon.

    Indekser matcher kolonne-rekkefølgen i RL-pivot_tree:
        0=Nr, 1=Regnskapslinje, 2=OK(blank for RL), 3=IB, 4=Endring,
        5=Sum/UB, 6=AO_belop, 7=UB_for_ao, 8=UB_etter_ao, 9=Antall,
        10=UB_fjor, 11=Endring_fjor, 12=Endring_pct,
        13=BRREG, 14=Avvik_brreg, 15=Avvik_brreg_pct
    """
    headings = [
        "Nr",
        "Regnskapslinje",
        "",                                                 # OK — ikke relevant for RL
        _vocab_heading("IB", year=year),
        _vocab_heading("Endring", year=year),
        _vocab_heading("UB", year=year),
        _vocab_heading("AO_belop"),
        _vocab_heading("UB_for_ao"),
        _vocab_heading("UB_etter_ao"),
        _vocab_heading("Antall"),
        _vocab_heading("UB_fjor", year=year),
        _vocab_heading("Endring_fjor", year=year),
        _vocab_heading("Endring_pct", year=year),
        _vocab_heading("BRREG", brreg_year=brreg_year),
        _vocab_heading("Avvik_brreg"),
        _vocab_heading("Avvik_brreg_pct"),
    ]
    if fjor_source == "brreg":
        headings[10] = f"{headings[10]} (BRREG)"
    return tuple(headings)


def _sb_konto_headings_with_year(year: Optional[int]) -> tuple[str, ...]:
    """SB-konto headings via felles vokabular."""
    return (
        "Konto",
        "Kontonavn",
        "OK",
        "",                                                 # IB ikke vist
        _vocab_heading("Endring", year=year),               # Bevegelse fallback
        _vocab_heading("UB", year=year),                    # Sum = UB aktivt år
        "",                                                 # AO_belop
        "",                                                 # UB_for_ao
        "",                                                 # UB_etter_ao
        _vocab_heading("Antall"),
        _vocab_heading("UB_fjor", year=year),
        _vocab_heading("Endring_fjor", year=year),
        _vocab_heading("Endring_pct", year=year),
        "", "", "",                                         # BRREG, Avvik_brreg, Avvik_brreg_pct
    )


def update_pivot_headings(*, page: Any, mode: str) -> None:
    """Oppdater kolonneoverskrifter i pivot_tree basert på modus.

    mode = "Regnskapslinje" → RL_PIVOT_HEADINGS (med årstall injisert)
    mode = "SB-konto"       → komparativ konto-visning med årstall
    mode = "HB-konto"       → ren HB-pivot ("HB-bevegelse")
    mode = "Konto" (legacy) eller "Saldobalanse" (GUI-label) → behandles som SB-konto
    """
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return

    if mode in ("Konto", "Saldobalanse"):
        mode = "SB-konto"

    brreg_year = _resolve_brreg_year(getattr(page, "_nk_brreg_data", None))
    fjor_source = getattr(page, "_rl_fjor_source", None)

    if mode == "Regnskapslinje":
        headings = _rl_headings_with_year(
            _resolve_active_year(),
            brreg_year=brreg_year,
            fjor_source=fjor_source,
        )
    elif mode == "SB-konto":
        headings = _sb_konto_headings_with_year(_resolve_active_year())
    elif mode == "HB-konto":
        headings = HB_KONTO_PIVOT_HEADINGS
    else:
        headings = KONTO_PIVOT_HEADINGS
    cols = (
        "Konto",
        "Kontonavn",
        "OK",
        "IB",
        "Endring",
        "Sum",
        "AO_belop",
        "UB_for_ao",
        "UB_etter_ao",
        "Antall",
        "UB_fjor",
        "Endring_fjor",
        "Endring_pct",
        "BRREG",
        "Avvik_brreg",
        "Avvik_brreg_pct",
    )  # interne kolonne-IDer

    for col_id, heading in zip(cols, headings):
        try:
            tree.heading(col_id, text=heading)
        except Exception:
            pass

    # Sjekk om fjorårsdata er tilgjengelig (egen SB ELLER BRREG-fallback)
    has_prev = bool(
        getattr(page, "_rl_sb_prev_df", None) is not None
        or getattr(page, "_rl_fjor_source", None) == "brreg"
    )
    has_brreg = bool(getattr(page, "_nk_brreg_data", None))

    # Juster bredder for RL-modus (defaults – auto-fit kjøres etter data er fylt)
    if mode == "Regnskapslinje":
        try:
            # Nr-kolonnen er smal — bare et 2-5-sifret RL-nummer
            tree.column("Konto",    width=44,  minwidth=34,  stretch=False, anchor="e")
            # Regnskapslinje-navn trenger bredde
            tree.column("Kontonavn", width=290, minwidth=160, stretch=True,  anchor="w")
            tree.column("IB",       width=110, minwidth=75,  stretch=False, anchor="e")
            tree.column("Endring",  width=110, minwidth=75,  stretch=False, anchor="e")
            tree.column("Sum",      width=115, minwidth=80,  stretch=False, anchor="e")
            tree.column("AO_belop", width=125, minwidth=90,  stretch=False, anchor="e")
            tree.column("UB_for_ao", width=120, minwidth=90, stretch=False, anchor="e")
            tree.column("UB_etter_ao", width=120, minwidth=90, stretch=False, anchor="e")
            # Antall trenger ikke mye plass
            tree.column("Antall",   width=48,  minwidth=38,  stretch=False, anchor="e")
        except Exception:
            pass
        # Fjorårskolonner: vis/skjul basert på tilgjengelige data
        if has_prev:
            try:
                tree.column("UB_fjor", width=115, minwidth=80, anchor="e")
                tree.column("Endring_fjor", width=115, minwidth=80, anchor="e")
                tree.column("Endring_pct", width=80, minwidth=60, anchor="e")
            except Exception:
                pass
        else:
            try:
                tree.column("UB_fjor", width=0, minwidth=0, stretch=False)
                tree.column("Endring_fjor", width=0, minwidth=0, stretch=False)
                tree.column("Endring_pct", width=0, minwidth=0, stretch=False)
            except Exception:
                pass
        # BRREG-kolonner: vis/skjul basert på om BRREG-data er hentet
        if has_brreg:
            try:
                tree.column("BRREG", width=115, minwidth=80, anchor="e")
                tree.column("Avvik_brreg", width=115, minwidth=80, anchor="e")
                tree.column("Avvik_brreg_pct", width=90, minwidth=60, anchor="e")
            except Exception:
                pass
        else:
            try:
                tree.column("BRREG", width=0, minwidth=0, stretch=False)
                tree.column("Avvik_brreg", width=0, minwidth=0, stretch=False)
                tree.column("Avvik_brreg_pct", width=0, minwidth=0, stretch=False)
            except Exception:
                pass
    elif mode == "SB-konto":
        try:
            tree.column("Konto", width=80, minwidth=50, stretch=False, anchor="w")
            tree.column("Kontonavn", width=220, minwidth=120, stretch=True, anchor="w")
            tree.column("IB", width=0, minwidth=0, stretch=False, anchor="e")
            tree.column("Endring", width=115 if not has_prev else 0, minwidth=75 if not has_prev else 0, stretch=False, anchor="e")
            tree.column("Sum", width=115, minwidth=80, stretch=False, anchor="e")
            tree.column("AO_belop", width=0, minwidth=0, stretch=False, anchor="e")
            tree.column("UB_for_ao", width=0, minwidth=0, stretch=False, anchor="e")
            tree.column("UB_etter_ao", width=0, minwidth=0, stretch=False, anchor="e")
            tree.column("Antall", width=70, minwidth=50, stretch=False, anchor="e")
        except Exception:
            pass
        if has_prev:
            try:
                tree.column("UB_fjor", width=115, minwidth=80, anchor="e")
                tree.column("Endring_fjor", width=115, minwidth=80, anchor="e")
                tree.column("Endring_pct", width=80, minwidth=60, anchor="e")
            except Exception:
                pass
        else:
            try:
                tree.column("UB_fjor", width=0, minwidth=0, stretch=False)
                tree.column("Endring_fjor", width=0, minwidth=0, stretch=False)
                tree.column("Endring_pct", width=0, minwidth=0, stretch=False)
            except Exception:
                pass
        try:
            tree.column("BRREG", width=0, minwidth=0, stretch=False)
            tree.column("Avvik_brreg", width=0, minwidth=0, stretch=False)
            tree.column("Avvik_brreg_pct", width=0, minwidth=0, stretch=False)
        except Exception:
            pass
    else:
        # HB-konto (og legacy fallback)
        try:
            tree.column("Konto", width=80, minwidth=50, stretch=False, anchor="w")
            tree.column("Kontonavn", width=220, minwidth=120, stretch=True, anchor="w")
            tree.column("IB", width=0, minwidth=0, stretch=False, anchor="e")
            tree.column("Endring", width=0, minwidth=0, stretch=False, anchor="e")
            tree.column("Sum", width=115, minwidth=80, stretch=False, anchor="e")
            tree.column("AO_belop", width=0, minwidth=0, stretch=False, anchor="e")
            tree.column("UB_for_ao", width=0, minwidth=0, stretch=False, anchor="e")
            tree.column("UB_etter_ao", width=0, minwidth=0, stretch=False, anchor="e")
            tree.column("Antall", width=70, minwidth=50, stretch=False, anchor="e")
            tree.column("UB_fjor", width=0, minwidth=0, stretch=False)
            tree.column("Endring_fjor", width=0, minwidth=0, stretch=False)
            tree.column("Endring_pct", width=0, minwidth=0, stretch=False)
            tree.column("BRREG", width=0, minwidth=0, stretch=False)
            tree.column("Avvik_brreg", width=0, minwidth=0, stretch=False)
            tree.column("Avvik_brreg_pct", width=0, minwidth=0, stretch=False)
        except Exception:
            pass


def refresh_rl_pivot(*, page: Any) -> None:
    """Fyll pivot_tree med regnskapslinjer (IB, UB, Antall)."""
    # Per-stage timing sendes til src.monitoring.perf. Sett UTVALG_PROFILE=analyse
    # (eller bakoverkompat UTVALG_PROFILE_REFRESH=1) for stderr-print.
    import time as _time
    _stage_t0 = _time.perf_counter()
    _stages: dict[str, float] = {}

    try:
        from src.monitoring.perf import record_event as _record_event
    except Exception:
        _record_event = None  # type: ignore[assignment]

    def _mark(label: str) -> None:
        nonlocal _stage_t0
        now = _time.perf_counter()
        duration_ms = (now - _stage_t0) * 1000.0
        _stages[label] = duration_ms
        if _record_event is not None:
            try:
                _record_event(f"analyse.rl_pivot.{label}", duration_ms)
            except Exception:
                pass
        _stage_t0 = now

    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return

    selected_regnr = [regnr for regnr, _ in get_selected_rl_rows(page=page)]

    # Oppdater headings
    update_pivot_headings(page=page, mode="Regnskapslinje")
    _mark("setup+headings")

    try:
        page._clear_tree(tree)
    except Exception:
        pass

    df_filtered = getattr(page, "_df_filtered", None)
    if df_filtered is None or not isinstance(df_filtered, pd.DataFrame) or df_filtered.empty:
        return

    intervals = getattr(page, "_rl_intervals", None)
    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)

    try:
        page._rl_mapping_warning = ""
    except Exception:
        pass

    if intervals is None or regnskapslinjer is None:
        try:
            page._rl_mapping_warning = "Regnskapslinje-mapping ikke konfigurert."
        except Exception:
            pass
        _show_rl_not_configured(tree)
        return

    base_sb_df, adjusted_sb_df, sb_df = _resolve_analysis_sb_views(page=page)

    account_overrides = _load_current_client_account_overrides()
    try:
        from regnskap_mapping import normalize_regnskapslinjer
        regn = normalize_regnskapslinjer(regnskapslinjer)
        sumline_regnr = {int(v) for v in regn.loc[regn["sumpost"], "regnr"].astype(int).tolist()}
        # Klassifiser sumposter etter nivå: høyt sumnivå = hovedsum
        _sumnivaa_map: dict[int, int] = {}
        if "sumnivaa" in regn.columns:
            for _, r in regn.loc[regn["sumpost"]].iterrows():
                try:
                    _sumnivaa_map[int(r["regnr"])] = int(r["sumnivaa"]) if r["sumnivaa"] is not None else 1
                except Exception:
                    pass
        # Resultat/balanse per regnr (brukt for Type-filter i UI)
        _rb_map: dict[int, str] = {}
        if "rb" in regn.columns:
            for _, r in regn.iterrows():
                v = r.get("rb")
                if v in ("balanse", "resultat"):
                    try:
                        _rb_map[int(r["regnr"])] = str(v)
                    except Exception:
                        pass
    except Exception:
        sumline_regnr = set()
        _sumnivaa_map = {}
        _rb_map = {}

    _rb_filter = ""
    try:
        _rbv = getattr(page, "_var_rb", None)
        if _rbv is not None:
            _sel = str(_rbv.get()).strip().lower()
            if _sel.startswith("balans"):
                _rb_filter = "balanse"
            elif _sel.startswith("resultat"):
                _rb_filter = "resultat"
    except Exception:
        _rb_filter = ""
    unmapped_accounts = get_unmapped_rl_accounts(
        df_filtered,
        intervals,
        regnskapslinjer=regnskapslinjer,
        account_overrides=account_overrides,
    )
    try:
        page._rl_mapping_warning = _format_mapping_warning(unmapped_accounts)
    except Exception:
        pass

    try:
        pivot_df = build_rl_pivot(
            df_filtered,
            intervals,
            regnskapslinjer,
            sb_df=sb_df,
            account_overrides=account_overrides,
        )
    except Exception as exc:
        log.warning("refresh_rl_pivot: feil ved bygging: %s", exc)
        return
    _mark("build_rl_pivot (hoved)")

    # --- Fjorårsdata ---
    sb_prev = ensure_sb_prev_loaded(page=page)
    has_prev = sb_prev is not None and not sb_prev.empty
    fjor_source: Optional[str] = None
    if has_prev:
        try:
            import previous_year_comparison
            import regnskap_client_overrides as _rco
            import session as _sess
            _cl = getattr(_sess, "client", None) or ""
            _yr = getattr(_sess, "year", None) or ""
            prior_overrides = _rco.load_prior_year_overrides(_cl, _yr) if _cl and _yr else None
            pivot_df = previous_year_comparison.add_previous_year_columns(
                pivot_df, sb_prev, intervals, regnskapslinjer,
                account_overrides=account_overrides,
                prior_year_overrides=prior_overrides,
            )
            fjor_source = "sb"
        except Exception as exc:
            log.warning("refresh_rl_pivot: fjorårskolonner feilet: %s", exc)
            has_prev = False

    # BRREG-fallback når egne fjorårstall mangler og BRREG dekker år N-1
    if not has_prev:
        active_year = _resolve_active_year()
        brreg_data_try = getattr(page, "_nk_brreg_data", None)
        if active_year is not None:
            fjor_year = active_year - 1
            try:
                import brreg_fjor_fallback
                if brreg_fjor_fallback.has_brreg_for_year(brreg_data_try, fjor_year):
                    pivot_df = brreg_fjor_fallback.build_brreg_fjor_pivot_columns(
                        pivot_df, regnskapslinjer, brreg_data_try, fjor_year,
                    )
                    has_prev = True
                    fjor_source = "brreg"
            except Exception as exc:
                log.warning("refresh_rl_pivot: BRREG-fjor-fallback feilet: %s", exc)

    try:
        page._rl_fjor_source = fjor_source
    except Exception:
        pass
    # Oppdater headings på nytt: fjor_source og has_prev er nå kjent
    update_pivot_headings(page=page, mode="Regnskapslinje")
    _mark("fjor+brreg-fallback")

    try:
        base_pivot_df = build_rl_pivot(
            df_filtered,
            intervals,
            regnskapslinjer,
            sb_df=base_sb_df,
            account_overrides=account_overrides,
        )
        adjusted_pivot_df = build_rl_pivot(
            df_filtered,
            intervals,
            regnskapslinjer,
            sb_df=adjusted_sb_df,
            account_overrides=account_overrides,
        )
        pivot_df = _add_adjustment_columns(
            pivot_df,
            base_pivot_df=base_pivot_df,
            adjusted_pivot_df=adjusted_pivot_df,
        )
    except Exception as exc:
        log.warning("refresh_rl_pivot: AO-sammenligning feilet: %s", exc)
        pivot_df = _add_adjustment_columns(pivot_df)
    _mark("AO-sammenligning (build_rl_pivot x2)")

    # --- BRREG-sammenligning ---
    brreg_data = getattr(page, "_nk_brreg_data", None)
    has_brreg = bool(brreg_data)
    if has_brreg:
        try:
            import brreg_rl_comparison
            pivot_df = brreg_rl_comparison.add_brreg_columns(
                pivot_df, regnskapslinjer, brreg_data,
            )
        except Exception as exc:
            log.warning("refresh_rl_pivot: BRREG-sammenligning feilet: %s", exc)
            has_brreg = False

    try:
        snap = pivot_df.copy()
        page._pivot_df_last = snap
        page._pivot_df_rl = snap
    except Exception:
        pass
    _mark("brreg+cache_snapshot")

    has_sb = sb_df is not None and not sb_df.empty

    # Sjekk om sumposter skal skjules
    _hide_sum = False
    try:
        _hsv = getattr(page, "_var_hide_sumposter", None)
        if _hsv is not None:
            _hide_sum = bool(_hsv.get())
    except Exception:
        pass

    # Last RL-kommentarer + handlingskoblinger
    _rl_comments: dict[str, str] = {}
    _rl_action_counts: dict[str, int] = {}
    try:
        import regnskap_client_overrides as _rco
        import session as _sess
        _cl = getattr(_sess, "client", None) or ""
        _yr = getattr(_sess, "year", None) or ""
        if _cl:
            _rl_comments = _rco.load_comments(_cl).get("rl", {})
        if _cl and _yr:
            _rl_action_map = _rco.load_rl_action_links(_cl, _yr)
            _rl_action_counts = {str(k): len(v) for k, v in _rl_action_map.items() if v}
    except Exception:
        pass

    _dec = 2
    try:
        _var_dec = getattr(page, "_var_decimals", None)
        if _var_dec is not None and not bool(_var_dec.get()):
            _dec = 0
    except Exception:
        pass

    for _, row in pivot_df.iterrows():
        regnr_int = int(row["regnr"])
        regnr = str(regnr_int)
        navn = str(row.get("regnskapslinje", "") or "")
        if _rb_filter and _rb_map.get(regnr_int, "") != _rb_filter:
            continue
        tags = ()
        if regnr_int in sumline_regnr:
            if _hide_sum:
                continue
            sumnivaa = _sumnivaa_map.get(regnr_int, 2)
            navn = f"Σ {navn}".strip()
            if sumnivaa >= 4:
                tags = ("sumline_total",)
            elif sumnivaa == 3:
                tags = ("sumline_major",)
            else:
                tags = ("sumline",)
        ib_val = float(row.get("IB", 0.0))
        endring_val = float(row.get("Endring", 0.0))
        ub_val = float(row.get("UB", 0.0))
        ao_val = float(row.get("AO_belop", 0.0))
        ub_for_ao_val = float(row.get("UB_for_ao", ub_val))
        ub_etter_ao_val = float(row.get("UB_etter_ao", ub_val))
        cnt_val = int(row.get("Antall", 0))

        if has_sb:
            ib_txt = formatting.fmt_amount(ib_val, decimals=_dec)
            endring_txt = formatting.fmt_amount(endring_val, decimals=_dec)
            ub_txt = formatting.fmt_amount(ub_val, decimals=_dec)
            ao_txt = formatting.fmt_amount(ao_val, decimals=_dec)
            ub_for_ao_txt = formatting.fmt_amount(ub_for_ao_val, decimals=_dec)
            ub_etter_ao_txt = formatting.fmt_amount(ub_etter_ao_val, decimals=_dec)
        else:
            ib_txt = ""
            endring_txt = formatting.fmt_amount(endring_val, decimals=_dec) + " *"
            ub_txt = formatting.fmt_amount(ub_val, decimals=_dec) + " *"
            ao_txt = ""
            ub_for_ao_txt = ""
            ub_etter_ao_txt = ""

        cnt_txt = formatting.format_int_no(cnt_val)

        # Fjorårskolonner
        if has_prev:
            ub_fjor_val = row.get("UB_fjor")
            endring_fjor_val = row.get("Endring_fjor")
            endring_pct_val = row.get("Endring_pct")
            ub_fjor_txt = formatting.fmt_amount(float(ub_fjor_val), decimals=_dec) if ub_fjor_val is not None and ub_fjor_val == ub_fjor_val else ""
            endring_fjor_txt = formatting.fmt_amount(float(endring_fjor_val), decimals=_dec) if endring_fjor_val is not None and endring_fjor_val == endring_fjor_val else ""
            endring_pct_txt = f"{float(endring_pct_val):.1f} %" if endring_pct_val is not None and endring_pct_val == endring_pct_val else ""
        else:
            ub_fjor_txt = ""
            endring_fjor_txt = ""
            endring_pct_txt = ""

        # BRREG-kolonner
        if has_brreg:
            brreg_val = row.get("BRREG")
            avvik_val = row.get("Avvik_brreg")
            avvik_pct_val = row.get("Avvik_brreg_pct")
            brreg_txt = formatting.fmt_amount(float(brreg_val), decimals=_dec) if brreg_val is not None and brreg_val == brreg_val else ""
            avvik_txt = formatting.fmt_amount(float(avvik_val), decimals=_dec) if avvik_val is not None and avvik_val == avvik_val else ""
            avvik_pct_txt = f"{float(avvik_pct_val):.1f} %" if avvik_pct_val is not None and avvik_pct_val == avvik_pct_val else ""
        else:
            brreg_txt = ""
            avvik_txt = ""
            avvik_pct_txt = ""

        # Legg til kommentar-markering
        _comment = _rl_comments.get(regnr, "")
        if _comment and regnr_int not in sumline_regnr:
            navn = f"\u270e {navn}  \u2014 {_comment}"
            tags = tags + ("commented",) if tags else ("commented",)

        # Handlingskobling-badge (f.eks. "Salgsinntekt  \u2022 3 handlinger")
        _n_actions = _rl_action_counts.get(regnr, 0)
        if _n_actions and regnr_int not in sumline_regnr:
            badge = "1 handling" if _n_actions == 1 else f"{_n_actions} handlinger"
            navn = f"{navn}  \u2022 {badge}"

        try:
            tree.insert(
                "",
                "end",
                values=(
                    regnr,
                    navn,
                    "",              # OK — ikke relevant i RL-modus
                    ib_txt,
                    endring_txt,
                    ub_txt,
                    ao_txt,
                    ub_for_ao_txt,
                    ub_etter_ao_txt,
                    cnt_txt,
                    ub_fjor_txt,
                    endring_fjor_txt,
                    endring_pct_txt,
                    brreg_txt,
                    avvik_txt,
                    avvik_pct_txt,
                ),
                tags=tags,
            )
        except Exception:
            continue

    _mark("tree.insert (alle RL-rader)")

    # Auto-juster kolonnene dersom fjorårsdata akkurat ble lastet
    try:
        import page_analyse_columns as _pac
        _pac.update_pivot_columns_for_prev_year(page=page)
    except Exception:
        pass

    maybe_auto_fit = getattr(page, "_maybe_auto_fit_pivot_tree", None)
    if callable(maybe_auto_fit):
        try:
            maybe_auto_fit()
        except Exception:
            pass

    if selected_regnr:
        try:
            page._restore_rl_pivot_selection(selected_regnr)
        except Exception:
            pass
    _mark("post: column-fit + selection")

    # Stages allerede sendt som events per fase via _mark().
    # Stderr-print håndteres av src.monitoring.perf når UTVALG_PROFILE er satt.


def _show_rl_not_configured(tree: Any) -> None:
    try:
        tree.insert(
            "", "end",
            values=(
                "-", "Regnskapslinjer/mapping ikke konfigurert (Innstillinger)",
                "", "", "", "", "", "", "", "", "", "", "", "", "", "",
            ),
        )
    except Exception:
        pass
