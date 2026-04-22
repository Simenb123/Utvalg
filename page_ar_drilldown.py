"""page_ar_drilldown.py — Toplevel-dialog for å grave i eierkjeden.

Viser eiere av et orgnr som ekspanderbar Treeview. Klikk på en
selskaps-aksjonær henter dens eiere og legger dem inn som children
inline (ingen ny Toplevel per nivå). Hvis et selskap mangler i
RF-1086 for valgte år vises «Ikke importert for {år}» som markør.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from page_ar_formatters import _fmt_pct, _safe_text

log = logging.getLogger(__name__)

_PLACEHOLDER_PREFIX = "__placeholder__"


class _OwnerDrilldownDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        *,
        orgnr: str,
        name: str,
        lookup_year: str,
    ) -> None:
        super().__init__(master)
        self._orgnr = (orgnr or "").strip()
        self._name = (name or "").strip()
        self._lookup_year = (lookup_year or "").strip()

        title_label = self._name or self._orgnr or "Eierkjede"
        year_suffix = f" ({self._lookup_year})" if self._lookup_year else ""
        self.title(f"Eierkjede — {title_label}{year_suffix}")
        self.geometry("780x560")
        self.minsize(620, 420)
        self.resizable(True, True)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._iid_meta: dict[str, dict] = {}
        self._loaded_iids: set[str] = set()
        self._iid_counter = 0

        self._build_header()
        self._build_tree()
        self._build_buttons()

        self._root_iid = self._add_owner_node(
            parent="",
            orgnr=self._orgnr,
            name=self._name,
            kind="company",
            pct=None,
            depth=0,
        )
        self._tree.item(self._root_iid, open=True)
        self._load_children(self._root_iid)

        self.grab_set()
        self.focus_set()

    def _build_header(self) -> None:
        info = ttk.Frame(self, padding=(8, 6, 8, 0))
        info.grid(row=0, column=0, sticky="ew")
        info.columnconfigure(1, weight=1)

        company_text = self._name or "-"
        if self._orgnr:
            company_text = f"{company_text}  ({self._orgnr})" if self._name else self._orgnr
        year_text = self._lookup_year or "-"

        ttk.Label(info, text="Selskap:", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 8),
        )
        ttk.Label(info, text=company_text, wraplength=620, justify="left").grid(
            row=0, column=1, sticky="w",
        )
        ttk.Label(info, text="AR-år:", font=("Segoe UI", 9, "bold")).grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=(2, 0),
        )
        ttk.Label(info, text=year_text).grid(row=1, column=1, sticky="w", pady=(2, 0))

    def _build_tree(self) -> None:
        frame = ttk.Frame(self, padding=(8, 6, 8, 0))
        frame.grid(row=1, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        cols = ("pct", "type", "orgnr")
        tree = ttk.Treeview(frame, columns=cols, show="tree headings", selectmode="browse")
        tree.heading("#0", text="Aksjonær")
        tree.column("#0", width=340, stretch=True, anchor="w")
        tree.heading("pct", text="Andel")
        tree.column("pct", width=80, anchor="e", stretch=False)
        tree.heading("type", text="Type")
        tree.column("type", width=90, anchor="w", stretch=False)
        tree.heading("orgnr", text="Orgnr")
        tree.column("orgnr", width=110, anchor="w", stretch=False)

        ysb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")

        tree.tag_configure("missing", foreground="#A05A00")
        tree.tag_configure("person", foreground="#344054")

        tree.bind("<<TreeviewOpen>>", self._on_tree_open)

        self._tree = tree

    def _build_buttons(self) -> None:
        frame = ttk.Frame(self, padding=(8, 8, 8, 8))
        frame.grid(row=2, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)
        ttk.Button(frame, text="Lukk", command=self.destroy).grid(row=0, column=1)

    def _next_iid(self) -> str:
        self._iid_counter += 1
        return f"node-{self._iid_counter}"

    def _add_owner_node(
        self,
        *,
        parent: str,
        orgnr: str,
        name: str,
        kind: str,
        pct: float | None,
        depth: int,
    ) -> str:
        iid = self._next_iid()
        kind_norm = (kind or "").lower()
        kind_label = (
            "Person" if kind_norm == "person"
            else "Selskap" if kind_norm == "company"
            else (kind or "-")
        )
        pct_text = _fmt_pct(pct) if pct is not None else ""
        label = name or orgnr or "(uten navn)"
        tags: tuple[str, ...] = ("person",) if kind_norm == "person" else ()
        self._tree.insert(
            parent, "end", iid=iid,
            text=label,
            values=(pct_text, kind_label, (orgnr or "").strip()),
            tags=tags,
        )
        meta = {
            "orgnr": (orgnr or "").strip(),
            "name": name or "",
            "kind": kind_norm,
            "depth": depth,
        }
        self._iid_meta[iid] = meta
        if kind_norm == "company" and meta["orgnr"]:
            ph_iid = f"{_PLACEHOLDER_PREFIX}{iid}"
            self._tree.insert(iid, "end", iid=ph_iid, text="(klikk for å laste…)", values=("", "", ""))
        return iid

    def _on_tree_open(self, _event=None) -> None:
        iid = self._tree.focus()
        if not iid or iid in self._loaded_iids:
            return
        self._load_children(iid)

    def _load_children(self, iid: str) -> None:
        meta = self._iid_meta.get(iid)
        if not meta or iid in self._loaded_iids:
            return
        for child in list(self._tree.get_children(iid)):
            if child.startswith(_PLACEHOLDER_PREFIX):
                self._tree.delete(child)
        orgnr = meta["orgnr"]
        if not orgnr or not self._lookup_year:
            self._loaded_iids.add(iid)
            return
        try:
            import ar_store
            rows = list(ar_store.list_company_owners(orgnr, self._lookup_year) or [])
        except Exception:
            log.warning(
                "list_company_owners feilet for %s/%s",
                orgnr, self._lookup_year, exc_info=True,
            )
            rows = []
        if not rows:
            self._tree.insert(
                iid, "end",
                text=f"Ikke importert for {self._lookup_year}",
                values=("", "", ""),
                tags=("missing",),
            )
            self._loaded_iids.add(iid)
            return
        rows.sort(
            key=lambda r: (
                -float(r.get("ownership_pct") or 0.0),
                _safe_text(r.get("shareholder_name")).casefold(),
            )
        )
        for row in rows:
            self._add_owner_node(
                parent=iid,
                orgnr=_safe_text(row.get("shareholder_orgnr")),
                name=_safe_text(row.get("shareholder_name")),
                kind=_safe_text(row.get("shareholder_kind")),
                pct=float(row.get("ownership_pct") or 0.0),
                depth=meta["depth"] + 1,
            )
        self._loaded_iids.add(iid)

    def show(self) -> None:
        self.wait_window(self)
