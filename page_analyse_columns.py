"""page_analyse_columns.py

Kolonnehåndtering for Analyse-fanen: pivot-synlighet, TX-kolonnevalg,
auto-fit og breddepersistens.

Alle funksjoner tar ``page`` (AnalysePage-instans) som duck-typed objekt
og leser/skriver attributter direkte – samme mønster som de øvrige
page_analyse_*-modulene.
"""

from __future__ import annotations

from typing import Any, List, Optional

import analyse_columns
import analyse_treewidths
import preferences


# =====================================================================
# Pivot-kolonnesynlighet
# =====================================================================

# Kolonner som alltid skal strekke seg for å fylle ledig plass
PIVOT_STRETCH_COLS = ("Kontonavn",)
PIVOT_FILL_PRIORITY = ("Kontonavn", "Konto")
PIVOT_FILL_WEIGHTS = {"Kontonavn": 9, "Konto": 1}
TX_HEADER_DRAG_THRESHOLD_PX = 10


def normalize_aggregation_mode(value: object) -> str:
    """Map user-facing og legacy mode-verdier til kanonisk intern verdi.

    GUI viser nå bare "Saldobalanse" og "Regnskapslinje". Legacy/interne
    moduser ("Konto", "SB-konto", "HB-konto", "MVA-kode") kollapses til
    kanonisk "SB-konto" slik at eldre prefs/kode fortsatt fungerer.
    """
    v = str(value or "").strip()
    if v == "Regnskapslinje":
        return "Regnskapslinje"
    return "SB-konto"


def normalize_view_mode(value: object) -> str:
    """Map høyre-side view-modus til kanonisk intern verdi.

    GUI viser nå bare "Saldobalanse" og "Hovedbok". Gamle moduser
    ("Saldobalansekontoer", "Transaksjoner", "Nøkkeltall", "Motposter",
    "Motposter (kontonivå)") normaliseres slik at eldre prefs/kode
    fortsatt fungerer. Ukjente/fjernede verdier → "Saldobalansekontoer".
    """
    v = str(value or "").strip()
    if v in ("Hovedbok", "Transaksjoner"):
        return "Transaksjoner"
    return "Saldobalansekontoer"


def _read_agg_mode(page: Any) -> str:
    """Les aggregeringsmodus fra page med legacy-migrering."""
    try:
        raw = page._var_aggregering.get() if page._var_aggregering is not None else ""
    except Exception:
        raw = ""
    return normalize_aggregation_mode(raw)


def _read_view_mode(page: Any) -> str:
    """Les høyre-panel view-modus fra page med legacy-migrering."""
    try:
        raw = page._var_tx_view_mode.get() if page._var_tx_view_mode is not None else ""
    except Exception:
        raw = ""
    return normalize_view_mode(raw)


# =====================================================================
# Felles brukerrettet label-mapper for Analyse-kolonner
# =====================================================================

# Kanoniske labels for kolonne-ID-er som brukes både i venstre pivot og
# høyre SB-tree. UB / UB_fjor får årstall injisert via analysis_heading.
_ANALYSIS_HEADINGS_STATIC = {
    "Konto": "Konto",
    "Kontonavn": "Kontonavn",
    "OK": "OK",
    "OK_av": "OK av",
    "OK_dato": "OK dato",
    "Vedlegg": "Vedlegg",
    "Gruppe": "Gruppe",
    "IB": "IB",
    "Endring": "Bevegelse i år",       # periode-bevegelse (UB-IB)
    "Endring_fjor": "Endring",          # år-over-år (UB - UB_fjor)
    "Endring_pct": "Endring %",
    "Antall": "Antall",
    "AO_belop": "Tilleggspostering",
    "UB_for_ao": "UB før ÅO",
    "UB_etter_ao": "UB etter ÅO",
    "BRREG": "BRREG",
    "Avvik_brreg": "Avvik mot BRREG",
    "Avvik_brreg_pct": "Avvik % mot BRREG",
}


def analysis_heading(col_id: str, *, year: Optional[int] = None) -> str:
    """Returner kanonisk brukerrettet overskrift for en Analyse-kolonne-ID.

    Brukes av både venstre pivot og høyre SB-tree slik at samme kolonne
    ID vises med samme label overalt.

    - ``Sum`` / ``UB``   → ``UB <år>`` når år er kjent, ellers ``UB``.
    - ``UB_fjor``        → ``UB <år-1>`` når år er kjent, ellers ``UB i fjor``.
    - Øvrige kolonner    → fra ``_ANALYSIS_HEADINGS_STATIC``, fallback til ID.
    """
    if col_id in ("Sum", "UB"):
        return f"UB {year}" if year is not None else "UB"
    if col_id == "UB_fjor":
        return f"UB {year - 1}" if year is not None else "UB i fjor"
    return _ANALYSIS_HEADINGS_STATIC.get(col_id, col_id)


def _active_year() -> Optional[int]:
    """Les aktivt regnskapsår fra session som int når mulig."""
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


_LEGACY_RL_VISIBLE_DEFAULTS = {
    (
        "Konto",
        "Kontonavn",
        "IB",
        "Endring",
        "Sum",
        "AO_belop",
        "UB_for_ao",
        "UB_etter_ao",
        "Antall",
    ),
    (
        "Konto",
        "Kontonavn",
        "Endring",
        "Sum",
        "UB_fjor",
        "AO_belop",
        "UB_for_ao",
        "UB_etter_ao",
        "Antall",
        "Endring_pct",
    ),
    # Tidligere PIVOT_COLS_DEFAULT_RL (uten fjor\u00e5rsdata)
    ("Konto", "Kontonavn", "IB", "Endring", "Sum", "Antall"),
    # Tidligere default med fjor\u00e5rsdata (avledet av gammel pivot_default_for_mode)
    ("Konto", "Kontonavn", "Endring", "Sum", "UB_fjor", "Antall", "Endring_pct"),
    # Forrige PIVOT_COLS_DEFAULT_RL (med intern Endring = Bevegelse i \u00e5r)
    (
        "Konto",
        "Kontonavn",
        "Sum",
        "UB_fjor",
        "Endring",
        "Endring_fjor",
        "Endring_pct",
        "Antall",
    ),
    # Tidligere slank fallback uten fj\u00e5rsdata med intern Endring innskutt etter Sum
    ("Konto", "Kontonavn", "Sum", "Endring", "Antall"),
}


def _has_prev_year(page: Any) -> bool:
    """Returner True dersom fjorårsdata er lastet og tilgjengelig."""
    import pandas as pd
    pivot_df = getattr(page, "_pivot_df_last", None)
    if isinstance(pivot_df, pd.DataFrame) and "UB_fjor" in pivot_df.columns:
        return True
    sb_prev = getattr(page, "_rl_sb_prev_df", None)
    if isinstance(sb_prev, pd.DataFrame) and not sb_prev.empty:
        return True
    return False


def _rl_like_default(*, page: Any, base: tuple[str, ...]) -> tuple[str, ...]:
    """Samme komparative kolonne-default som RL, med slank fallback uten fjorårsdata.

    Brukes av både Regnskapslinje- og SB-konto-modus: begge viser
    ``UB <år>``, ``UB <år-1>``, ``Endring`` og ``Endring %`` når
    fjorårsdata er tilgjengelig. Uten fjorårsdata droppes de
    fjorårsavhengige kolonnene uten å sette inn intern ``Endring``
    (Bevegelse i år) som fallback — den forblir tilgjengelig via
    kolonne-menyen, men er ikke standard synlig.
    """
    if _has_prev_year(page):
        return tuple(base)
    prev_dependent = {"UB_fjor", "Endring_fjor", "Endring_pct"}
    result: list[str] = []
    seen: set[str] = set()
    for col in base:
        if col in prev_dependent:
            continue
        if col in seen:
            continue
        result.append(col)
        seen.add(col)
    return tuple(result)


def pivot_default_for_mode(*, page: Any) -> tuple[str, ...]:
    """Returner standard synlige pivot-kolonner for gjeldende aggregeringsmodus.

    RL / SB-konto standardrekkefølge (med fjorårsdata):
        Nr / Konto | Regnskapslinje / Kontonavn | UB <aktivt år> |
        UB <aktivt år-1> | Endring | Endring % | Antall
        (kolonne-IDer: Konto | Kontonavn | Sum | UB_fjor | Endring_fjor |
         Endring_pct | Antall)

    Uten fjorårsdata:
        UB <aktivt år> | Bevegelse i år | Antall
        (kolonne-IDer: Konto | Kontonavn | Sum | Endring | Antall)

    HB-konto: Konto | Kontonavn | HB-bevegelse | Antall (ingen komparativ).
    """
    agg = _read_agg_mode(page)
    if agg == "HB-konto":
        return getattr(page, "PIVOT_COLS_DEFAULT_HB_KONTO", page.PIVOT_COLS_DEFAULT_VISIBLE)
    if agg == "SB-konto":
        base = getattr(page, "PIVOT_COLS_DEFAULT_SB_KONTO", page.PIVOT_COLS_DEFAULT_VISIBLE)
        return _rl_like_default(page=page, base=tuple(base))
    if agg == "Regnskapslinje":
        base = getattr(page, "PIVOT_COLS_DEFAULT_RL", page.PIVOT_COLS_DEFAULT_VISIBLE)
        return _rl_like_default(page=page, base=tuple(base))
    return page.PIVOT_COLS_DEFAULT_VISIBLE


def load_pivot_visible_columns(*, page: Any) -> None:
    """Last lagret pivot-kolonnesynlighet fra preferences."""
    try:
        stored = preferences.get("analyse.pivot_cols.visible", None)
    except Exception:
        stored = None

    if isinstance(stored, list) and stored:
        valid = [c for c in stored if c in page.PIVOT_COLS]
        for p in page.PIVOT_COLS_PINNED:
            if p not in valid:
                valid.insert(0, p)
        page._pivot_visible_cols = valid
    else:
        page._pivot_visible_cols = list(page.PIVOT_COLS_DEFAULT_VISIBLE)


def persist_pivot_visible_columns(*, page: Any) -> None:
    try:
        preferences.set("analyse.pivot_cols.visible", list(page._pivot_visible_cols))
    except Exception:
        pass


def apply_pivot_visible_columns(*, page: Any) -> None:
    """Oppdater pivot-tree displaycolumns basert på _pivot_visible_cols."""
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    all_cols = list(tree["columns"])
    visible = [c for c in page._pivot_visible_cols if c in all_cols]
    if not visible:
        visible = list(page.PIVOT_COLS_DEFAULT_VISIBLE)
    try:
        tree["displaycolumns"] = visible
    except Exception:
        pass


def toggle_pivot_column(*, page: Any, col: str) -> None:
    """Slå av/på en kolonne i pivot-visningen."""
    if col in page.PIVOT_COLS_PINNED:
        return
    if col in page._pivot_visible_cols:
        page._pivot_visible_cols.remove(col)
    else:
        pos = 0
        for pc in page.PIVOT_COLS:
            if pc == col:
                break
            if pc in page._pivot_visible_cols:
                pos += 1
        page._pivot_visible_cols.insert(pos, col)
    apply_pivot_visible_columns(page=page)
    persist_pivot_visible_columns(page=page)


def show_pivot_column_menu(*, page: Any, event: Any) -> None:
    """Vis høyreklikkmeny for å vise/skjule pivot-kolonner."""
    if not getattr(page, "_tk_ok", False) or event is None:
        return
    try:
        import tkinter as tk
    except Exception:
        return

    tree = getattr(page, "_pivot_tree", None)
    menu = tk.Menu(page, tearoff=0)
    for col in page.PIVOT_COLS:
        if col in page.PIVOT_COLS_PINNED:
            continue
        display_name = col
        if tree is not None:
            try:
                heading_text = tree.heading(col, "text")
                if heading_text and heading_text.strip():
                    display_name = heading_text.strip()
                else:
                    continue  # Ikke relevant i nåværende modus
            except Exception:
                pass
        is_visible = col in page._pivot_visible_cols
        label = f"{'✓  ' if is_visible else '    '}{display_name}"
        menu.add_command(
            label=label,
            command=lambda c=col: toggle_pivot_column(page=page, col=c),
        )
    menu.add_separator()
    menu.add_command(label="Standard", command=lambda: reset_pivot_columns(page=page))

    # Kommentar-alternativ for RL- og konto-moduser
    agg_mode = _read_agg_mode(page)

    if tree is not None:
        try:
            item = tree.identify_row(event.y)
            if item:
                vals = tree.item(item, "values")
                if vals:
                    first_col = str(vals[0]).strip()
                    second_col = str(vals[1]).strip() if len(vals) > 1 else ""
                    if first_col and not first_col.startswith("\u03a3"):
                        menu.add_separator()
                        if agg_mode == "Regnskapslinje":
                            menu.add_command(
                                label=f"Vis statistikk for {first_col} {second_col}",
                                command=lambda r=first_col: _open_statistikk(page=page, regnr=r),
                            )
                            menu.add_command(
                                label=f"Kommentar for {first_col} {second_col}\u2026",
                                command=lambda: _open_rl_comment(page=page, regnr=first_col, rl_name=second_col),
                            )
                            link_label = _action_link_label(
                                kind="rl", entity_key=first_col, base="Koble til handling"
                            )
                            menu.add_command(
                                label=f"{link_label}\u2026",
                                command=lambda: _open_action_link(
                                    page=page, kind="rl",
                                    entity_key=first_col,
                                    entity_label=f"{first_col} {second_col}",
                                ),
                            )
                        elif agg_mode in ("SB-konto", "HB-konto", ""):
                            menu.add_command(
                                label=f"Kommentar for {first_col} {second_col}\u2026",
                                command=lambda: _open_account_comment(page=page, konto=first_col, kontonavn=second_col),
                            )
                            link_label = _action_link_label(
                                kind="account", entity_key=first_col, base="Koble til handling"
                            )
                            menu.add_command(
                                label=f"{link_label}\u2026",
                                command=lambda: _open_action_link(
                                    page=page, kind="account",
                                    entity_key=first_col,
                                    entity_label=f"{first_col} {second_col}",
                                ),
                            )
        except Exception:
            pass

    try:
        menu.tk_popup(event.x_root, event.y_root)
    except Exception:
        pass


def _open_rl_comment(*, page: Any, regnr: str, rl_name: str) -> None:
    """Åpne kommentar-dialog for en regnskapslinje."""
    try:
        import page_analyse_sb
        page_analyse_sb._edit_comment(
            page=page, kind="rl", key=regnr, label=f"{regnr} {rl_name}",
        )
    except Exception:
        pass


def _open_account_comment(*, page: Any, konto: str, kontonavn: str) -> None:
    """Åpne kommentar-dialog for en konto i konto-pivot."""
    try:
        import page_analyse_sb
        page_analyse_sb._edit_comment(
            page=page, kind="accounts", key=konto, label=f"{konto} {kontonavn}",
        )
    except Exception:
        pass


def _action_link_label(*, kind: str, entity_key: str, base: str) -> str:
    try:
        import page_analyse_sb
        return page_analyse_sb._action_link_menu_label(
            kind=kind, entity_key=entity_key, base=base,
        )
    except Exception:
        return base


def _open_action_link(
    *, page: Any, kind: str, entity_key: str, entity_label: str
) -> None:
    try:
        import page_analyse_sb
        page_analyse_sb._open_action_link_dialog(
            page=page, kind=kind,
            entity_key=entity_key, entity_label=entity_label,
        )
    except Exception:
        pass


def _open_statistikk(*, page: Any, regnr: str) -> None:
    """Bytt til Statistikk-fanen og vis valgt regnskapslinje."""
    try:
        import session as _session
        app = getattr(_session, "APP", None)
        if app is None:
            return
        stat_page = getattr(app, "page_statistikk", None)
        if stat_page is None:
            return
        nb = getattr(app, "nb", None)
        if nb is not None:
            nb.select(stat_page)
        stat_page.show_regnr(int(regnr))
    except Exception:
        pass


def reset_pivot_columns(*, page: Any) -> None:
    page._pivot_visible_cols = list(pivot_default_for_mode(page=page))
    apply_pivot_visible_columns(page=page)
    persist_pivot_visible_columns(page=page)


def adapt_pivot_columns_for_mode(*, page: Any) -> None:
    """Tilpass synlige kolonner når aggregeringsmodus endres."""
    defaults = pivot_default_for_mode(page=page)
    agg = _read_agg_mode(page)
    if agg in ("Regnskapslinje", "SB-konto"):
        current = tuple(getattr(page, "_pivot_visible_cols", []) or [])
        if current in _LEGACY_RL_VISIBLE_DEFAULTS:
            page._pivot_visible_cols = list(defaults)
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    relevant: set[str] = set(page.PIVOT_COLS_PINNED)
    for col_id in page.PIVOT_COLS:
        try:
            heading_text = tree.heading(col_id, "text")
        except Exception:
            heading_text = ""
        if heading_text and heading_text.strip():
            relevant.add(col_id)
    new_visible = list(defaults)
    for col in page._pivot_visible_cols:
        if col not in new_visible and col in relevant:
            new_visible.append(col)
    new_visible = [c for c in new_visible if c in relevant]
    if not new_visible:
        new_visible = list(defaults)
    page._pivot_visible_cols = new_visible
    apply_pivot_visible_columns(page=page)
    persist_pivot_visible_columns(page=page)


def update_pivot_columns_for_prev_year(*, page: Any) -> None:
    """Kall etter at fjorårsdata er lastet.

    Legger automatisk til UB_fjor, Endring_fjor og Endring_pct (fjerner IB)
    i RL-modus så brukeren får ny komparativ standard. Gjør ingenting i
    Konto-modus. Rekkefølge: Sum → UB_fjor → Endring_fjor → Endring_pct.
    """
    agg = ""
    try:
        agg = str(page._var_aggregering.get())
    except Exception:
        pass
    if agg != "Regnskapslinje":
        return

    if not _has_prev_year(page):
        return

    visible = list(getattr(page, "_pivot_visible_cols", []))

    changed = False
    # Fjern IB hvis det er der (ikke del av ny komparativ default)
    if "IB" in visible:
        visible.remove("IB")
        changed = True

    # Sørg for rekkefølge Sum → UB_fjor → Endring_fjor → Endring_pct ved å
    # sette inn manglende kolonner rett etter "Sum" (eller hver etter den
    # forrige hvis Sum mangler).
    def _insert_after(anchor: str, col: str) -> bool:
        if col in visible:
            return False
        try:
            idx = visible.index(anchor)
            visible.insert(idx + 1, col)
        except ValueError:
            visible.append(col)
        return True

    changed |= _insert_after("Sum", "UB_fjor")
    changed |= _insert_after("UB_fjor", "Endring_fjor")
    changed |= _insert_after("Endring_fjor", "Endring_pct")

    if changed:
        page._pivot_visible_cols = visible
        apply_pivot_visible_columns(page=page)
        persist_pivot_visible_columns(page=page)


def update_pivot_columns_for_brreg(*, page: Any) -> None:
    """Kall etter at BRREG-data er hentet.

    Viser BRREG, Avvik_brreg og Avvik_brreg_pct i RL-modus når tilgjengelig.
    """
    agg = ""
    try:
        agg = str(page._var_aggregering.get())
    except Exception:
        pass
    if agg != "Regnskapslinje":
        return

    if not getattr(page, "_nk_brreg_data", None):
        return

    visible = list(getattr(page, "_pivot_visible_cols", []))
    changed = False
    for col in ("BRREG", "Avvik_brreg", "Avvik_brreg_pct"):
        if col not in visible:
            visible.append(col)
            changed = True

    if changed:
        page._pivot_visible_cols = visible
        apply_pivot_visible_columns(page=page)
        persist_pivot_visible_columns(page=page)


def clear_pivot_columns_for_brreg(*, page: Any) -> None:
    """Skjul BRREG-kolonner i RL-modus (kalles når BRREG-data tømmes)."""
    visible = list(getattr(page, "_pivot_visible_cols", []))
    changed = False
    for col in ("BRREG", "Avvik_brreg", "Avvik_brreg_pct"):
        if col in visible:
            visible.remove(col)
            changed = True
    if changed:
        page._pivot_visible_cols = visible
        try:
            apply_pivot_visible_columns(page=page)
            persist_pivot_visible_columns(page=page)
        except Exception:
            pass


# =====================================================================
# TX-kolonnepreferanser
# =====================================================================

def load_tx_columns_from_preferences(*, page: Any) -> None:
    """Last inn kolonneoppsett for transaksjonslisten fra preferences."""
    try:
        stored_order = preferences.get("analyse.tx_cols.order", None)
        stored_visible = preferences.get("analyse.tx_cols.visible", None)
    except Exception:
        stored_order = None
        stored_visible = None

    order = stored_order if isinstance(stored_order, list) else list(page.TX_COLS_DEFAULT)
    visible = stored_visible if isinstance(stored_visible, list) else list(page.TX_COLS_DEFAULT)

    order_clean, visible_order = analyse_columns.normalize_tx_column_config(
        order=order,
        visible=visible,
        all_cols=None,
        pinned=page.PINNED_TX_COLS,
        required=page.REQUIRED_TX_COLS,
    )

    page._tx_cols_order = list(order_clean)
    page._tx_cols_visible = list(visible_order)
    page.TX_COLS = tuple(visible_order)


def persist_tx_columns_to_preferences(*, page: Any) -> None:
    try:
        preferences.set("analyse.tx_cols.order", list(page._tx_cols_order))
        preferences.set("analyse.tx_cols.visible", list(page.TX_COLS))
    except Exception:
        pass


def get_all_tx_columns_for_chooser(*, page: Any) -> List[str]:
    import pandas as pd
    cols: List[str] = []
    cols.extend(getattr(page, "_tx_cols_order", []))
    cols.extend(list(page.TX_COLS_DEFAULT))

    df = page._df_filtered if isinstance(page._df_filtered, pd.DataFrame) else page.dataset
    if isinstance(df, pd.DataFrame):
        for c in df.columns:
            try:
                name = str(c)
            except Exception:
                continue
            if not name or name.startswith("_"):
                continue
            cols.append(name)

    return analyse_columns.unique_preserve(cols, canonicalize=True)


def apply_tx_column_config(*, page: Any, order: List[str], visible: List[str],
                           all_cols: Optional[List[str]] = None) -> None:
    all_cols = all_cols or get_all_tx_columns_for_chooser(page=page)

    order_clean, visible_order = analyse_columns.normalize_tx_column_config(
        order=order,
        visible=visible,
        all_cols=all_cols,
        pinned=page.PINNED_TX_COLS,
        required=page.REQUIRED_TX_COLS,
    )

    page._tx_cols_order = list(order_clean)
    page._tx_cols_visible = list(visible_order)
    page.TX_COLS = tuple(visible_order)

    persist_tx_columns_to_preferences(page=page)

    configure_tx_tree_columns(page=page)
    page._refresh_transactions_view()


def open_tx_column_chooser(*, page: Any) -> None:
    if not getattr(page, "_tk_ok", False):
        return

    try:
        from views_column_chooser import open_column_chooser
    except Exception:
        return

    all_cols = get_all_tx_columns_for_chooser(page=page)
    current_visible = list(getattr(page, "TX_COLS", page.TX_COLS_DEFAULT))
    initial_order = list(getattr(page, "_tx_cols_order", all_cols))

    res = open_column_chooser(
        page,
        all_cols=all_cols,
        visible_cols=current_visible,
        initial_order=initial_order,
        default_visible_cols=list(page.TX_COLS_DEFAULT),
        default_order=list(page.TX_COLS_DEFAULT),
    )
    if not res:
        return

    order, visible = res
    if not isinstance(order, list) or not isinstance(visible, list):
        return

    apply_tx_column_config(page=page, order=order, visible=visible, all_cols=all_cols)


def reset_tx_columns_to_default(*, page: Any) -> None:
    apply_tx_column_config(
        page=page,
        order=list(page.TX_COLS_DEFAULT),
        visible=list(page.TX_COLS_DEFAULT),
    )


# =====================================================================
# SB-kolonnepreferanser (Saldobalansekontoer-visning)
# =====================================================================

# SB-pinned kolonner (kan ikke skjules eller flyttes fra starten)
SB_PINNED_COLS = ("Konto", "Kontonavn")

# Dynamiske kolonner som skjules midlertidig når fjorårsdata mangler,
# men der brukerens preferanse ikke slettes.
SB_DYNAMIC_COLS = ("UB_fjor", "Endring_fjor", "Endring_pct")


def _sb_defaults(page: Any) -> tuple[list[str], list[str]]:
    """Returner (alle SB-kolonner, kanonisk standard synlig-sett)."""
    try:
        import page_analyse_sb as _sb
        all_cols = list(_sb.SB_COLS)
        default_visible = list(getattr(_sb, "SB_DEFAULT_VISIBLE", _sb.SB_COLS))
    except Exception:
        all_cols = list(SB_PINNED_COLS)
        default_visible = list(SB_PINNED_COLS)
    # Sørg for at pinned alltid ligger først i default_visible
    for p in reversed(SB_PINNED_COLS):
        if p not in default_visible:
            default_visible.insert(0, p)
    return all_cols, default_visible


def _sb_ub_fjor_available(page: Any) -> bool:
    """Har SB-visningen fjorårsdata tilgjengelig for UB_fjor-kolonnen?"""
    import pandas as pd
    sb_prev = getattr(page, "_rl_sb_prev_df", None)
    if isinstance(sb_prev, pd.DataFrame) and not sb_prev.empty:
        return True
    return False


def load_sb_columns_from_preferences(*, page: Any) -> None:
    """Last inn SB-kolonneoppsett fra preferences og normaliser."""
    try:
        stored_order = preferences.get("analyse.sb_cols.order", None)
        stored_visible = preferences.get("analyse.sb_cols.visible", None)
    except Exception:
        stored_order = None
        stored_visible = None

    default_order, default_visible = _sb_defaults(page)

    # Migrer gamle preferanser til ny kanonisk standard (UB <år> + UB <år-1>
    # + Endring + Endring %) når stored_visible mangler de nye komparative
    # kolonnene men inneholder legacy-kolonner (IB/Endring intern).
    if isinstance(stored_visible, list) and stored_visible:
        has_new_canonical = any(
            c in stored_visible for c in ("Endring_fjor", "Endring_pct")
        )
        has_legacy_intern = any(c in stored_visible for c in ("IB", "Endring"))
        if has_legacy_intern and not has_new_canonical:
            stored_visible = None

    order = stored_order if isinstance(stored_order, list) else list(default_order)
    visible = stored_visible if isinstance(stored_visible, list) else list(default_visible)

    order_clean, visible_order = analyse_columns.normalize_tx_column_config(
        order=order,
        visible=visible,
        all_cols=default_order,
        pinned=SB_PINNED_COLS,
        required=SB_PINNED_COLS,
    )

    page._sb_cols_order = list(order_clean)
    page._sb_cols_visible = list(visible_order)


def persist_sb_columns_to_preferences(*, page: Any) -> None:
    try:
        preferences.set("analyse.sb_cols.order", list(getattr(page, "_sb_cols_order", [])))
        preferences.set("analyse.sb_cols.visible", list(getattr(page, "_sb_cols_visible", [])))
    except Exception:
        pass


def apply_sb_column_config(*, page: Any, order: List[str], visible: List[str]) -> None:
    default_order, _ = _sb_defaults(page)

    order_clean, visible_order = analyse_columns.normalize_tx_column_config(
        order=order,
        visible=visible,
        all_cols=default_order,
        pinned=SB_PINNED_COLS,
        required=SB_PINNED_COLS,
    )

    page._sb_cols_order = list(order_clean)
    page._sb_cols_visible = list(visible_order)

    persist_sb_columns_to_preferences(page=page)
    configure_sb_tree_columns(page=page)


def open_sb_column_chooser(*, page: Any) -> None:
    if not getattr(page, "_tk_ok", False):
        return
    try:
        from views_column_chooser import open_column_chooser
    except Exception:
        return

    default_order, default_visible = _sb_defaults(page)
    current_visible = list(getattr(page, "_sb_cols_visible", default_visible))
    initial_order = list(getattr(page, "_sb_cols_order", default_order))

    res = open_column_chooser(
        page,
        all_cols=list(default_order),
        visible_cols=current_visible,
        initial_order=initial_order,
        default_visible_cols=list(default_visible),
        default_order=list(default_order),
    )
    if not res:
        return
    order, visible = res
    if not isinstance(order, list) or not isinstance(visible, list):
        return
    apply_sb_column_config(page=page, order=order, visible=visible)


def reset_sb_columns_to_default(*, page: Any) -> None:
    default_order, default_visible = _sb_defaults(page)
    apply_sb_column_config(page=page, order=default_order, visible=default_visible)


def configure_sb_tree_columns(*, page: Any) -> None:
    """Sett displaycolumns + bredder på SB-treet basert på preferanser.

    UB_fjor skjules dynamisk når fjorårsdata mangler, men brukerens
    preferanse beholdes.
    """
    if not getattr(page, "_tk_ok", False):
        return
    tree = getattr(page, "_sb_tree", None)
    if tree is None:
        return

    try:
        import page_analyse_sb as _sb
    except Exception:
        return

    default_order, _ = _sb_defaults(page)
    order = list(getattr(page, "_sb_cols_order", default_order))
    visible_pref = list(getattr(page, "_sb_cols_visible", default_order))

    has_prev = _sb_ub_fjor_available(page)
    effective_visible = [
        c for c in visible_pref
        if not (c in SB_DYNAMIC_COLS and not has_prev)
    ]

    try:
        tree.configure(columns=tuple(default_order))
        tree["displaycolumns"] = tuple(effective_visible)
    except Exception:
        return

    widths_pref = getattr(page, "_sb_col_widths", None) or {}
    year = _active_year()

    for c in default_order:
        heading = analysis_heading(c, year=year)
        try:
            tree.heading(c, text=heading)
        except Exception:
            pass

        if c in _sb._SB_NUMERIC_COLS:
            anchor = "e"
        elif c in _sb._SB_CENTER_COLS:
            anchor = "center"
        else:
            anchor = "w"
        stretch = (c == "Kontonavn")

        default_width = _sb._SB_COL_WIDTHS.get(c, 100)
        width = int(widths_pref.get(c, default_width))
        try:
            tree.column(c, width=width, minwidth=40, anchor=anchor, stretch=stretch)
        except Exception:
            pass


# =====================================================================
# Bredde-persistens & auto-fit
# =====================================================================

def load_saved_column_widths(pref_key: str) -> dict[str, int]:
    try:
        raw = preferences.get(pref_key, {})
    except Exception:
        raw = {}

    if not isinstance(raw, dict):
        return {}

    widths: dict[str, int] = {}
    for key, value in raw.items():
        name = str(key or "").strip()
        if not name:
            continue
        try:
            width = int(value)
        except Exception:
            continue
        if 40 <= width <= 1200:
            widths[name] = width
    return widths


def persist_saved_column_widths(pref_key: str, widths: dict[str, int]) -> None:
    clean: dict[str, int] = {}
    for key, value in widths.items():
        name = str(key or "").strip()
        if not name:
            continue
        try:
            width = int(value)
        except Exception:
            continue
        if 40 <= width <= 1200:
            clean[name] = width
    try:
        preferences.set(pref_key, clean)
    except Exception:
        pass


def tree_display_columns(tree: Any) -> List[str]:
    try:
        display = tree["displaycolumns"]
    except Exception:
        display = ()
    if display in ("#all", ("#all",)):
        try:
            return list(tree["columns"])
        except Exception:
            return []
    return [str(c) for c in (display or ()) if str(c).strip()]


def safe_tree_column_width(tree: Any, col: str) -> Optional[int]:
    try:
        return int(tree.column(col, option="width"))
    except Exception:
        try:
            cfg = tree.column(col)
        except Exception:
            return None
        if isinstance(cfg, dict):
            try:
                return int(cfg.get("width"))
            except Exception:
                return None
    return None


def snapshot_tree_widths(tree: Any, columns: List[str]) -> dict[str, int]:
    widths: dict[str, int] = {}
    for col in columns:
        width = safe_tree_column_width(tree, col)
        if width is not None and 40 <= width <= 1200:
            widths[col] = width
    return widths


def tree_rows_for_width_estimate(tree: Any, columns: List[str], *, limit: int = 200) -> List[dict]:
    """Hent radverdier for breddeestimering, korrekt indeksert per kolonnenavn.

    tree.item(item).get("values") returnerer verdier for ALLE kolonner i tree["columns"]
    rekkefølge, uavhengig av hvilke kolonner som er synlige (displaycolumns). Vi mapper
    derfor eksplisitt kolonnenavn → verdi fremfor å bruke posisjonell indeks, slik at
    skjulte kolonner ikke forskyver indeksene for synlige kolonner.
    """
    try:
        all_cols = list(tree["columns"])
    except Exception:
        all_cols = list(columns)

    col_index = {col: i for i, col in enumerate(all_cols)}

    try:
        children = list(tree.get_children(""))[:limit]
    except Exception:
        return []

    rows: List[dict] = []
    for item in children:
        try:
            values = list(tree.item(item).get("values") or [])
        except Exception:
            continue
        if not values:
            continue
        row: dict = {}
        for col in columns:
            idx = col_index.get(col)
            row[col] = values[idx] if idx is not None and idx < len(values) else ""
        rows.append(row)
    return rows


def column_id_from_event(tree: Any, event: Any) -> Optional[str]:
    try:
        token = str(tree.identify_column(event.x))
    except Exception:
        return None
    if not token.startswith("#"):
        return None
    try:
        index = int(token[1:]) - 1
    except Exception:
        return None

    columns = tree_display_columns(tree)
    if 0 <= index < len(columns):
        return columns[index]
    return None


def auto_fit_tree_columns(
    *,
    tree: Any,
    columns: List[str],
    stored_widths: dict[str, int],
    pref_key: str,
    only_missing: bool = False,
    target_col: Optional[str] = None,
    persist: bool = False,
    stretch_cols: set[str] | None = None,
) -> None:
    """Auto-fit kolonnbredder basert på innhold.

    ``stretch_cols`` angir kolonner som beholder ``stretch=True``
    (f.eks. ``{"Kontonavn"}``). Alle andre settes til ``stretch=False``.
    """
    rows = tree_rows_for_width_estimate(tree, columns)
    if not rows and target_col is None:
        return

    updated = dict(stored_widths)
    stretch_cols = stretch_cols or set()

    for col in columns:
        if target_col and col != target_col:
            continue
        if only_missing and col in stored_widths:
            continue

        values = [row.get(col, "") for row in rows]
        width = analyse_treewidths.suggest_column_width(col, values)
        try:
            tree.column(
                col,
                width=width,
                minwidth=analyse_treewidths.column_minwidth(col),
                anchor=analyse_treewidths.column_anchor(col),
                stretch=col in stretch_cols,
            )
        except Exception:
            continue

        if persist:
            updated[col] = width

    if persist:
        stored_widths.clear()
        stored_widths.update(updated)
        persist_saved_column_widths(pref_key, stored_widths)


def rebalance_tree_columns_to_available_width(
    *,
    tree: Any,
    columns: List[str],
    preferred_cols: List[str],
    weights: dict[str, int] | None = None,
) -> None:
    """Fordel ledig Treeview-bredde til prioriterte kolonner.

    Eksisterende kolonnebredder brukes som base. Dersom treeviewen er bredere
    enn summen av kolonnene, fordeles overskytende plass til prioriterte
    kolonner slik at vi unngar store ubrukt hvite flater.
    """
    try:
        available = int(tree.winfo_width())
    except Exception:
        return
    if available <= 80:
        return

    widths = {
        col: safe_tree_column_width(tree, col) or analyse_treewidths.default_column_width(col)
        for col in columns
    }
    total = sum(widths.values())
    extra = available - total - 6
    if extra <= 8:
        return

    targets = [col for col in preferred_cols if col in columns]
    if not targets:
        targets = [col for col in columns if analyse_treewidths.column_anchor(col) == "w"]
    if not targets and columns:
        targets = [columns[-1]]
    if not targets:
        return

    weight_map = weights or {}
    total_weight = sum(max(1, int(weight_map.get(col, 1))) for col in targets)
    if total_weight <= 0:
        return

    remaining = extra
    for idx, col in enumerate(targets):
        if idx == len(targets) - 1:
            share = remaining
        else:
            share = max(0, int(extra * max(1, int(weight_map.get(col, 1))) / total_weight))
            remaining -= share
        try:
            tree.column(
                col,
                width=widths[col] + share,
                anchor=analyse_treewidths.column_anchor(col),
            )
        except Exception:
            continue


def sample_tx_values_for_width(*, page: Any, display_col: str, limit: int = 200) -> List[Any]:
    import pandas as pd
    df = page._df_filtered if isinstance(page._df_filtered, pd.DataFrame) else page.dataset
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []

    for source_col in analyse_columns.candidate_source_columns(display_col):
        if source_col in df.columns:
            try:
                return df[source_col].head(limit).tolist()
            except Exception:
                return []
    return []


# =====================================================================
# Hjelpere for TX/Pivot auto-fit + resize events
# =====================================================================

def remember_tx_column_widths(*, page: Any) -> None:
    tree = getattr(page, "_tx_tree", None)
    if tree is None:
        return
    widths = snapshot_tree_widths(tree, tree_display_columns(tree))
    if not widths:
        return
    page._tx_col_widths.update(widths)
    persist_saved_column_widths("analyse.tx_cols.widths", page._tx_col_widths)


def remember_pivot_column_widths(*, page: Any) -> None:
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    widths = snapshot_tree_widths(tree, tree_display_columns(tree))
    if not widths:
        return
    page._pivot_col_widths.update(widths)
    persist_saved_column_widths("analyse.pivot.widths", page._pivot_col_widths)


def remember_sb_column_widths(*, page: Any) -> None:
    tree = getattr(page, "_sb_tree", None)
    if tree is None:
        return
    widths = snapshot_tree_widths(tree, tree_display_columns(tree))
    if not widths:
        return
    if not hasattr(page, "_sb_col_widths") or page._sb_col_widths is None:
        page._sb_col_widths = {}
    page._sb_col_widths.update(widths)
    persist_saved_column_widths("analyse.sb_cols.widths", page._sb_col_widths)


def maybe_auto_fit_tx_tree(*, page: Any) -> None:
    tree = getattr(page, "_tx_tree", None)
    if tree is None:
        return
    force = getattr(page, "_tx_first_load", False)
    auto_fit_tree_columns(
        tree=tree,
        columns=tree_display_columns(tree),
        stored_widths=page._tx_col_widths,
        pref_key="analyse.tx_cols.widths",
        only_missing=not force,
        persist=force,
    )
    if force:
        page._tx_first_load = False


def maybe_auto_fit_pivot_tree(*, page: Any) -> None:
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    force = getattr(page, "_pivot_first_load", False)
    auto_fit_tree_columns(
        tree=tree,
        columns=tree_display_columns(tree),
        stored_widths=page._pivot_col_widths,
        pref_key="analyse.pivot.widths",
        only_missing=not force,
        persist=force,
        stretch_cols=set(PIVOT_STRETCH_COLS),
    )
    rebalance_pivot_tree_columns(page=page)
    if force:
        page._pivot_first_load = False


def auto_fit_tx_columns(*, page: Any) -> None:
    tree = getattr(page, "_tx_tree", None)
    if tree is None:
        return
    auto_fit_tree_columns(
        tree=tree,
        columns=tree_display_columns(tree),
        stored_widths=page._tx_col_widths,
        pref_key="analyse.tx_cols.widths",
        persist=True,
    )


def auto_fit_pivot_columns(*, page: Any) -> None:
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    auto_fit_tree_columns(
        tree=tree,
        columns=tree_display_columns(tree),
        stored_widths=page._pivot_col_widths,
        pref_key="analyse.pivot.widths",
        persist=True,
        stretch_cols=set(PIVOT_STRETCH_COLS),
    )
    rebalance_pivot_tree_columns(page=page)


def auto_fit_analyse_columns(*, page: Any) -> None:
    auto_fit_pivot_columns(page=page)
    auto_fit_tx_columns(page=page)


def rebalance_pivot_tree_columns(*, page: Any) -> None:
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    rebalance_tree_columns_to_available_width(
        tree=tree,
        columns=tree_display_columns(tree),
        preferred_cols=list(PIVOT_FILL_PRIORITY),
        weights=dict(PIVOT_FILL_WEIGHTS),
    )


def schedule_balance_pivot_tree(*, page: Any) -> None:
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    try:
        after_id = getattr(page, "_pivot_balance_after_id", None)
        if after_id:
            page.after_cancel(after_id)
    except Exception:
        pass

    def _run() -> None:
        try:
            page._pivot_balance_after_id = None
        except Exception:
            pass
        rebalance_pivot_tree_columns(page=page)

    try:
        page._pivot_balance_after_id = page.after_idle(_run)
    except Exception:
        rebalance_pivot_tree_columns(page=page)


# =====================================================================
# Dobbelt-klikk og mouse-release events
# =====================================================================

def on_tx_tree_double_click(*, page: Any, event: Any) -> Optional[str]:
    tree = getattr(page, "_tx_tree", None)
    if tree is None or event is None:
        return None
    try:
        region = str(tree.identify_region(event.x, event.y))
    except Exception:
        return None
    if region != "separator":
        return None

    col = column_id_from_event(tree, event)
    if not col:
        return "break"

    auto_fit_tree_columns(
        tree=tree,
        columns=tree_display_columns(tree),
        stored_widths=page._tx_col_widths,
        pref_key="analyse.tx_cols.widths",
        target_col=col,
        persist=True,
    )
    return "break"


def on_tx_tree_mouse_press(*, page: Any, event: Any) -> None:
    tree = getattr(page, "_tx_tree", None)
    if tree is None or event is None:
        return

    try:
        region = str(tree.identify_region(event.x, event.y))
    except Exception:
        region = ""
    if region != "heading":
        setattr(page, "_tx_header_drag", None)
        return

    col = column_id_from_event(tree, event)
    if not col:
        setattr(page, "_tx_header_drag", None)
        return

    setattr(
        page,
        "_tx_header_drag",
        {
            "source": col,
            "start_x": int(getattr(event, "x", 0) or 0),
            "active": False,
        },
    )


def on_tx_tree_mouse_drag(*, page: Any, event: Any) -> None:
    tree = getattr(page, "_tx_tree", None)
    drag = getattr(page, "_tx_header_drag", None)
    if tree is None or event is None or not isinstance(drag, dict):
        return

    if drag.get("active"):
        return

    try:
        region = str(tree.identify_region(event.x, event.y))
    except Exception:
        region = ""
    if region != "heading":
        return

    start_x = int(drag.get("start_x", 0) or 0)
    cur_x = int(getattr(event, "x", 0) or 0)
    if abs(cur_x - start_x) < TX_HEADER_DRAG_THRESHOLD_PX:
        return

    drag["active"] = True
    setattr(page, "_tx_header_drag", drag)
    try:
        tree._suppress_next_heading_sort = True  # type: ignore[attr-defined]
    except Exception:
        pass


def _finish_tx_header_drag(*, page: Any, event: Any) -> bool:
    tree = getattr(page, "_tx_tree", None)
    drag = getattr(page, "_tx_header_drag", None)
    setattr(page, "_tx_header_drag", None)
    if tree is None or event is None or not isinstance(drag, dict):
        return False

    if not drag.get("active"):
        return False

    source = str(drag.get("source") or "").strip()
    target = column_id_from_event(tree, event) or ""
    if not source or not target or source == target:
        return False

    order = analyse_columns.reorder_tx_column(
        getattr(page, "_tx_cols_order", ()),
        source=source,
        target=target,
        all_cols=get_all_tx_columns_for_chooser(page=page),
        pinned=getattr(page, "PINNED_TX_COLS", ("Konto", "Kontonavn")),
        required=getattr(page, "REQUIRED_TX_COLS", ("Konto", "Kontonavn", "Bilag")),
    )
    current_visible = list(getattr(page, "TX_COLS", ()))
    apply_tx_column_config(page=page, order=order, visible=current_visible)
    try:
        after_idle = getattr(tree, "after_idle", None)
        if callable(after_idle):
            after_idle(lambda: setattr(tree, "_suppress_next_heading_sort", False))
    except Exception:
        pass
    return True


def on_pivot_tree_double_click(*, page: Any, event: Any) -> Optional[str]:
    tree = getattr(page, "_pivot_tree", None)
    if tree is None or event is None:
        return None
    try:
        region = str(tree.identify_region(event.x, event.y))
    except Exception:
        return None
    if region != "separator":
        return None

    col = column_id_from_event(tree, event)
    if not col:
        return "break"

    auto_fit_tree_columns(
        tree=tree,
        columns=tree_display_columns(tree),
        stored_widths=page._pivot_col_widths,
        pref_key="analyse.pivot.widths",
        target_col=col,
        persist=True,
        stretch_cols=set(PIVOT_STRETCH_COLS),
    )
    return "break"


def on_tx_tree_mouse_release(*, page: Any, event: Any) -> None:
    tree = getattr(page, "_tx_tree", None)
    if tree is None or event is None:
        return

    if _finish_tx_header_drag(page=page, event=event):
        return

    try:
        region = str(tree.identify_region(event.x, event.y))
    except Exception:
        region = ""
    if region in {"separator", "heading"}:
        remember_tx_column_widths(page=page)


def on_pivot_tree_mouse_release(*, page: Any, event: Any) -> None:
    tree = getattr(page, "_pivot_tree", None)
    if tree is None or event is None:
        return
    if _finish_pivot_header_drag(page=page, event=event):
        return
    try:
        region = str(tree.identify_region(event.x, event.y))
    except Exception:
        region = ""
    if region in {"separator", "heading"}:
        remember_pivot_column_widths(page=page)


# =====================================================================
# Pivot-tree kolonne drag-to-reorder
# =====================================================================

_PIVOT_DRAG_THRESHOLD_PX = 10


def on_pivot_tree_mouse_press(*, page: Any, event: Any) -> None:
    """Registrer start av mulig kolonndrag på pivot-treet."""
    tree = getattr(page, "_pivot_tree", None)
    if tree is None or event is None:
        setattr(page, "_pivot_header_drag", None)
        return
    try:
        region = str(tree.identify_region(event.x, event.y))
    except Exception:
        region = ""
    if region != "heading":
        setattr(page, "_pivot_header_drag", None)
        return
    col = column_id_from_event(tree, event)
    if not col:
        setattr(page, "_pivot_header_drag", None)
        return
    # Pinned kolonner kan ikke flyttes
    pinned = set(getattr(page, "PIVOT_COLS_PINNED", ("Konto", "Kontonavn")))
    if col in pinned:
        setattr(page, "_pivot_header_drag", None)
        return
    setattr(page, "_pivot_header_drag", {
        "source": col, "start_x": event.x, "active": False,
    })


def on_pivot_tree_mouse_drag(*, page: Any, event: Any) -> None:
    """Aktiver drag-modus når muspekeren har beveget seg nok."""
    drag = getattr(page, "_pivot_header_drag", None)
    tree = getattr(page, "_pivot_tree", None)
    if tree is None or event is None or not isinstance(drag, dict):
        return
    if drag.get("active"):
        return
    if abs(event.x - int(drag.get("start_x", 0) or 0)) >= _PIVOT_DRAG_THRESHOLD_PX:
        drag["active"] = True
        setattr(page, "_pivot_header_drag", drag)
        try:
            tree.configure(cursor="fleur")
        except Exception:
            pass


def _finish_pivot_header_drag(*, page: Any, event: Any) -> bool:
    """Fullfør pivot kolonndrag — flytt kolonne til ny posisjon."""
    tree = getattr(page, "_pivot_tree", None)
    drag = getattr(page, "_pivot_header_drag", None)
    setattr(page, "_pivot_header_drag", None)
    try:
        tree.configure(cursor="")
    except Exception:
        pass
    if tree is None or event is None or not isinstance(drag, dict):
        return False
    if not drag.get("active"):
        return False

    source = str(drag.get("source") or "").strip()
    target = column_id_from_event(tree, event) or ""
    if not source or not target or source == target:
        return False

    visible = list(getattr(page, "_pivot_visible_cols", []))
    pinned  = list(getattr(page, "PIVOT_COLS_PINNED", ("Konto", "Kontonavn")))

    if source not in visible or target not in visible:
        return False
    if target in pinned:
        return False  # kan ikke dra inn i pinned-sonen

    # Flytt source til target-posisjon
    visible.remove(source)
    try:
        target_idx = visible.index(target)
    except ValueError:
        target_idx = len(visible)
    visible.insert(target_idx, source)

    page._pivot_visible_cols = visible
    apply_pivot_visible_columns(page=page)
    persist_pivot_visible_columns(page=page)

    # Hindre at sortering trigges etter drag
    try:
        setattr(tree, "_suppress_next_heading_sort", True)
        after_fn = getattr(page, "after_idle", None) or getattr(tree, "after_idle", None)
        if callable(after_fn):
            after_fn(lambda: setattr(tree, "_suppress_next_heading_sort", False))
    except Exception:
        pass
    return True


# =====================================================================
# Pivot-sortering: modus-avhengig aktiver/deaktiver
# =====================================================================

def refresh_pivot_sorting(*, page: Any, enable_fn: Any) -> None:
    """Slå sortering av/på i pivot-treet basert på aggregeringsmodus.

    Konto-moduser (SB-konto, HB-konto) → sortering aktivert
        (radene er uavhengige kontoer).
    RL-modus → sortering deaktivert (rekkefølge er semantisk, med summer).
    """
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return

    cols = tuple(getattr(page, "PIVOT_COLS", ()))
    agg = _read_agg_mode(page)

    if agg in ("SB-konto", "HB-konto") and enable_fn is not None:
        try:
            enable_fn(tree, columns=cols)
        except Exception:
            pass
    else:
        # Deaktiver: erstatt kommando med no-op
        for col in cols:
            try:
                tree.heading(col, command=lambda: None)
            except Exception:
                pass


# =====================================================================
# Reset kolonnebredder
# =====================================================================

def reset_pivot_column_widths(*, page: Any) -> None:
    """Slett lagrede bredder og bruk standardverdier igjen."""
    try:
        import preferences as _prefs
        _prefs.set("analyse.pivot.widths", {})
    except Exception:
        pass
    if hasattr(page, "_pivot_col_widths"):
        page._pivot_col_widths = {}
    # Kjør heading-oppdatering for å trigge default-bredder
    agg = _read_agg_mode(page) or "Regnskapslinje"
    try:
        import page_analyse_rl as _rl
        _rl.update_pivot_headings(page=page, mode=agg)
    except Exception:
        pass


def reset_tx_column_widths(*, page: Any) -> None:
    """Slett lagrede TX-kolonnebredder."""
    try:
        import preferences as _prefs
        _prefs.set("analyse.tx_cols.widths", {})
    except Exception:
        pass
    if hasattr(page, "_tx_col_widths"):
        page._tx_col_widths = {}


# =====================================================================
# TX-tree kolonnekonfigurasjon og sortering
# =====================================================================

def configure_tx_tree_columns(*, page: Any) -> None:
    if not getattr(page, "_tk_ok", False):
        return

    tree = getattr(page, "_tx_tree", None)
    if tree is None:
        return

    cols = tuple(getattr(page, "TX_COLS", page.TX_COLS_DEFAULT))

    try:
        tree.configure(columns=cols)
        tree["displaycolumns"] = cols
    except Exception:
        return

    for c in cols:
        try:
            tree.heading(c, text=c)
        except Exception:
            pass

        width = int(
            page._tx_col_widths.get(
                c,
                analyse_treewidths.suggest_column_width(
                    c, sample_tx_values_for_width(page=page, display_col=c)
                ),
            )
        )
        anchor = analyse_treewidths.column_anchor(c)
        try:
            tree.column(
                c,
                width=width,
                minwidth=analyse_treewidths.column_minwidth(c),
                anchor=anchor,
                stretch=False,
            )
        except Exception:
            pass

    enable_tx_sorting(page=page)


def enable_tx_sorting(*, page: Any, enable_fn: Any = None) -> None:
    """Aktiver klikk-for-sortering på transaksjonslisten.

    ``enable_fn`` kan sendes inn for testbarhet (monkeypatching).
    Hvis None, importeres fra ui_treeview_sort.
    """
    if not getattr(page, "_tk_ok", False):
        return
    if getattr(page, "_tx_tree", None) is None:
        return
    if enable_fn is None:
        try:
            from ui_treeview_sort import enable_treeview_sorting
            enable_fn = enable_treeview_sorting
        except Exception:
            return
    try:
        enable_fn(page._tx_tree, columns=page.TX_COLS)
    except Exception:
        pass
