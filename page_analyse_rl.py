"""page_analyse_rl.py

Regnskapslinje-pivot for Analyse-fanen.

Ansvar:
- Laste intervall-mapping og regnskapslinjer fra regnskap_config
- Laste aktiv saldobalanse (SB) for gjeldende klient/år
- Bygge pivot på regnskapslinje-nivå med IB, UB (fra SB) og Netto/Antall (fra HB)
- Hente kontoer tilhørende valgte regnskapslinjer (for å filtrere tx-listen)

Kolonner i RL-pivot:
  regnr | Regnskapslinje | IB | UB | Antall

Datakilder:
  - IB, UB: aktiv SB-versjon for klient/år (via client_store + trial_balance_reader)
  - Antall:  sum av HB-transaksjoner (df_filtered)
  - Netto:   UB - IB (fra SB), eller sum av Beløp (HB) om SB mangler

Visningsregel:
  - Med SB:   vis RL der |UB| > 0 ELLER Antall > 0  (skjul rent tomme linjer)
  - Uten SB:  vis kun RL der Antall > 0

Modul-struktur (utskilt fra denne fasaden):
  - page_analyse_rl_data      → data-lasting (SB, intervaller, fjorårs-SB, overrides)
  - page_analyse_rl_pivot     → pivot-bygging og aggregering
  - page_analyse_rl_drilldown → konto-drilldown og detaljkontekst under valgte RL
  - page_analyse_rl_render    → headings, refresh_rl_pivot, RL_PIVOT_HEADINGS m.m.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Re-eksport av utskilte moduler (bakoverkompatibilitet)
# ---------------------------------------------------------------------------

from page_analyse_rl_data import (  # noqa: F401
    _load_current_client_account_overrides,
    _resolve_analysis_sb_views,
    _resolve_regnr_for_accounts,
    _try_repair_empty_sb,
    ensure_sb_prev_loaded,
    load_rl_config,
    load_sb_for_session,
)
from page_analyse_rl_pivot import (  # noqa: F401
    _add_adjustment_columns,
    _aggregate_hb_to_regnr,
    _aggregate_sb_to_regnr,
    _empty_pivot,
    _format_mapping_warning,
    build_rl_pivot,
    get_unmapped_rl_accounts,
)
from page_analyse_rl_drilldown import (  # noqa: F401
    _expand_selected_regnskapslinjer,
    build_rl_account_drilldown,
    build_selected_rl_account_drilldown,
    build_selected_rl_detail_context,
    get_selected_rl_accounts,
    get_selected_rl_rows,
)
from page_analyse_rl_render import (  # noqa: F401
    HB_KONTO_PIVOT_HEADINGS,
    KONTO_PIVOT_HEADINGS,
    RL_PIVOT_HEADINGS,
    _resolve_active_year,
    _rl_headings_with_year,
    _sb_konto_headings_with_year,
    _show_rl_not_configured,
    refresh_rl_pivot,
    update_pivot_headings,
)
