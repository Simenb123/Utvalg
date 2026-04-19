"""page_analyse_columns_menu.py

Kolonne-kontekstmeny for pivot-treet + kommentar/handlings-popup-helpere.

Utskilt fra page_analyse_columns.py. Re-eksportert via page_analyse_columns
som fasade for bakoverkompatibilitet.
"""

from __future__ import annotations

from typing import Any


def show_pivot_column_menu(*, page: Any, event: Any) -> None:
    """Vis høyreklikkmeny for å vise/skjule pivot-kolonner."""
    if not getattr(page, "_tk_ok", False) or event is None:
        return
    try:
        import tkinter as tk
    except Exception:
        return

    # Lazy import for å unngå sirkularitet med page_analyse_columns-fasaden.
    from page_analyse_columns import (
        _read_agg_mode,
        reset_pivot_columns,
        toggle_pivot_column,
    )

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
