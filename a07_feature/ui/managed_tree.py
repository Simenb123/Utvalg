from __future__ import annotations

from tkinter import ttk
from typing import Sequence

from src.shared.columns_vocabulary import active_year_from_session, heading as global_column_heading
from src.shared.ui.managed_treeview import ColumnSpec, ManagedTreeview


_A07_TREE_PREF_PREFIX = "ui"
_A07_VIEW_PREFIX = "a07."

_A07_COMPAT_HEADING_OVERRIDES = {
    "GL_Belop": "SB",
    "GL_Sum": "SB forslag",
    "SamledeYtelser": "SB opplys.",
    "AgaGrunnlag": "SB AGA",
}

_A07_FALLBACK_HEADING_OVERRIDES = {
    "GL": "SB",
    "GL_Belop": "SB",
    "GL forslag": "SB forslag",
    "GL opplys.": "SB opplys.",
    "GL AGA": "SB AGA",
}

_A07_GLOBAL_VOCABULAR_IDS = {
    "Konto",
    "Kontonavn",
    "IB",
    "Endring",
    "UB",
    "Antall",
    "AntallKontoer",
    "Regnskapslinje",
}


def a07_managed_view_id(view_id: object) -> str:
    raw = str(view_id or "").strip()
    if not raw:
        raise ValueError("A07 ManagedTreeview requires a view_id.")
    return raw if raw.startswith(_A07_VIEW_PREFIX) else f"{_A07_VIEW_PREFIX}{raw}"


def a07_column_heading(column_id: object, fallback: object = "", *, year: int | None = None) -> str:
    cid = str(column_id or "").strip()
    fallback_s = str(fallback or "").strip()
    if cid in _A07_COMPAT_HEADING_OVERRIDES:
        return _A07_COMPAT_HEADING_OVERRIDES[cid]
    if fallback_s in _A07_FALLBACK_HEADING_OVERRIDES:
        return _A07_FALLBACK_HEADING_OVERRIDES[fallback_s]
    if cid in _A07_GLOBAL_VOCABULAR_IDS:
        global_id = "Antall" if cid == "AntallKontoer" else cid
        return global_column_heading(global_id, year=year)
    return fallback_s or cid


def a07_column_specs(
    columns: Sequence[tuple[str, str, int, str]],
    *,
    pinned_first: bool = True,
    sortable: bool = True,
    year: int | None = None,
) -> list[ColumnSpec]:
    if year is None:
        year = active_year_from_session()
    specs: list[ColumnSpec] = []
    for index, (column_id, heading, width, anchor) in enumerate(columns):
        cid = str(column_id or "").strip()
        if not cid:
            continue
        anchor_s = str(anchor or "w").strip() or "w"
        specs.append(
            ColumnSpec(
                id=cid,
                heading=a07_column_heading(cid, heading, year=year),
                width=int(width or 100),
                minwidth=40,
                anchor=anchor_s,
                stretch=(anchor_s == "w" and int(width or 100) >= 120),
                visible_by_default=True,
                pinned=bool(pinned_first and index == 0),
                sortable=sortable,
            )
        )
    return specs


class A07PageManagedTreeMixin:
    def _managed_tree_registry(self) -> dict[str, ManagedTreeview]:
        registry = getattr(self, "_a07_managed_treeviews", None)
        if not isinstance(registry, dict):
            registry = {}
            self._a07_managed_treeviews = registry
        return registry

    def _managed_tree_for(self, tree: ttk.Treeview) -> ManagedTreeview | None:
        for manager in self._managed_tree_registry().values():
            if getattr(manager, "tree", None) is tree:
                return manager
        return None

    def _build_managed_tree_tab(
        self,
        parent: ttk.Frame,
        columns: Sequence[tuple[str, str, int, str]],
        *,
        view_id: str,
        default_visible: Sequence[str] | None = None,
        pinned_cols: Sequence[str] | None = None,
        sortable: bool = True,
        selectmode: str | None = None,
        height: int | None = None,
        on_body_right_click=None,
    ) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)

        column_ids = [str(column_id) for column_id, *_rest in columns]
        tree = ttk.Treeview(frame, columns=column_ids, show="headings")
        if selectmode:
            tree.configure(selectmode=selectmode)
        if height is not None:
            tree.configure(height=height)

        manager = ManagedTreeview(
            tree,
            view_id=a07_managed_view_id(view_id),
            column_specs=a07_column_specs(columns, pinned_first=not pinned_cols, sortable=sortable),
            pref_prefix=_A07_TREE_PREF_PREFIX,
            default_visible=default_visible,
            pinned_cols=pinned_cols,
            on_body_right_click=on_body_right_click,
            auto_bind=True,
        )
        self._managed_tree_registry()[a07_managed_view_id(view_id)] = manager

        ybar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)

        tree.pack(side="left", fill="both", expand=True)
        ybar.pack(side="right", fill="y")
        xbar.pack(side="bottom", fill="x")
        return tree


__all__ = [
    "A07PageManagedTreeMixin",
    "a07_column_heading",
    "a07_column_specs",
    "a07_managed_view_id",
]
