"""Motpostanalyse (GUI) - actions/callbacks.

Denne modulen inneholder "hendelser"/knappehandlinger for motpostanalysen.

Hvorfor egen modul?
    - :mod:`views_motpost_konto` blir stor når UI + rendering + actions
      ligger i samme fil.
    - Ved refaktorering er det viktig å ikke bryte eksisterende tester.

Design:
    - Funksjoner tar inn dependencies eksplisitt der testene monkeypatcher
      navn i :mod:`views_motpost_konto`.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import logging
import os
from time import perf_counter
import subprocess
import sys


logger = logging.getLogger(__name__)


def on_select_motkonto(view: Any, *, konto_str_fn: Callable[[Any], str]) -> None:
    """Håndter valg av motkonto i pivot-tabellen."""

    sel = view._tree_summary.selection()
    if not sel:
        view._selected_motkonto = None
        view._refresh_details()
        return

    item = sel[0]
    motkonto = view._tree_summary.item(item, "values")[0]
    view._selected_motkonto = konto_str_fn(motkonto)
    view._refresh_details()


def mark_outlier(view: Any, *, messagebox_mod: Any, konto_str_fn: Callable[[Any], str]) -> None:
    sel = view._tree_summary.selection()
    if not sel:
        messagebox_mod.showinfo("Motpostanalyse", "Velg en eller flere motkontoer for å markere som outlier.")
        return
    for item in sel:
        motkonto = view._tree_summary.item(item, "values")[0]
        view._outliers.add(konto_str_fn(motkonto))
    view._render_summary()


def clear_outliers(view: Any) -> None:
    view._outliers.clear()
    view._render_summary()


def show_combinations(
    view: Any,
    *,
    build_motkonto_combinations_fn: Callable[..., Any],
    build_motkonto_combinations_per_selected_account_fn: Callable[..., Any],
    show_popup_fn: Callable[..., Any],
    messagebox_mod: Any,
) -> None:
    """Vis en oversikt over motkonto-kombinasjoner (popup)."""
    try:
        df_scope = getattr(getattr(view, "_data", None), "df_scope", None)
        if df_scope is None or getattr(df_scope, "empty", False):
            messagebox_mod.showinfo("Kombinasjoner", "Ingen data i grunnlaget.")
            return

        selected_accounts = getattr(getattr(view, "_data", None), "selected_accounts", ())
        if not selected_accounts:
            messagebox_mod.showinfo("Kombinasjoner", "Ingen valgte kontoer.")
            return

        selected_direction = getattr(getattr(view, "_data", None), "selected_direction", "Alle")
        konto_navn_map = getattr(view, "_konto_name_map", None)
        combo_cache = getattr(view, "_combo_popup_build_cache", None)
        if not isinstance(combo_cache, dict):
            combo_cache = {}
            view._combo_popup_build_cache = combo_cache

        cache_key = (
            id(df_scope),
            int(len(df_scope)),
            tuple(str(c) for c in df_scope.columns),
            tuple(str(a) for a in selected_accounts),
            str(selected_direction or "Alle"),
            tuple(sorted(str(k) for k in getattr(view, "_outliers", set()))),
            id(konto_navn_map),
        )

        cached_payload = combo_cache.get(cache_key)
        if cached_payload is not None:
            df_combo, df_combo_per = cached_payload
        else:
            t0 = perf_counter()

            # Nyere builders aksepterer selected_direction; eldre stubs/tests gjør ikke.
            try:
                df_combo = build_motkonto_combinations_fn(
                    df_scope,
                    selected_accounts,
                    selected_direction=selected_direction,
                    outlier_motkonto=view._outliers,
                    konto_navn_map=konto_navn_map,
                )
            except TypeError:
                df_combo = build_motkonto_combinations_fn(
                    df_scope,
                    selected_accounts,
                    outlier_motkonto=view._outliers,
                    konto_navn_map=konto_navn_map,
                )

            try:
                df_combo_per = build_motkonto_combinations_per_selected_account_fn(
                    df_scope,
                    selected_accounts,
                    selected_direction=selected_direction,
                    outlier_motkonto=view._outliers,
                    konto_navn_map=konto_navn_map,
                )
            except TypeError:
                df_combo_per = build_motkonto_combinations_per_selected_account_fn(
                    df_scope,
                    selected_accounts,
                    outlier_motkonto=view._outliers,
                    konto_navn_map=konto_navn_map,
                )

            combo_cache[cache_key] = (df_combo, df_combo_per)
            if len(combo_cache) > 8:
                combo_cache.pop(next(iter(combo_cache)), None)
            logger.debug(
                "motpost.show_combinations built popup data in %.3fs (scope_rows=%s, combos=%s, per_selected=%s)",
                perf_counter() - t0,
                len(df_scope),
                len(df_combo),
                len(df_combo_per),
            )

        bilag_total = int(df_scope["Bilag"].astype(str).nunique()) if "Bilag" in df_scope.columns else 0
        summary = (
            f"Antall kombinasjoner: {len(df_combo)} | Bilag i grunnlag: {bilag_total} | "
            f"Rader per konto: {len(df_combo_per)}"
        )

        outlier_combos = getattr(view, "_outlier_combinations", set())
        # Sørg for at attributtet finnes selv om objektet er konstruert via __new__ i tester
        view._outlier_combinations = outlier_combos

        # Status/kommentar per kombinasjon deles som referanse med popup slik at merkingen
        # (Forventet/Outlier/Umerket) og kommentarer bevares mellom åpninger og ved eksport.
        combo_status_map = getattr(view, "_combo_status_map", None)
        if combo_status_map is None:
            combo_status_map = {}
        view._combo_status_map = combo_status_map

        combo_comment_map = getattr(view, "_combo_comment_map", None)
        if combo_comment_map is None:
            combo_comment_map = {}
        view._combo_comment_map = combo_comment_map
        scope_mode = getattr(view, "_scope_mode", None)
        scope_items = getattr(view, "_scope_items", None)
        konto_regnskapslinje_map = getattr(view, "_konto_regnskapslinje_map", None)

        # Ny signatur (med drilldown/outliers). I tester kan funksjonen være monkeypatched
        # med eldre signatur, så vi faller tilbake ved TypeError.
        try:
            show_popup_fn(
                view,
                df_combos=df_combo,
                df_combo_per_selected=df_combo_per,
                title="Motkonto-kombinasjoner",
                summary=summary,
                df_scope=df_scope,
                selected_accounts=selected_accounts,
                selected_direction=selected_direction,
                konto_navn_map=konto_navn_map,
                scope_mode=scope_mode,
                scope_items=scope_items,
                konto_regnskapslinje_map=konto_regnskapslinje_map,
                outlier_combinations=outlier_combos,
                combo_status_map=combo_status_map,
                combo_comment_map=combo_comment_map,
                on_export_excel=view._export_excel,
            )
        except TypeError:
            show_popup_fn(
                view,
                df_combos=df_combo,
                df_combo_per_selected=df_combo_per,
                title="Motkonto-kombinasjoner",
                summary=summary,
            )
    except Exception as e:
        messagebox_mod.showerror("Kombinasjoner", f"Kunne ikke vise kombinasjoner:\n{e}")


def export_excel(
    view: Any,
    *,
    filedialog_mod: Any,
    messagebox_mod: Any,
    build_motpost_excel_workbook_fn: Callable[..., Any],
    outlier_combinations: Optional[set[str]] = None,
    combo_status_map: Optional[dict[str, str]] = None,
    combo_comment_map: Optional[dict[str, str]] = None,
) -> None:
    """Eksporterer motpostanalyse til Excel.

    OBS: For store datasett kan arket med full bilagsutskrift (outliers) bli
    ekstremt stort og/eller overskride Excel sin radbegrensning. Derfor gjør vi
    en rask forhåndstelling og lar brukeren velge om bilagslinjer skal tas med.
    """

    try:
        file_path = filedialog_mod.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            title="Eksporter motpostanalyse",
        )
        if not file_path:
            return

        path = str(file_path)

        # Finn outlier-kombinasjoner. Statuskart (combo_status_map) har prioritet.
        combo_status_map = combo_status_map if combo_status_map is not None else (getattr(view, "_combo_status_map", {}) or {})
        outlier_combinations = (
            outlier_combinations if outlier_combinations is not None else (getattr(view, "_outlier_combinations", set()) or set())
        )
        combo_comment_map = combo_comment_map if combo_comment_map is not None else (getattr(view, "_combo_comment_map", {}) or {})

        include_outlier_transactions = True

        # Best effort: forhåndstelling av hvor mange transaksjonslinjer som ville blitt eksportert.
        # Dette gir brukeren et bedre grunnlag for å velge "inkluder bilagslinjer".
        try:
            from .excel import normalize_combo_status_map
            from .combinations import build_bilag_to_motkonto_combo

            def _fmt_int(n: int) -> str:
                return f"{int(n):,}".replace(",", " ")

            status_norm = normalize_combo_status_map(combo_status_map)
            if status_norm:
                outlier_combo_set = {c for c, s in status_norm.items() if s == "outlier"}
            else:
                outlier_combo_set = set(outlier_combinations)

            df_scope = getattr(getattr(view, "_data", None), "df_scope", None)

            if outlier_combo_set and df_scope is not None and hasattr(df_scope, "empty") and not df_scope.empty:
                # df_scope fra MotpostData har normalt Bilag_str
                bilag_col = "Bilag_str" if "Bilag_str" in df_scope.columns else "Bilag"
                selected_accounts = list(getattr(getattr(view, "_data", None), "selected_accounts", []) or [])

                bilag_to_combo = build_bilag_to_motkonto_combo(df_scope, selected_accounts)
                out_bilag = {b for b, combo in bilag_to_combo.items() if combo in outlier_combo_set and str(b).strip()}

                if out_bilag:
                    if bilag_col == "Bilag_str":
                        line_count = int(df_scope["Bilag_str"].astype(str).isin(out_bilag).sum())
                    else:
                        # fallback hvis Bilag_str ikke finnes
                        line_count = int(df_scope["Bilag"].map(lambda v: str(v).strip()).isin(out_bilag).sum())

                    max_data_rows = 1_048_576 - 3  # tittel+notat+header

                    if line_count > max_data_rows:
                        # Kan ikke eksporteres med bilagslinjer i ett ark.
                        msg = (
                            f"Full bilagsutskrift (outliers) ville blitt ca {_fmt_int(line_count)} rader (Excel maks {_fmt_int(max_data_rows)}).\n\n"
                            "Dette kan ikke eksporteres i ett ark.\n\n"
                            "Vil du eksportere uten bilagslinjer i stedet?"
                        )
                        ask_yes_no = getattr(messagebox_mod, "askyesno", None)
                        if ask_yes_no is not None:
                            res = ask_yes_no("Motpostanalyse", msg)
                            if not res:
                                return
                        include_outlier_transactions = False
                    elif line_count > 0:
                        msg = (
                            f"Full bilagsutskrift (outliers): ca {_fmt_int(line_count)} rader fordelt på {_fmt_int(len(out_bilag))} bilag.\n\n"
                            "Å inkludere bilagslinjer gjør eksporten tregere og kan gi en svært stor Excel-fil.\n\n"
                            "Vil du inkludere bilagslinjer i Excel-eksporten?\n\n"
                            "Ja = inkluder bilagslinjer (større / tregere)\n"
                            "Nei = utelat bilagslinjer (raskere)\n"
                            "Avbryt = avbryt eksport"
                        )
                        ask_ync = getattr(messagebox_mod, "askyesnocancel", None)
                        if ask_ync is not None:
                            res = ask_ync("Motpostanalyse", msg)
                            if res is None:
                                return
                            include_outlier_transactions = bool(res)
                        else:
                            # fallback hvis askyesnocancel ikke finnes
                            ask_yes_no = getattr(messagebox_mod, "askyesno", None)
                            if ask_yes_no is not None:
                                include_outlier_transactions = bool(ask_yes_no("Motpostanalyse", msg))
        except Exception:
            # Hvis forhåndstelling feiler av en eller annen grunn, fortsett med standard.
            include_outlier_transactions = True

        # Bygg workbook
        selected_motkonto = getattr(view, "_selected_motkonto", None)
        outlier_motkonto = getattr(view, "_outliers", set())

        try:
            wb = build_motpost_excel_workbook_fn(
                view._data,
                outlier_motkonto=outlier_motkonto,
                selected_motkonto=selected_motkonto,
                combo_status_map=combo_status_map,
                combo_comment_map=combo_comment_map,
                outlier_combinations=outlier_combinations,
                include_outlier_transactions=include_outlier_transactions,
            )
        except TypeError:
            # Bakoverkompatibilitet hvis funksjonen ikke støtter flagget
            wb = build_motpost_excel_workbook_fn(
                view._data,
                outlier_motkonto=outlier_motkonto,
                selected_motkonto=selected_motkonto,
                combo_status_map=combo_status_map,
                combo_comment_map=combo_comment_map,
                outlier_combinations=outlier_combinations,
            )

        wb.save(path)
        messagebox_mod.showinfo("Motpostanalyse", f"Eksportert til Excel:\n{path}")

        _best_effort_open_file(path)
    except Exception as e:
        messagebox_mod.showerror("Motpostanalyse", f"Kunne ikke eksportere til Excel:\n{e}")


def open_bilag_drilldown(
    view: Any,
    bilag: str,
    *,
    konto_str_fn: Callable[[Any], str],
    messagebox_mod: Any,
) -> None:
    """Åpner bilagsdrilldown for ett bilag."""
    bilag = konto_str_fn(bilag)
    try:
        from views_bilag_drill import BilagDrillDialog

        dlg = BilagDrillDialog(view, view._df_all)
        dlg.preset_and_show(bilag)
    except Exception as e:
        messagebox_mod.showerror("Motpostanalyse", f"Kunne ikke åpne drilldown:\n{e}")


def drilldown(
    view: Any,
    *,
    treeview_first_selected_value_fn: Callable[..., Optional[str]],
    konto_str_fn: Callable[[Any], str],
    messagebox_mod: Any,
) -> None:
    bilag = treeview_first_selected_value_fn(view._tree_details, col_index=0, value_transform=konto_str_fn)
    if not bilag:
        messagebox_mod.showinfo("Motpostanalyse", "Velg et bilag i listen for å åpne drilldown.")
        return
    view._open_bilag_drilldown(bilag)


def _best_effort_open_file(path: str) -> None:
    """Best effort åpning av fil etter eksport."""
    try:
        if hasattr(os, "startfile"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        # Ikke kritisk om dette feiler (f.eks. i testmiljø).
        pass
