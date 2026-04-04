"""page_lonn.py — Lønnsanalyse fane.

Sammenstiller lønnsposter gruppert via konto_klassifisering.
Utfører kontrollberegninger:
  - Feriepenger: lønnsgrunnlag × sats ≈ kostnadsført feriepenger
  - AGA: (lønn + feriepenger) × sats ≈ kostnadsført AGA
  - Balansesjekk: skyldig lønn/feriepenger/AGA mot kostnadsført
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
# Lønn-gruppe-konfigurasjon
# ---------------------------------------------------------------------------

_GRP_LONN          = "Lønnskostnad"
_GRP_FERIE_KOST    = "Feriepenger"
_GRP_AGA_KOST      = "Kostnadsført arbeidsgiveravgift"
_GRP_AGA_FERIE     = "Kostnadsført arbeidsgiveravgift av feriepenger"
_GRP_PENSJON_KOST  = "Pensjonskostnad"

_GRP_SKYLDIG_LONN   = "Skyldig lønn"
_GRP_SKYLDIG_FERIE  = "Skyldig feriepenger"
_GRP_SKYLDIG_AGA    = "Skyldig arbeidsgiveravgift"
_GRP_SKYLDIG_AGA_FP = "Skyldig arbeidsgiveravgift av feriepenger"
_GRP_SKYLDIG_PENSJON= "Skyldig pensjon"

_FERIE_SATS   = 0.102   # standard 10,2 %
_FERIE_SATS_5 = 0.125   # 60+ år, 5 uker: 12,5 %
_AGA_SATS     = 0.141   # sone I: 14,1 %

_RESULT_GROUPS = [
    _GRP_LONN,
    _GRP_FERIE_KOST,
    _GRP_AGA_KOST,
    _GRP_AGA_FERIE,
    _GRP_PENSJON_KOST,
]
_BALANCE_GROUPS = [
    _GRP_SKYLDIG_LONN,
    _GRP_SKYLDIG_FERIE,
    _GRP_SKYLDIG_AGA,
    _GRP_SKYLDIG_AGA_FP,
    _GRP_SKYLDIG_PENSJON,
]

_TAG_HEADER  = "header"
_TAG_RECON   = "recon"
_TAG_OK      = "ok"
_TAG_AVVIK   = "avvik"
_TAG_INFO    = "info"


# ---------------------------------------------------------------------------
# Hjelpefunksjoner
# ---------------------------------------------------------------------------

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


def _sum_for_group(sb_df: Any, gruppe_mapping: dict[str, str],
                   gruppe: str, col_map: dict[str, str]) -> tuple[float, float, float]:
    import pandas as pd
    kontoer = {k for k, v in gruppe_mapping.items() if v == gruppe}
    if not kontoer:
        return 0.0, 0.0, 0.0
    konto_src = col_map.get("konto", "")
    if not konto_src:
        return 0.0, 0.0, 0.0
    mask = sb_df[konto_src].astype(str).isin(kontoer)
    sub = sb_df[mask]

    def _s(key: str) -> float:
        col = col_map.get(key, "")
        if not col or col not in sub.columns:
            return 0.0
        return float(pd.to_numeric(sub[col], errors="coerce").fillna(0.0).sum())
    return _s("ib"), _s("endring"), _s("ub")


# ---------------------------------------------------------------------------
# Hoved-side
# ---------------------------------------------------------------------------

class LonnPage(ttk.Frame):  # type: ignore[misc]

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

    def set_analyse_page(self, page: Any) -> None:
        self._analyse_page = page

    def refresh_from_session(self, session: Any = None) -> None:
        self._load_data()
        self._refresh_all()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        tb = ttk.Frame(self, padding=(6, 4))
        tb.grid(row=0, column=0, sticky="ew")

        ttk.Label(tb, text="Lønnsanalyse",
                  font=("TkDefaultFont", 11, "bold")).pack(side="left", padx=(0, 12))
        ttk.Button(tb, text="Oppdater", command=self._refresh_all,
                   width=10).pack(side="left")
        ttk.Button(tb, text="Eksporter til Excel\u2026",
                   command=self._export_excel).pack(side="left", padx=(6, 0))
        self._status_lbl = ttk.Label(tb, text="", foreground="#555")
        self._status_lbl.pack(side="left", padx=(12, 0))
        ttk.Label(
            tb,
            text="Klassifiser kontoer i Analyse-fanen for å aktivere lønnsanalyse.",
            foreground="#888",
        ).pack(side="right", padx=(0, 8))

        pane = ttk.PanedWindow(self, orient="vertical")
        pane.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))

        # Resultatregnskap-del
        top = ttk.LabelFrame(pane, text="Resultatkostnader", padding=(4, 4))
        top.columnconfigure(0, weight=1)
        top.rowconfigure(0, weight=1)
        pane.add(top, weight=2)
        self._rs_tree = self._make_tree(top)
        self._rs_tree.grid(row=0, column=0, sticky="nsew")
        vsb1 = ttk.Scrollbar(top, orient="vertical", command=self._rs_tree.yview)
        vsb1.grid(row=0, column=1, sticky="ns")
        self._rs_tree.configure(yscrollcommand=vsb1.set)

        # Balanse-del
        mid = ttk.LabelFrame(pane, text="Balansekontoer (skyldige beløp)", padding=(4, 4))
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(0, weight=1)
        pane.add(mid, weight=2)
        self._bs_tree = self._make_tree(mid)
        self._bs_tree.grid(row=0, column=0, sticky="nsew")
        vsb2 = ttk.Scrollbar(mid, orient="vertical", command=self._bs_tree.yview)
        vsb2.grid(row=0, column=1, sticky="ns")
        self._bs_tree.configure(yscrollcommand=vsb2.set)

        # Kontoer-drill
        bot = ttk.LabelFrame(pane, text="Kontoer i valgt gruppe", padding=(4, 4))
        bot.columnconfigure(0, weight=1)
        bot.rowconfigure(0, weight=1)
        pane.add(bot, weight=3)
        self._konto_tree = self._make_konto_tree(bot)
        self._konto_tree.grid(row=0, column=0, sticky="nsew")
        vsb3 = ttk.Scrollbar(bot, orient="vertical", command=self._konto_tree.yview)
        vsb3.grid(row=0, column=1, sticky="ns")
        self._konto_tree.configure(yscrollcommand=vsb3.set)
        self._konto_frame = bot

        self._rs_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._bs_tree.bind("<<TreeviewSelect>>", self._on_tree_select)

    def _make_tree(self, parent: Any) -> Any:
        cols = ("gruppe", "ib", "bevegelse", "ub")
        tree = ttk.Treeview(parent, columns=cols, show="headings",
                             selectmode="browse", height=8)
        tree.heading("gruppe",    text="Post",      anchor="w")
        tree.heading("ib",        text="IB",        anchor="e")
        tree.heading("bevegelse", text="Bevegelse",  anchor="e")
        tree.heading("ub",        text="UB",        anchor="e")
        tree.column("gruppe",    width=280, anchor="w", stretch=True)
        tree.column("ib",        width=140, anchor="e", stretch=False)
        tree.column("bevegelse", width=140, anchor="e", stretch=False)
        tree.column("ub",        width=140, anchor="e", stretch=False)
        tree.tag_configure(_TAG_HEADER, background="#E8EFF7",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure(_TAG_RECON,  background="#F5F5F5",
                           font=("TkDefaultFont", 9, "italic"))
        tree.tag_configure(_TAG_OK,     foreground="#1B7F35",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure(_TAG_AVVIK,  foreground="#C0392B",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure(_TAG_INFO,   foreground="#555555",
                           font=("TkDefaultFont", 9, "italic"))
        return tree

    def _make_konto_tree(self, parent: Any) -> Any:
        cols = ("konto", "kontonavn", "ib", "bevegelse", "ub")
        tree = ttk.Treeview(parent, columns=cols, show="headings",
                             selectmode="browse")
        tree.heading("konto",     text="Konto",     anchor="w")
        tree.heading("kontonavn", text="Kontonavn", anchor="w")
        tree.heading("ib",        text="IB",        anchor="e")
        tree.heading("bevegelse", text="Bevegelse", anchor="e")
        tree.heading("ub",        text="UB",        anchor="e")
        tree.column("konto",     width=80,  anchor="w", stretch=False)
        tree.column("kontonavn", width=280, anchor="w", stretch=True)
        tree.column("ib",        width=130, anchor="e", stretch=False)
        tree.column("bevegelse", width=130, anchor="e", stretch=False)
        tree.column("ub",        width=130, anchor="e", stretch=False)
        tree.tag_configure("neg", foreground="red")
        tree.tag_configure(_TAG_HEADER, background="#E8EFF7",
                           font=("TkDefaultFont", 9, "bold"))
        return tree

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _export_excel(self) -> None:
        try:
            import session as _session
            import analyse_export_excel as _xls
            client = getattr(_session, "client", None) or ""
            year   = str(getattr(_session, "year", "") or "")
            path = _xls.open_save_dialog(
                title="Eksporter Lønnsanalyse",
                default_filename=f"lønnsanalyse_{client}_{year}.xlsx".strip("_"),
                master=self,
            )
            if not path:
                return
            rs_sheet = _xls.treeview_to_sheet(
                self._rs_tree,
                title="Resultatkostnader",
                heading="Lønnsanalyse — Resultatkostnader",
                bold_tags=(_TAG_HEADER, _TAG_OK, _TAG_AVVIK),
                bg_tags={_TAG_HEADER: "BDD7EE", _TAG_OK: "E8F5E9", _TAG_AVVIK: "FFEBEE"},
            )
            bs_sheet = _xls.treeview_to_sheet(
                self._bs_tree,
                title="Balansekontoer",
                heading="Lønnsanalyse — Skyldige beløp",
                bold_tags=(_TAG_HEADER,),
                bg_tags={_TAG_HEADER: "BDD7EE"},
            )
            konto_sheet = _xls.treeview_to_sheet(
                self._konto_tree,
                title="Kontoer",
                heading=f"Kontoer: {self._selected_gruppe}" if self._selected_gruppe
                        else "Kontoer",
                bold_tags=(_TAG_HEADER,),
                bg_tags={_TAG_HEADER: "BDD7EE"},
            )
            _xls.export_and_open(path, [rs_sheet, bs_sheet, konto_sheet],
                                  title="Lønnsanalyse", client=client, year=year)
        except Exception as e:
            log.exception("Lønn Excel-eksport feilet: %s", e)

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
        try:
            sb_df = page._get_effective_sb_df()
        except Exception:
            pass
        self._sb_df = sb_df
        self._col_map = _resolve_sb_columns(sb_df)
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
        self._populate_rs_tree()
        self._populate_bs_tree()
        self._populate_kontoer(self._selected_gruppe)
        self._update_status()

    def _update_status(self) -> None:
        if not self._gruppe_mapping:
            self._status_lbl.configure(
                text="Ingen kontoer klassifisert. Bruk 'Klassifiser kontoer' i Analyse-fanen."
            )
            return
        lonn_ub = _sum_for_group(self._sb_df, self._gruppe_mapping,
                                  _GRP_LONN, self._col_map)[2] if self._sb_df is not None else 0.0
        self._status_lbl.configure(
            text=f"Lønnskostnad UB: {formatting.fmt_amount(lonn_ub)}"
        )

    def _populate_rs_tree(self) -> None:
        tree = self._rs_tree
        tree.delete(*tree.get_children())

        if self._sb_df is None or not self._gruppe_mapping:
            tree.insert("", "end", values=("Ingen klassifiserte kontoer.", "", "", ""),
                        tags=(_TAG_INFO,))
            return

        # Samle tilgjengelige RS-grupper
        import konto_klassifisering as _kk
        all_grps = set(_kk.all_groups_in_use(self._gruppe_mapping))
        rs_grps = [g for g in _RESULT_GROUPS if g in all_grps]
        extra_rs = [g for g in all_grps
                    if g not in _RESULT_GROUPS and g not in _BALANCE_GROUPS
                    and any(w in g.lower() for w in ("lønn", "lønns", "ferie", "aga",
                                                      "pensjon", "arbeidsgiver"))]
        rs_grps += extra_rs

        tree.insert("", "end", values=("Personalkostnader", "", "", ""),
                    tags=(_TAG_HEADER,))

        totals: dict[str, tuple[float, float, float]] = {}
        for g in rs_grps:
            ib, bev, ub = _sum_for_group(self._sb_df, self._gruppe_mapping,
                                          g, self._col_map)
            totals[g] = (ib, bev, ub)
            tree.insert("", "end", iid=f"_grp_{g}",
                        values=(f"  {g}",
                                formatting.fmt_amount(ib),
                                formatting.fmt_amount(bev),
                                formatting.fmt_amount(ub)),
                        tags=())

        # Totalsum
        if totals:
            t_ib  = sum(v[0] for v in totals.values())
            t_bev = sum(v[1] for v in totals.values())
            t_ub  = sum(v[2] for v in totals.values())
            tree.insert("", "end", values=(
                "  Σ Totale personalkostnader",
                formatting.fmt_amount(t_ib),
                formatting.fmt_amount(t_bev),
                formatting.fmt_amount(t_ub),
            ), tags=(_TAG_HEADER,))

        # Kontrollberegninger
        self._insert_rs_controls(tree, totals)

    def _insert_rs_controls(self, tree: Any,
                              totals: dict[str, tuple[float, float, float]]) -> None:
        """Sett inn kontrollberegninger (feriepenger, AGA)."""

        def _bev(g: str) -> float:
            return totals.get(g, (0.0, 0.0, 0.0))[1]

        lonn_bev  = _bev(_GRP_LONN)
        ferie_bev = _bev(_GRP_FERIE_KOST)
        aga_bev   = _bev(_GRP_AGA_KOST)

        tree.insert("", "end", values=("Kontrollberegninger", "", "", ""),
                    tags=(_TAG_HEADER,))

        # Feriepenger: lønnsgrunnlag × 10,2 %
        if lonn_bev:
            forventet_ferie = abs(lonn_bev) * _FERIE_SATS
            avvik_ferie = abs(ferie_bev) - forventet_ferie
            ok_ferie = abs(avvik_ferie) < max(500.0, abs(lonn_bev) * 0.02)
            tag = _TAG_OK if ok_ferie else _TAG_AVVIK
            tree.insert("", "end", values=(
                f"  Feriepenger (forventet {_FERIE_SATS*100:.1f}% av lønn)",
                "", "",
                formatting.fmt_amount(forventet_ferie),
            ), tags=(_TAG_INFO,))
            diff_txt = "✓" if ok_ferie else f"⚠ avvik {formatting.fmt_amount(avvik_ferie)}"
            tree.insert("", "end", values=(
                f"    → Bokført {diff_txt}",
                "", "",
                formatting.fmt_amount(abs(ferie_bev)),
            ), tags=(tag,))

        # AGA: (lønn + feriepenger) × 14,1 %
        if lonn_bev or ferie_bev:
            grunnlag_aga = abs(lonn_bev) + abs(ferie_bev)
            forventet_aga = grunnlag_aga * _AGA_SATS
            avvik_aga = abs(aga_bev) - forventet_aga
            ok_aga = abs(avvik_aga) < max(500.0, grunnlag_aga * 0.02)
            tag_aga = _TAG_OK if ok_aga else _TAG_AVVIK
            tree.insert("", "end", values=(
                f"  AGA (forventet {_AGA_SATS*100:.1f}% av lønn + feriepenger)",
                "", "",
                formatting.fmt_amount(forventet_aga),
            ), tags=(_TAG_INFO,))
            diff_txt = "✓" if ok_aga else f"⚠ avvik {formatting.fmt_amount(avvik_aga)}"
            tree.insert("", "end", values=(
                f"    → Bokført {diff_txt}",
                "", "",
                formatting.fmt_amount(abs(aga_bev)),
            ), tags=(tag_aga,))

    def _populate_bs_tree(self) -> None:
        tree = self._bs_tree
        tree.delete(*tree.get_children())

        if self._sb_df is None or not self._gruppe_mapping:
            return

        import konto_klassifisering as _kk
        all_grps = set(_kk.all_groups_in_use(self._gruppe_mapping))
        bs_grps = [g for g in _BALANCE_GROUPS if g in all_grps]
        extra_bs = [g for g in all_grps
                    if g not in _RESULT_GROUPS and g not in _BALANCE_GROUPS
                    and "skyldig" in g.lower()]
        bs_grps += extra_bs

        if not bs_grps:
            tree.insert("", "end", values=("Ingen skyldige lønnsposter klassifisert.", "", "", ""),
                        tags=(_TAG_INFO,))
            return

        tree.insert("", "end", values=("Skyldige beløp", "", "", ""),
                    tags=(_TAG_HEADER,))

        for g in bs_grps:
            ib, bev, ub = _sum_for_group(self._sb_df, self._gruppe_mapping,
                                          g, self._col_map)
            tree.insert("", "end", iid=f"_grp_{g}",
                        values=(f"  {g}",
                                formatting.fmt_amount(ib),
                                formatting.fmt_amount(bev),
                                formatting.fmt_amount(ub)),
                        tags=())

    # ------------------------------------------------------------------
    # Konto-drill
    # ------------------------------------------------------------------

    def _on_tree_select(self, event: Any = None) -> None:
        # Finn hvilken tree som sendte event
        source_tree = None
        for t in (self._rs_tree, self._bs_tree):
            if t.selection():
                source_tree = t
                break
        if source_tree is None:
            return

        sel = source_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if not iid.startswith("_grp_"):
            return
        gruppe = iid[len("_grp_"):]
        self._selected_gruppe = gruppe
        self._populate_kontoer(gruppe)
        try:
            self._konto_frame.configure(text=f"Kontoer: {gruppe}")
        except Exception:
            pass

        # Nullstill valg i den andre treet
        other = self._bs_tree if source_tree is self._rs_tree else self._rs_tree
        try:
            other.selection_remove(other.selection())
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
        konto_src = self._col_map.get("konto", "")
        if not konto_src or not kontoer_i_gruppe:
            return

        mask = self._sb_df[konto_src].astype(str).isin(kontoer_i_gruppe)
        sub = self._sb_df[mask].copy()
        try:
            sub = sub.sort_values(konto_src,
                                  key=lambda s: pd.to_numeric(s, errors="coerce"))
        except Exception:
            pass

        navn_col = self._col_map.get("kontonavn", "")
        ib_col   = self._col_map.get("ib", "")
        endr_col = self._col_map.get("endring", "")
        ub_col   = self._col_map.get("ub", "")
        cols = list(sub.columns)

        sum_ib = sum_bev = sum_ub = 0.0

        for tup in sub.itertuples(index=False):
            def _get(col: str, d: Any = "") -> Any:
                if not col or col not in cols:
                    return d
                return tup[cols.index(col)]

            konto = str(_get(konto_src, "")).strip()
            navn  = str(_get(navn_col, "")).strip()
            ib    = float(pd.to_numeric(_get(ib_col,   0), errors="coerce") or 0)
            bev   = float(pd.to_numeric(_get(endr_col, 0), errors="coerce") or 0)
            ub    = float(pd.to_numeric(_get(ub_col,   0), errors="coerce") or 0)
            sum_ib += ib; sum_bev += bev; sum_ub += ub

            tags = ("neg",) if ub < 0 else ()
            tree.insert("", "end", values=(
                konto, navn,
                formatting.fmt_amount(ib),
                formatting.fmt_amount(bev),
                formatting.fmt_amount(ub),
            ), tags=tags)

        tree.insert("", "end", values=(
            "Σ", f"{len(sub)} kontoer",
            formatting.fmt_amount(sum_ib),
            formatting.fmt_amount(sum_bev),
            formatting.fmt_amount(sum_ub),
        ), tags=(_TAG_HEADER,))
