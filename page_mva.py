"""page_mva.py — MVA-analyse fane.

Viser MVA-kontoer gruppert via konto_klassifisering.
Krever at brukeren har klassifisert kontoene i Analyse-fanen.

Fanen er delt i to:
  - Sammendrag: sum per MVA-gruppe (IB, Bevegelse, UB) + avstemmingsrad
  - Kontoer: enkeltkontoer for valgt gruppe
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

import formatting

# ---------------------------------------------------------------------------
# MVA-gruppe-konfigurasjon
# ---------------------------------------------------------------------------

# Standard gruppenavn for MVA (fra konto_klassifisering.DEFAULT_GROUPS)
_GRP_INNG  = "Inngående MVA"
_GRP_UTG   = "Utgående MVA"
_GRP_SKYLDIG = "Skyldig MVA"

_MVA_GROUPS_ORDERED = [_GRP_UTG, _GRP_INNG, _GRP_SKYLDIG]

# Farge-tags
_TAG_HEADER   = "header"
_TAG_RECON    = "recon"
_TAG_OK       = "ok"
_TAG_AVVIK    = "avvik"
_TAG_SELECTED = "selected_grp"


# ---------------------------------------------------------------------------
# Hjelpefunksjoner
# ---------------------------------------------------------------------------

def _sum_for_group(
    sb_df: Any,
    gruppe_mapping: dict[str, str],
    gruppe: str,
    col_map: dict[str, str],
) -> tuple[float, float, float]:
    """Returner (IB, bevegelse, UB) for alle kontoer i gitt gruppe."""
    import pandas as pd

    kontoer_i_gruppe = {k for k, v in gruppe_mapping.items() if v == gruppe}
    if not kontoer_i_gruppe:
        return 0.0, 0.0, 0.0

    konto_src = col_map.get("konto", "")
    if not konto_src:
        return 0.0, 0.0, 0.0

    mask = sb_df[konto_src].astype(str).isin(kontoer_i_gruppe)
    sub = sb_df[mask]

    def _sum(key: str) -> float:
        col = col_map.get(key, "")
        if not col or col not in sub.columns:
            return 0.0
        return float(pd.to_numeric(sub[col], errors="coerce").fillna(0.0).sum())

    return _sum("ib"), _sum("endring"), _sum("ub")


def _resolve_sb_columns(sb_df: Any) -> dict[str, str]:
    col_map: dict[str, str] = {}
    for c in sb_df.columns:
        cl = c.lower()
        if cl == "konto":
            col_map["konto"] = c
        elif cl == "kontonavn":
            col_map["kontonavn"] = c
        elif cl == "ib":
            col_map["ib"] = c
        elif cl in ("netto", "endring"):
            col_map["endring"] = c
        elif cl == "ub":
            col_map["ub"] = c
    return col_map


# ---------------------------------------------------------------------------
# Hoved-side
# ---------------------------------------------------------------------------

class MvaPage(ttk.Frame):  # type: ignore[misc]

    def __init__(self, master: Any) -> None:
        super().__init__(master)
        self._analyse_page: Any = None
        self._gruppe_mapping: dict[str, str] = {}
        self._col_map: dict[str, str] = {}
        self._sb_df: Any = None
        self._selected_gruppe: str = ""

        if tk is None:
            return

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_ui()

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def set_analyse_page(self, page: Any) -> None:
        self._analyse_page = page

    def refresh_from_session(self, session: Any = None) -> None:
        self._load_data()
        self._refresh_all()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Toolbar
        tb = ttk.Frame(self, padding=(6, 4))
        tb.grid(row=0, column=0, sticky="ew")

        ttk.Label(tb, text="MVA-analyse",
                  font=("TkDefaultFont", 11, "bold")).pack(side="left", padx=(0, 12))
        ttk.Button(tb, text="Oppdater", command=self._refresh_all,
                   width=10).pack(side="left")
        ttk.Button(tb, text="Eksporter til Excel\u2026",
                   command=self._export_excel).pack(side="left", padx=(6, 0))
        self._status_lbl = ttk.Label(tb, text="", foreground="#555")
        self._status_lbl.pack(side="left", padx=(12, 0))

        ttk.Label(
            tb,
            text="Klassifiser kontoer i Analyse-fanen for å aktivere MVA-analyse.",
            foreground="#888",
        ).pack(side="right", padx=(0, 8))

        # Hoved-pane: topp = sammendrag, bunn = kontoer
        pane = ttk.PanedWindow(self, orient="vertical")
        pane.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))

        # --- Sammendrag ---
        top_frame = ttk.LabelFrame(pane, text="Sammendrag", padding=(4, 4))
        top_frame.columnconfigure(0, weight=1)
        top_frame.rowconfigure(0, weight=1)
        pane.add(top_frame, weight=2)

        self._summary_tree = self._make_summary_tree(top_frame)
        self._summary_tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(top_frame, orient="vertical",
                             command=self._summary_tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self._summary_tree.configure(yscrollcommand=vsb.set)
        self._summary_tree.bind("<<TreeviewSelect>>", self._on_summary_select)

        # --- Kontoer ---
        bot_frame = ttk.LabelFrame(pane, text="Kontoer i valgt gruppe", padding=(4, 4))
        bot_frame.columnconfigure(0, weight=1)
        bot_frame.rowconfigure(0, weight=1)
        pane.add(bot_frame, weight=3)

        self._konto_tree = self._make_konto_tree(bot_frame)
        self._konto_tree.grid(row=0, column=0, sticky="nsew")
        vsb2 = ttk.Scrollbar(bot_frame, orient="vertical",
                              command=self._konto_tree.yview)
        vsb2.grid(row=0, column=1, sticky="ns")
        self._konto_tree.configure(yscrollcommand=vsb2.set)

    def _make_summary_tree(self, parent: Any) -> Any:
        cols = ("gruppe", "ib", "bevegelse", "ub")
        tree = ttk.Treeview(parent, columns=cols, show="headings",
                             selectmode="browse", height=12)
        tree.heading("gruppe",    text="Gruppe",    anchor="w")
        tree.heading("ib",        text="IB",        anchor="e")
        tree.heading("bevegelse", text="Bevegelse", anchor="e")
        tree.heading("ub",        text="UB",        anchor="e")
        tree.column("gruppe",    width=260, anchor="w", stretch=True)
        tree.column("ib",        width=140, anchor="e", stretch=False)
        tree.column("bevegelse", width=140, anchor="e", stretch=False)
        tree.column("ub",        width=140, anchor="e", stretch=False)

        tree.tag_configure(_TAG_HEADER,  background="#E8EFF7",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure(_TAG_RECON,   background="#F5F5F5",
                           font=("TkDefaultFont", 9, "italic"))
        tree.tag_configure(_TAG_OK,      foreground="#1B7F35",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure(_TAG_AVVIK,   foreground="#C0392B",
                           font=("TkDefaultFont", 9, "bold"))
        return tree

    def _make_konto_tree(self, parent: Any) -> Any:
        cols = ("konto", "kontonavn", "ib", "bevegelse", "ub")
        tree = ttk.Treeview(parent, columns=cols, show="headings",
                             selectmode="browse")
        tree.heading("konto",    text="Konto",    anchor="w")
        tree.heading("kontonavn",text="Kontonavn",anchor="w")
        tree.heading("ib",       text="IB",       anchor="e")
        tree.heading("bevegelse",text="Bevegelse",anchor="e")
        tree.heading("ub",       text="UB",       anchor="e")
        tree.column("konto",     width=80,  anchor="w", stretch=False)
        tree.column("kontonavn", width=280, anchor="w", stretch=True)
        tree.column("ib",        width=130, anchor="e", stretch=False)
        tree.column("bevegelse", width=130, anchor="e", stretch=False)
        tree.column("ub",        width=130, anchor="e", stretch=False)
        tree.tag_configure("neg", foreground="red")
        return tree

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _load_data(self) -> None:
        import pandas as pd
        self._sb_df = None
        self._gruppe_mapping = {}
        self._col_map = {}

        page = self._analyse_page
        if page is None:
            return

        sb_df = getattr(page, "_rl_sb_df", None)
        if sb_df is None or not isinstance(sb_df, pd.DataFrame) or sb_df.empty:
            return

        # Prøv å hente effektiv (filtrert) SB-df
        try:
            sb_df = page._get_effective_sb_df()
        except Exception:
            pass

        self._sb_df = sb_df
        self._col_map = _resolve_sb_columns(sb_df)

        # Last klassifisering
        try:
            import konto_klassifisering as _kk
            import session as _session
            client = getattr(_session, "client", None) or ""
            if client:
                self._gruppe_mapping = _kk.load(client)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh_all(self) -> None:
        self._load_data()
        self._populate_summary()
        self._populate_kontoer(self._selected_gruppe)
        self._update_status()

    def _update_status(self) -> None:
        n = len(self._gruppe_mapping)
        if n == 0:
            self._status_lbl.configure(
                text="Ingen kontoer klassifisert. Bruk 'Klassifiser kontoer' i Analyse-fanen."
            )
        else:
            import konto_klassifisering as _kk
            groups = _kk.all_groups_in_use(self._gruppe_mapping)
            mva_grps = [g for g in groups if "mva" in g.lower()]
            self._status_lbl.configure(
                text=f"{n} kontoer klassifisert | {len(mva_grps)} MVA-grupper"
            )

    def _populate_summary(self) -> None:
        tree = self._summary_tree
        tree.delete(*tree.get_children())

        if self._sb_df is None or not self._gruppe_mapping:
            tree.insert("", "end", values=(
                "Ingen klassifiserte kontoer funnet.",
                "", "", "",
            ), tags=(_TAG_RECON,))
            return

        import konto_klassifisering as _kk
        all_groups = _kk.all_groups_in_use(self._gruppe_mapping)

        # Skill MVA-grupper fra andre grupper
        mva_groups = [g for g in _MVA_GROUPS_ORDERED if g in all_groups]
        other_mva  = [g for g in all_groups
                      if "mva" in g.lower() and g not in mva_groups]
        mva_groups += other_mva

        # --- MVA-seksjon ---
        if mva_groups:
            tree.insert("", "end", iid="_hdr_mva",
                        values=("MVA-kontoer", "", "", ""),
                        tags=(_TAG_HEADER,))

            totals: dict[str, tuple[float, float, float]] = {}
            for g in mva_groups:
                ib, bev, ub = _sum_for_group(
                    self._sb_df, self._gruppe_mapping, g, self._col_map)
                totals[g] = (ib, bev, ub)
                tree.insert("", "end", iid=f"_grp_{g}",
                            values=(f"  {g}",
                                    formatting.fmt_amount(ib),
                                    formatting.fmt_amount(bev),
                                    formatting.fmt_amount(ub)),
                            tags=())

            # Avstemming
            self._insert_recon(tree, totals)

        # --- Andre klassifiserte grupper ---
        other_groups = [g for g in all_groups if g not in mva_groups]
        if other_groups:
            tree.insert("", "end", iid="_hdr_andre",
                        values=("Andre klassifiserte grupper", "", "", ""),
                        tags=(_TAG_HEADER,))
            for g in other_groups:
                ib, bev, ub = _sum_for_group(
                    self._sb_df, self._gruppe_mapping, g, self._col_map)
                tree.insert("", "end", iid=f"_grp_{g}",
                            values=(f"  {g}",
                                    formatting.fmt_amount(ib),
                                    formatting.fmt_amount(bev),
                                    formatting.fmt_amount(ub)),
                            tags=())

    def _export_excel(self) -> None:
        try:
            import session as _session
            import analyse_export_excel as _xls
            client = getattr(_session, "client", None) or ""
            year   = str(getattr(_session, "year", "") or "")
            path = _xls.open_save_dialog(
                title="Eksporter MVA-analyse",
                default_filename=f"mva_analyse_{client}_{year}.xlsx".strip("_"),
                master=self,
            )
            if not path:
                return
            sum_sheet = _xls.treeview_to_sheet(
                self._summary_tree,
                title="Sammendrag",
                heading="MVA-analyse — Sammendrag",
                bold_tags=(_TAG_HEADER, _TAG_RECON, _TAG_OK, _TAG_AVVIK),
                bg_tags={_TAG_HEADER: "BDD7EE", _TAG_OK: "E8F5E9", _TAG_AVVIK: "FFEBEE"},
            )
            konto_sheet = _xls.treeview_to_sheet(
                self._konto_tree,
                title="Kontoer",
                heading=f"Kontoer: {self._selected_gruppe}" if self._selected_gruppe
                        else "Kontoer",
                bold_tags=(_TAG_HEADER,),
                bg_tags={_TAG_HEADER: "BDD7EE"},
            )
            _xls.export_and_open(path, [sum_sheet, konto_sheet],
                                  title="MVA-analyse", client=client, year=year)
        except Exception as e:
            log.exception("MVA Excel-eksport feilet: %s", e)

    def _insert_recon(
        self,
        tree: Any,
        totals: dict[str, tuple[float, float, float]],
    ) -> None:
        """Sett inn avstemmingsrader under MVA-grupper."""
        def _ub(g: str) -> float:
            return totals.get(g, (0.0, 0.0, 0.0))[2]
        def _bev(g: str) -> float:
            return totals.get(g, (0.0, 0.0, 0.0))[1]

        utg_ub    = _ub(_GRP_UTG)
        inng_ub   = _ub(_GRP_INNG)
        skyldig_ub = _ub(_GRP_SKYLDIG)

        netto_ub  = utg_ub - inng_ub   # Netto MVA til betaling
        diff      = netto_ub + skyldig_ub  # Skyldig MVA er kredit → bør motsvare netto

        # Netto MVA-rad
        tree.insert("", "end", iid="_recon_netto",
                    values=(
                        "  → Netto MVA (Utgående − Inngående)",
                        "",
                        "",
                        formatting.fmt_amount(netto_ub),
                    ), tags=(_TAG_RECON,))

        # Differanse-rad
        ok = abs(diff) < 1.0
        tag = _TAG_OK if ok else _TAG_AVVIK
        diff_txt = "✓ Avstemt" if ok else f"⚠ Avvik: {formatting.fmt_amount(diff)}"
        tree.insert("", "end", iid="_recon_diff",
                    values=(
                        f"  → Skyldig MVA (saldo) {diff_txt}",
                        "",
                        "",
                        formatting.fmt_amount(skyldig_ub),
                    ), tags=(tag,))

    # ------------------------------------------------------------------
    # Konto-drill
    # ------------------------------------------------------------------

    def _on_summary_select(self, _event: Any = None) -> None:
        sel = self._summary_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if not iid.startswith("_grp_"):
            return
        gruppe = iid[len("_grp_"):]
        self._selected_gruppe = gruppe
        self._populate_kontoer(gruppe)
        # Oppdater LabelFrame-tittel
        try:
            parent = self._konto_tree.master
            parent.configure(text=f"Kontoer: {gruppe}")
        except Exception:
            pass

    def _populate_kontoer(self, gruppe: str) -> None:
        import pandas as pd
        tree = self._konto_tree
        tree.delete(*tree.get_children())

        if not gruppe or self._sb_df is None:
            return

        kontoer_i_gruppe = {k for k, v in self._gruppe_mapping.items()
                            if v == gruppe}
        if not kontoer_i_gruppe:
            return

        konto_src = self._col_map.get("konto", "")
        if not konto_src:
            return

        mask = self._sb_df[konto_src].astype(str).isin(kontoer_i_gruppe)
        sub = self._sb_df[mask].copy()

        # Sorter etter konto numerisk
        try:
            sub = sub.sort_values(konto_src,
                                  key=lambda s: pd.to_numeric(s, errors="coerce"))
        except Exception:
            pass

        navn_col  = self._col_map.get("kontonavn", "")
        ib_col    = self._col_map.get("ib", "")
        endr_col  = self._col_map.get("endring", "")
        ub_col    = self._col_map.get("ub", "")

        sum_ib = sum_bev = sum_ub = 0.0

        for tup in sub.itertuples(index=False):
            cols = list(sub.columns)

            def _get(col: str, default: Any = "") -> Any:
                if not col or col not in cols:
                    return default
                return tup[cols.index(col)]

            konto = str(_get(konto_src, "")).strip()
            navn  = str(_get(navn_col, "")).strip()
            ib    = float(pd.to_numeric(_get(ib_col,   0), errors="coerce") or 0)
            bev   = float(pd.to_numeric(_get(endr_col, 0), errors="coerce") or 0)
            ub    = float(pd.to_numeric(_get(ub_col,   0), errors="coerce") or 0)

            sum_ib  += ib
            sum_bev += bev
            sum_ub  += ub

            tags = ("neg",) if ub < 0 else ()
            tree.insert("", "end", values=(
                konto, navn,
                formatting.fmt_amount(ib),
                formatting.fmt_amount(bev),
                formatting.fmt_amount(ub),
            ), tags=tags)

        # Sum-rad
        tree.insert("", "end", values=(
            "Σ", f"{len(sub)} kontoer",
            formatting.fmt_amount(sum_ib),
            formatting.fmt_amount(sum_bev),
            formatting.fmt_amount(sum_ub),
        ), tags=(_TAG_HEADER,))
