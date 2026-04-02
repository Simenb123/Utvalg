"""treeview_column_manager.py — Gjenbrukbar kolonnevisning for ttk.Treeview.

Gir hoeyreklikk-meny paa header for aa velge synlige kolonner,
full kolonnevelger-dialog, og persistens via preferences.
"""

from __future__ import annotations

import logging
from typing import Sequence

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

logger = logging.getLogger(__name__)


class TreeviewColumnManager:
    """Haandterer kolonnevisning, hoeyreklikk-meny og persistens for ett Treeview."""

    def __init__(
        self,
        tree: ttk.Treeview,
        *,
        view_id: str,
        all_cols: Sequence[str],
        default_visible: Sequence[str] | None = None,
        pinned_cols: Sequence[str] = (),
        pref_prefix: str = "consolidation",
    ) -> None:
        self._tree = tree
        self._view_id = view_id
        self._all_cols = list(all_cols)
        self._default_visible = list(default_visible or all_cols)
        self._pinned = set(pinned_cols)
        self._pref_prefix = pref_prefix
        self._pref_key = f"{pref_prefix}.{view_id}.visible_cols"
        self._order_key = f"{pref_prefix}.{view_id}.column_order"

        # Load saved visibility + order or use defaults
        self._visible: list[str] = list(self._default_visible)
        self._order: list[str] = list(all_cols)
        self.load_from_preferences()
        self._normalize_order()
        self.apply_visible()

    # ------------------------------------------------------------------
    # Pinned-first invariant
    # ------------------------------------------------------------------

    def _normalize_order(self) -> None:
        """Soeerg for at pinned-kolonner alltid er foerst i rekkefoeljen."""
        if not self._pinned:
            return
        pinned_in_order = [c for c in self._order if c in self._pinned]
        rest = [c for c in self._order if c not in self._pinned]
        self._order = pinned_in_order + rest

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def load_from_preferences(self) -> None:
        """Last lagrede synlige kolonner og rekkefoelje fra preferences."""
        try:
            import preferences
            stored = preferences.get(self._pref_key, None)
            stored_order = preferences.get(self._order_key, None)
        except Exception:
            stored = None
            stored_order = None

        # Restore order
        if isinstance(stored_order, list) and stored_order:
            valid_order = [c for c in stored_order if c in self._all_cols]
            # Add any all_cols not in stored order at the end
            for c in self._all_cols:
                if c not in valid_order:
                    valid_order.append(c)
            if valid_order:
                self._order = valid_order
        self._normalize_order()

        # Restore visibility
        if isinstance(stored, list) and stored:
            valid = [c for c in stored if c in self._all_cols]
            # Soeerg for at pinned-kolonner alltid er med
            for p in self._pinned:
                if p in self._all_cols and p not in valid:
                    valid.insert(0, p)
            if valid:
                self._visible = valid
                return
        self._visible = list(self._default_visible)

    def save_to_preferences(self) -> None:
        """Lagre synlige kolonner og rekkefoelje til preferences."""
        try:
            import preferences
            preferences.set(self._pref_key, list(self._visible))
            preferences.set(self._order_key, list(self._order))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def apply_visible(self) -> None:
        """Sett displaycolumns paa treet basert paa synlig sett og rekkefoelje."""
        vis_set = set(self._visible) & set(self._all_cols)
        if not vis_set:
            vis_set = set(self._default_visible)
        # Build displaycolumns in user-chosen order
        ordered = [c for c in self._order if c in vis_set]
        # Add any visible cols not yet in order (safety)
        for c in self._visible:
            if c in vis_set and c not in ordered:
                ordered.append(c)
        try:
            self._tree["displaycolumns"] = ordered
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Toggle / Reset
    # ------------------------------------------------------------------

    def toggle_column(self, col: str) -> None:
        """Slaa av/paa en kolonne."""
        if col in self._pinned:
            return
        if col in self._visible:
            self._visible.remove(col)
        else:
            # Innsett paa riktig posisjon (bevar brukerens rekkefoelje)
            pos = 0
            for c in self._order:
                if c == col:
                    break
                if c in self._visible:
                    pos += 1
            self._visible.insert(pos, col)
        self.apply_visible()
        self.save_to_preferences()

    def reorder_columns(self, source: str, target: str) -> bool:
        """Flytt en kolonne foran en annen og bevar pinned-regler."""
        source = str(source or "").strip()
        target = str(target or "").strip()
        if not source or not target or source == target:
            return False
        if source not in self._order or target not in self._order:
            return False
        if source in self._pinned:
            return False

        moved = list(self._order)
        moved.remove(source)
        insert_at = moved.index(target)
        moved.insert(insert_at, source)
        self._order = moved
        self._normalize_order()
        self.apply_visible()
        self.save_to_preferences()
        return True

    def set_visible_columns(self, visible_cols: Sequence[str]) -> None:
        """Sett synlige kolonner eksplisitt og persistér."""
        visible = [c for c in visible_cols if c in self._all_cols]
        for p in self._pinned:
            if p in self._all_cols and p not in visible:
                visible.insert(0, p)
        self._visible = visible or list(self._default_visible)
        self.apply_visible()
        self.save_to_preferences()

    def reset_to_default(self) -> None:
        """Tilbakestill til standard synlige kolonner og rekkefoelje."""
        self._visible = list(self._default_visible)
        self._order = list(self._all_cols)
        self._normalize_order()
        self.apply_visible()
        self.save_to_preferences()

    # ------------------------------------------------------------------
    # Dynamic columns (for trees that rebuild their columns)
    # ------------------------------------------------------------------

    def update_columns(self, new_all_cols: Sequence[str]) -> None:
        """Oppdater kolonnesett (for dynamiske trær som _tree_result).

        Bevarer brukerens synlighets- og rekkefoelje-valg for kolonner som
        fortsatt finnes. Nye kolonner legges til som synlige.
        """
        old_all = set(self._all_cols)
        self._all_cols = list(new_all_cols)
        new_set = set(new_all_cols)

        # Update order: keep existing order for cols that still exist, append new ones
        kept_order = [c for c in self._order if c in new_set]
        for c in new_all_cols:
            if c not in old_all and c not in kept_order:
                kept_order.append(c)
        self._order = kept_order if kept_order else list(new_all_cols)
        self._normalize_order()

        # Behold eksisterende synlige som fortsatt er gyldige
        kept = [c for c in self._visible if c in new_set]
        # Legg til nye kolonner som ikke fantes foer
        for c in new_all_cols:
            if c not in old_all and c not in kept:
                kept.append(c)
        # Soeerg for pinned
        for p in self._pinned:
            if p in new_set and p not in kept:
                kept.insert(0, p)

        self._visible = kept if kept else list(new_all_cols)
        self._default_visible = list(new_all_cols)
        self.apply_visible()

    # ------------------------------------------------------------------
    # Header right-click menu
    # ------------------------------------------------------------------

    def show_header_menu(self, event) -> None:
        """Vis hoeyreklikk-meny for kolonnevalg."""
        if tk is None:
            return

        menu = tk.Menu(self._tree, tearoff=0)

        all_set = set(self._all_cols)
        for col in self._order:
            if col not in all_set or col in self._pinned:
                continue
            # Bruk heading-tekst som visningsnavn
            display_name = col
            try:
                heading_text = self._tree.heading(col, "text")
                if heading_text and heading_text.strip():
                    display_name = heading_text.strip()
            except Exception:
                pass

            is_visible = col in self._visible
            label = f"{'✓  ' if is_visible else '    '}{display_name}"
            menu.add_command(
                label=label,
                command=lambda c=col: self.toggle_column(c),
            )

        menu.add_separator()
        menu.add_command(label="Standard", command=self.reset_to_default)
        menu.add_command(label="Kolonner\u2026", command=self.open_chooser_dialog)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        except Exception:
            pass

    def on_right_click(self, event) -> str | None:
        """Generisk hoeyreklikk-handler som viser meny kun paa header.

        Returnerer "break" om klikket var paa header (spiser eventet),
        ellers None (lar andre handlere ta over).
        """
        try:
            region = str(self._tree.identify_region(event.x, event.y))
        except Exception:
            return None

        if region == "heading":
            self.show_header_menu(event)
            return "break"
        return None

    # ------------------------------------------------------------------
    # Full column chooser dialog
    # ------------------------------------------------------------------

    def open_chooser_dialog(self) -> None:
        """Aapne full kolonnevelger-dialog."""
        try:
            from views_column_chooser import open_column_chooser
        except ImportError:
            return

        result = open_column_chooser(
            self._tree,
            all_cols=self._all_cols,
            visible_cols=self._visible,
            initial_order=self._order,
            default_visible_cols=self._default_visible,
            default_order=list(self._all_cols),
        )
        if result is not None:
            order, visible = result
            # Soeerg for pinned
            for p in self._pinned:
                if p in self._all_cols and p not in visible:
                    visible.insert(0, p)
            self._order = [c for c in order if c in self._all_cols]
            self._normalize_order()
            self._visible = visible
            self.apply_visible()
            self.save_to_preferences()
