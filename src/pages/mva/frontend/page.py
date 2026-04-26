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

from src.shared.columns_vocabulary import active_year_from_session, heading

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


def _to_int_or_default(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


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
        # Sett initial labels — overskrives ved refresh_from_session.
        self._apply_vocabulary_labels()

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def set_analyse_page(self, page: Any) -> None:
        self._analyse_page = page

    def refresh_from_session(self, session: Any = None) -> None:
        self._load_data()
        self._apply_vocabulary_labels()
        self._refresh_all()

    def _apply_vocabulary_labels(self) -> None:
        """Oppdater saldo-headings ('IB', 'Bevegelse', 'UB') med aktivt år
        fra felles kolonne-vokabular. Kall etter session-oppdatering."""
        yr = active_year_from_session()
        ib_label = heading("IB", year=yr)
        bev_label = heading("Endring", year=yr)   # periode-bevegelse
        ub_label = heading("UB", year=yr)
        for tree in (
            getattr(self, "_summary_tree", None),
            getattr(self, "_konto_tree", None),
        ):
            if tree is None:
                continue
            try:
                tree.heading("ib",        text=ib_label,  anchor="e")
                tree.heading("bevegelse", text=bev_label, anchor="e")
                tree.heading("ub",        text=ub_label,  anchor="e")
            except Exception:
                pass

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
        ttk.Button(tb, text="MVA-oppsett\u2026",
                   command=self._open_mva_config).pack(side="left", padx=(6, 0))
        ttk.Button(tb, text="Importer Skatteetaten\u2026",
                   command=self._import_skatteetaten).pack(side="left", padx=(6, 0))
        ttk.Button(tb, text="Importer MVA-melding\u2026",
                   command=self._import_mva_melding).pack(side="left", padx=(6, 0))
        ttk.Button(tb, text="Eksporter til Excel\u2026",
                   command=self._export_excel).pack(side="left", padx=(6, 0))
        self._status_lbl = ttk.Label(tb, text="", foreground="#555")
        self._status_lbl.pack(side="left", padx=(12, 0))

        ttk.Label(
            tb,
            text="Klassifiser kontoer i Analyse-fanen for å aktivere MVA-analyse.",
            foreground="#888",
        ).pack(side="right", padx=(0, 8))

        # Hoved-notebook med 5 sub-faner
        nb = ttk.Notebook(self)
        nb.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self._notebook = nb

        # --- Sub-fane 1: Sammendrag ---
        tab_sum = ttk.Frame(nb)
        tab_sum.columnconfigure(0, weight=1)
        tab_sum.rowconfigure(0, weight=1)
        nb.add(tab_sum, text="Sammendrag")
        self._tab_sammendrag = tab_sum
        self._build_tab_sammendrag(tab_sum)

        # --- Sub-fane 2: Per kode/termin ---
        tab_kt = ttk.Frame(nb)
        tab_kt.columnconfigure(0, weight=1)
        tab_kt.rowconfigure(0, weight=1)
        nb.add(tab_kt, text="Per kode/termin")
        self._tab_kode_termin = tab_kt
        self._build_tab_kode_termin(tab_kt)

        # --- Sub-fane 3: Avstemming HB ---
        tab_av = ttk.Frame(nb)
        tab_av.columnconfigure(0, weight=1)
        tab_av.rowconfigure(0, weight=1)
        nb.add(tab_av, text="Avstemming HB")
        self._tab_avstemming = tab_av
        self._build_tab_avstemming(tab_av)

        # --- Sub-fane 4: Kontroller ---
        tab_ko = ttk.Frame(nb)
        tab_ko.columnconfigure(0, weight=1)
        tab_ko.rowconfigure(0, weight=1)
        nb.add(tab_ko, text="Kontroller")
        self._tab_kontroller = tab_ko
        self._build_tab_kontroller(tab_ko)

        # --- Sub-fane 5: Skyldig saldo ---
        tab_sk = ttk.Frame(nb)
        tab_sk.columnconfigure(0, weight=1)
        tab_sk.rowconfigure(0, weight=1)
        nb.add(tab_sk, text="Skyldig saldo")
        self._tab_skyldig = tab_sk
        self._build_tab_skyldig(tab_sk)

        # Lazy refresh: bygg faneinnhold når den først blir synlig
        self._loaded_tabs: set[int] = {0}  # Sammendrag bygges via _refresh_all
        nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    # ------------------------------------------------------------------
    # Sub-fane 1: Sammendrag
    # ------------------------------------------------------------------

    def _build_tab_sammendrag(self, parent: Any) -> None:
        pane = ttk.PanedWindow(parent, orient="vertical")
        pane.grid(row=0, column=0, sticky="nsew")

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

    # ------------------------------------------------------------------
    # Sub-fane 2-5: placeholders — bygges i senere steg
    # ------------------------------------------------------------------

    def _build_tab_kode_termin(self, parent: Any) -> None:
        """Sub-fane 2: MVA-kode-pivot T1-T6 (gjenbruker build_mva_pivot)."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        header = ttk.Frame(parent, padding=(4, 4))
        header.grid(row=0, column=0, sticky="ew")

        ttk.Label(
            header,
            text="MVA-kode per termin (T1–T6)",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(side="left")

        self._var_show_grunnlag = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            header,
            text="Vis grunnlag (beløp eks. MVA)",
            variable=self._var_show_grunnlag,
            command=self._refresh_tab_kode_termin,
        ).pack(side="left", padx=(12, 0))

        self._kt_info_lbl = ttk.Label(header, text="", foreground="#666")
        self._kt_info_lbl.pack(side="right")

        body = ttk.Frame(parent, padding=(4, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        body.grid(row=1, column=0, sticky="nsew")

        cols = ("kode", "beskrivelse", "t1", "t2", "t3", "t4", "t5", "t6", "sum")
        tree = ttk.Treeview(body, columns=cols, show="headings",
                            selectmode="browse")
        headings = [
            ("kode", "MVA-kode", 80, "center"),
            ("beskrivelse", "Beskrivelse", 260, "w"),
            ("t1", "T1", 110, "e"),
            ("t2", "T2", 110, "e"),
            ("t3", "T3", 110, "e"),
            ("t4", "T4", 110, "e"),
            ("t5", "T5", 110, "e"),
            ("t6", "T6", 110, "e"),
            ("sum", "Sum", 130, "e"),
        ]
        for col_id, label, width, anchor in headings:
            tree.heading(col_id, text=label, anchor=anchor)
            tree.column(col_id, width=width, anchor=anchor,
                        stretch=(col_id == "beskrivelse"))
        tree.tag_configure("sumline", background="#F0F0F0",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure("sumline_major", background="#D9E6F5",
                           font=("TkDefaultFont", 9, "bold"))
        tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=vsb.set)

        self._kode_termin_tree = tree

    def _refresh_tab_kode_termin(self) -> None:
        """Bygg MVA-pivot via build_mva_pivot og fyll treet."""
        tree = getattr(self, "_kode_termin_tree", None)
        if tree is None:
            return
        try:
            tree.delete(*tree.get_children())
        except Exception:
            pass

        page = self._analyse_page
        if page is None:
            self._kt_info_lbl.configure(
                text="Åpne Analyse-fanen for å laste hovedboken."
            )
            return

        import pandas as pd
        df_filtered = getattr(page, "_df_filtered", None)
        if df_filtered is None or not isinstance(df_filtered, pd.DataFrame) or df_filtered.empty:
            self._kt_info_lbl.configure(text="Ingen filtrerte transaksjoner.")
            return

        from page_analyse_mva import build_mva_pivot

        client = ""
        try:
            import session as _session
            client = str(getattr(_session, "client", None) or "").strip()
        except Exception:
            pass

        try:
            pivot_df = build_mva_pivot(df_filtered, client=client or None)
        except Exception:
            log.exception("build_mva_pivot feilet i MVA-fanen")
            self._kt_info_lbl.configure(text="Kunne ikke bygge pivot.")
            return

        if pivot_df is None or pivot_df.empty:
            self._kt_info_lbl.configure(
                text="Ingen transaksjoner med MVA-kode funnet."
            )
            return

        show_grunnlag = bool(self._var_show_grunnlag.get())
        value_prefix = "G_" if show_grunnlag else ""
        sum_key = "G_Sum" if show_grunnlag else "Sum"

        n_codes = 0
        for _, row in pivot_df.iterrows():
            direction = str(row.get("direction", ""))
            code = str(row.get("MVA-kode", ""))
            desc = str(row.get("Beskrivelse", ""))

            def _fmt(val: Any) -> str:
                try:
                    fv = float(val)
                except Exception:
                    return ""
                if fv == 0:
                    return ""
                return formatting.fmt_amount(fv)

            vals = [code, desc]
            for t in range(1, 7):
                vals.append(_fmt(row.get(f"{value_prefix}T{t}", 0.0)))
            vals.append(_fmt(row.get(sum_key, 0.0)))

            tags: tuple = ()
            if direction == "_summary":
                tags = ("sumline",)
            elif direction == "_netto":
                tags = ("sumline_major",)
            else:
                n_codes += 1

            try:
                tree.insert("", "end", values=vals, tags=tags)
            except Exception:
                continue

        mode_txt = "grunnlag" if show_grunnlag else "avgift"
        self._kt_info_lbl.configure(
            text=f"{n_codes} MVA-koder · visning: {mode_txt}"
        )

    def _build_tab_avstemming(self, parent: Any) -> None:
        """Sub-fane 3: HB vs MVA-melding vs Skatteetaten per termin."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        header = ttk.Frame(parent, padding=(4, 4))
        header.grid(row=0, column=0, sticky="ew")

        self._av_status_hb = ttk.Label(header, text="HB: —", foreground="#555")
        self._av_status_hb.pack(side="left", padx=(0, 12))
        self._av_status_melding = ttk.Label(
            header, text="MVA-melding: —", foreground="#555",
        )
        self._av_status_melding.pack(side="left", padx=(0, 12))
        self._av_status_skatt = ttk.Label(
            header, text="Skatteetaten: —", foreground="#555",
        )
        self._av_status_skatt.pack(side="left", padx=(0, 12))

        body = ttk.Frame(parent, padding=(4, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        body.grid(row=1, column=0, sticky="nsew")

        cols = (
            "termin", "hb_utg", "hb_inn", "hb_netto",
            "melding", "skatt",
            "avvik_hb_melding", "avvik_melding_skatt",
        )
        tree = ttk.Treeview(body, columns=cols, show="headings",
                            selectmode="browse")
        headings = [
            ("termin", "Termin", 60, "center"),
            ("hb_utg", "HB Utgående", 120, "e"),
            ("hb_inn", "HB Inngående", 120, "e"),
            ("hb_netto", "HB Netto", 120, "e"),
            ("melding", "MVA-melding", 120, "e"),
            ("skatt", "Skatteetaten", 120, "e"),
            ("avvik_hb_melding", "Avvik HB↔Melding", 140, "e"),
            ("avvik_melding_skatt", "Avvik Melding↔Skatt", 140, "e"),
        ]
        for col_id, label, width, anchor in headings:
            tree.heading(col_id, text=label, anchor=anchor)
            tree.column(col_id, width=width, anchor=anchor, stretch=False)

        tree.tag_configure("sumline", background="#F0F0F0",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure("avvik", foreground="#C0392B",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure("ok", foreground="#1B7F35")
        tree.tag_configure("mangler", foreground="#888")

        tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=vsb.set)

        self._avstemming_tree = tree

    def _refresh_tab_avstemming(self) -> None:
        """Bygg 3-veis avstemming: HB / MVA-melding / Skatteetaten."""
        tree = getattr(self, "_avstemming_tree", None)
        if tree is None:
            return
        try:
            tree.delete(*tree.get_children())
        except Exception:
            pass

        client, year = self._get_session_client_year()

        # --- HB-verdier (per termin, netto) ---
        hb_utg = {t: 0.0 for t in range(1, 7)}
        hb_inn = {t: 0.0 for t in range(1, 7)}
        hb_status = "—"

        page = self._analyse_page
        import pandas as pd
        df_filtered = getattr(page, "_df_filtered", None) if page is not None else None
        if isinstance(df_filtered, pd.DataFrame) and not df_filtered.empty:
            from page_analyse_mva import build_mva_pivot
            try:
                pivot = build_mva_pivot(df_filtered, client=client or None)
                if not pivot.empty and "direction" in pivot.columns:
                    for t in range(1, 7):
                        t_col = f"T{t}"
                        if t_col in pivot.columns:
                            hb_utg[t] = abs(float(
                                pivot.loc[pivot["direction"] == "utgående", t_col].sum()
                            ))
                            hb_inn[t] = abs(float(
                                pivot.loc[pivot["direction"] == "inngående", t_col].sum()
                            ))
                hb_status = "HB: lastet fra Analyse"
            except Exception:
                log.exception("Kunne ikke bygge HB-pivot for avstemming")
                hb_status = "HB: feil ved pivotbygging"
        else:
            hb_status = "HB: ingen data i Analyse-fanen"

        # --- MVA-melding per termin ---
        melding = {t: None for t in range(1, 7)}
        mld_count = 0
        try:
            import src.shared.regnskap.client_overrides as rco
            if client and year:
                bucket = rco.load_mva_melding(client, year, termin=None) or {}
                for termin_str, data in bucket.items():
                    try:
                        termin_int = int(termin_str)
                    except (TypeError, ValueError):
                        continue
                    if termin_int not in melding:
                        continue
                    try:
                        from ..backend.melding_parser import MvaMeldingData
                        md = MvaMeldingData.from_dict(data)
                        melding[termin_int] = md.sum_utgaaende() - md.sum_inngaaende()
                        mld_count += 1
                    except Exception:
                        continue
        except Exception:
            log.debug("Kunne ikke laste MVA-melding", exc_info=True)

        # --- Skatteetaten per termin ---
        skatt = {t: None for t in range(1, 7)}
        skatt_count = 0
        try:
            import src.shared.regnskap.client_overrides as rco
            from ..backend.avstemming import SkatteetatenData
            if client and year:
                data = rco.load_skatteetaten_data(client, year)
                if data:
                    sd = SkatteetatenData.from_dict(data)
                    for t, v in sd.mva_per_termin.items():
                        if 1 <= int(t) <= 6:
                            skatt[int(t)] = float(v)
                            skatt_count += 1
        except Exception:
            log.debug("Kunne ikke laste Skatteetaten-data", exc_info=True)

        self._av_status_hb.configure(text=hb_status)
        if mld_count == 0:
            mld_text = (
                f"MVA-melding: ikke importert ({year or '—'}) — bruk "
                "«Importer MVA-melding…» i toolbaren"
            )
        else:
            mld_text = f"MVA-melding: {mld_count} terminer lastet ({year or '—'})"
        self._av_status_melding.configure(text=mld_text)
        if skatt_count == 0:
            skatt_text = (
                f"Skatteetaten: ikke importert ({year or '—'}) — bruk "
                "«Importer Skatteetaten…» i toolbaren"
            )
        else:
            skatt_text = (
                f"Skatteetaten: {skatt_count} terminer lastet ({year or '—'})"
            )
        self._av_status_skatt.configure(text=skatt_text)

        def _fmt(val: Any) -> str:
            if val is None:
                return "—"
            try:
                return formatting.fmt_amount(float(val))
            except Exception:
                return "—"

        def _avvik_tag(a: Any, b: Any) -> str:
            if a is None or b is None:
                return "mangler"
            try:
                diff = float(a) - float(b)
            except Exception:
                return "mangler"
            return "ok" if abs(diff) <= 1.0 else "avvik"

        # Data-rader per termin
        for t in range(1, 7):
            netto = hb_utg[t] - hb_inn[t]
            mld = melding[t]
            sk = skatt[t]
            diff_hm = None if mld is None else netto - mld
            diff_ms = None if (mld is None or sk is None) else mld - sk

            row_tag = ()
            # Fremhev primæravviket (HB vs melding) hvis finnes
            if mld is not None:
                row_tag = (_avvik_tag(netto, mld),)
            elif sk is not None:
                row_tag = (_avvik_tag(netto, sk),)

            vals = (
                f"T{t}",
                formatting.fmt_amount(hb_utg[t]),
                formatting.fmt_amount(hb_inn[t]),
                formatting.fmt_amount(netto),
                _fmt(mld),
                _fmt(sk),
                _fmt(diff_hm),
                _fmt(diff_ms),
            )
            try:
                tree.insert("", "end", values=vals, tags=row_tag)
            except Exception:
                pass

        # Sum-rad
        sum_hb_utg = sum(hb_utg.values())
        sum_hb_inn = sum(hb_inn.values())
        sum_netto = sum_hb_utg - sum_hb_inn
        sum_mld = sum((v for v in melding.values() if v is not None), 0.0) \
            if mld_count else None
        sum_sk = sum((v for v in skatt.values() if v is not None), 0.0) \
            if skatt_count else None
        diff_hm = None if sum_mld is None else sum_netto - sum_mld
        diff_ms = None if (sum_mld is None or sum_sk is None) else sum_mld - sum_sk

        try:
            tree.insert("", "end", values=(
                "Sum",
                formatting.fmt_amount(sum_hb_utg),
                formatting.fmt_amount(sum_hb_inn),
                formatting.fmt_amount(sum_netto),
                _fmt(sum_mld),
                _fmt(sum_sk),
                _fmt(diff_hm),
                _fmt(diff_ms),
            ), tags=("sumline",))
        except Exception:
            pass

    def _get_session_client_year(self) -> tuple[str, str]:
        try:
            import session as _session
            return (
                str(getattr(_session, "client", None) or "").strip(),
                str(getattr(_session, "year", None) or "").strip(),
            )
        except Exception:
            return ("", "")

    def _build_tab_kontroller(self, parent: Any) -> None:
        """Sub-fane 4: K1–K6 MVA-kontroller."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        header = ttk.Frame(parent, padding=(4, 4))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            header, text="MVA-kontroller (K1–K6)",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(side="left")
        self._kontroll_info = ttk.Label(header, text="", foreground="#555")
        self._kontroll_info.pack(side="right")

        body = ttk.Frame(parent, padding=(4, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        body.grid(row=1, column=0, sticky="nsew")

        cols = ("id", "label", "status", "treff", "belop", "kommentar")
        tree = ttk.Treeview(body, columns=cols, show="headings",
                            selectmode="browse")
        headings = [
            ("id", "Kontroll", 60, "center"),
            ("label", "Beskrivelse", 260, "w"),
            ("status", "Status", 90, "center"),
            ("treff", "Treff", 70, "e"),
            ("belop", "Beløp", 120, "e"),
            ("kommentar", "Kommentar", 500, "w"),
        ]
        for col_id, label, width, anchor in headings:
            tree.heading(col_id, text=label, anchor=anchor)
            tree.column(col_id, width=width, anchor=anchor,
                        stretch=(col_id == "kommentar"))
        tree.tag_configure("ok", foreground="#1B7F35")
        tree.tag_configure("avvik", foreground="#C0392B",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure("merk", foreground="#B38600")
        tree.tag_configure("mangler", foreground="#888")
        tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=vsb.set)

        self._kontroll_tree = tree
        self._kontroll_results: list[Any] = []
        tree.bind("<Double-1>", self._on_kontroll_double)

    def _refresh_tab_kontroller(self) -> None:
        tree = getattr(self, "_kontroll_tree", None)
        if tree is None:
            return
        try:
            tree.delete(*tree.get_children())
        except Exception:
            pass

        page = self._analyse_page
        import pandas as pd
        df_filtered = getattr(page, "_df_filtered", None) if page is not None else None
        if df_filtered is None or not isinstance(df_filtered, pd.DataFrame) or df_filtered.empty:
            self._kontroll_info.configure(text="Ingen transaksjoner å kontrollere.")
            self._kontroll_results = []
            return

        client, year = self._get_session_client_year()
        skatt = None
        try:
            import src.shared.regnskap.client_overrides as rco
            from ..backend.avstemming import SkatteetatenData
            if client and year:
                raw = rco.load_skatteetaten_data(client, year)
                if raw:
                    skatt = SkatteetatenData.from_dict(raw)
        except Exception:
            log.debug("Kunne ikke laste Skatteetaten for K5", exc_info=True)

        try:
            from ..backend.kontroller import run_all_controls
            result = run_all_controls(
                df_filtered,
                skatteetaten=skatt,
                gruppe_mapping=self._gruppe_mapping,
            )
        except Exception:
            log.exception("Kjøring av MVA-kontroller feilet")
            self._kontroll_info.configure(text="Kunne ikke kjøre kontroller.")
            self._kontroll_results = []
            return

        self._kontroll_results = result.results
        n_avvik = sum(1 for r in result.results if r.status == "AVVIK")
        n_merk = sum(1 for r in result.results if r.status == "MERK")
        self._kontroll_info.configure(
            text=f"{len(result.results)} kontroller · {n_avvik} avvik · {n_merk} merknader"
        )

        for r in result.results:
            status = (r.status or "").upper()
            tag_map = {
                "OK": "ok", "AVVIK": "avvik", "MERK": "merk", "MANGLER": "mangler",
            }
            tag = tag_map.get(status, "")
            try:
                tree.insert("", "end", iid=r.id, values=(
                    r.id, r.label, status, r.treff,
                    formatting.fmt_amount(r.beløp) if r.beløp else "",
                    r.kommentar,
                ), tags=(tag,) if tag else ())
            except Exception:
                continue

    def _on_kontroll_double(self, _event: Any = None) -> None:
        tree = getattr(self, "_kontroll_tree", None)
        if tree is None:
            return
        sel = tree.selection()
        if not sel:
            return
        kid = sel[0]
        result = next((r for r in self._kontroll_results if r.id == kid), None)
        if result is None or result.detaljer is None or result.detaljer.empty:
            from tkinter import messagebox
            messagebox.showinfo(
                "Detaljer",
                f"{result.label if result else kid}: ingen detaljer tilgjengelig.",
            )
            return
        self._show_kontroll_details(result)

    def _show_kontroll_details(self, result: Any) -> None:
        top = tk.Toplevel(self)
        top.title(f"Detaljer — {result.label}")
        top.geometry("900x500")
        top.transient(self.winfo_toplevel())
        frame = ttk.Frame(top, padding=8)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame, text=result.label,
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w")
        ttk.Label(frame, text=result.kommentar, foreground="#555").pack(anchor="w", pady=(0, 6))

        df = result.detaljer
        cols = list(df.columns)
        tree = ttk.Treeview(frame, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=str(c))
            tree.column(c, width=max(80, min(240, 10 * len(str(c)) + 40)))
        for _, row in df.iterrows():
            try:
                tree.insert("", "end", values=[row.get(c, "") for c in cols])
            except Exception:
                continue
        tree.pack(fill="both", expand=True)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        vsb.pack(side="right", fill="y")
        tree.configure(yscrollcommand=vsb.set)

    def _build_tab_skyldig(self, parent: Any) -> None:
        """Sub-fane 5: Skyldig MVA bevegelse (HB vs Skatteetaten)."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        header = ttk.Frame(parent, padding=(4, 4))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            header, text="Skyldig MVA — HB vs Skatteetaten",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(side="left")
        self._skyldig_info = ttk.Label(header, text="", foreground="#555")
        self._skyldig_info.pack(side="right")

        body = ttk.Frame(parent, padding=(4, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        body.grid(row=1, column=0, sticky="nsew")

        cols = ("termin", "hb_bev", "skatt_bev", "avvik")
        tree = ttk.Treeview(body, columns=cols, show="headings",
                            selectmode="browse")
        headings = [
            ("termin", "Termin", 80, "center"),
            ("hb_bev", "Bokført bevegelse (HB)", 180, "e"),
            ("skatt_bev", "Betalt/avsatt (Skatteetaten)", 200, "e"),
            ("avvik", "Avvik", 150, "e"),
        ]
        for col_id, label, width, anchor in headings:
            tree.heading(col_id, text=label, anchor=anchor)
            tree.column(col_id, width=width, anchor=anchor,
                        stretch=(col_id == "avvik"))
        tree.tag_configure("sumline", background="#F0F0F0",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure("avvik", foreground="#C0392B",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure("ok", foreground="#1B7F35")
        tree.tag_configure("mangler", foreground="#888")
        tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=vsb.set)

        self._skyldig_tree = tree

    def _refresh_tab_skyldig(self) -> None:
        tree = getattr(self, "_skyldig_tree", None)
        if tree is None:
            return
        try:
            tree.delete(*tree.get_children())
        except Exception:
            pass

        client, year = self._get_session_client_year()

        # --- HB bevegelse på skyldig-MVA-kontoer per termin ---
        hb_bev = {t: 0.0 for t in range(1, 7)}
        hb_count = 0
        page = self._analyse_page
        import pandas as pd
        df = getattr(page, "_df_filtered", None) if page is not None else None
        skyldig_kontoer = [
            k for k, v in self._gruppe_mapping.items()
            if str(v).strip() == _GRP_SKYLDIG
        ]
        if isinstance(df, pd.DataFrame) and not df.empty and skyldig_kontoer:
            from page_analyse_mva import month_to_termin
            konto_col = next(
                (c for c in df.columns if c.lower() == "konto"), None,
            )
            belop_col = next(
                (c for c in df.columns if c.lower() in ("beløp", "belop")), None,
            )
            dato_col = next(
                (c for c in df.columns if c.lower() == "dato"), None,
            )
            if konto_col and belop_col and dato_col:
                work = df[[konto_col, belop_col, dato_col]].copy()
                work["_konto"] = work[konto_col].astype(str).str.strip()
                work = work[work["_konto"].isin(set(skyldig_kontoer))]
                if not work.empty:
                    work["_belop"] = pd.to_numeric(
                        work[belop_col], errors="coerce",
                    ).fillna(0.0)
                    work["_dato"] = pd.to_datetime(
                        work[dato_col], errors="coerce",
                    )
                    work["_termin"] = work["_dato"].dt.month.apply(
                        lambda m: month_to_termin(int(m)) if pd.notna(m) else 0,
                    )
                    grouped = work.groupby("_termin")["_belop"].sum()
                    for t, v in grouped.items():
                        if 1 <= int(t) <= 6:
                            hb_bev[int(t)] = float(v)
                            hb_count += 1

        # --- Skatteetaten bevegelse per termin (fra mva_per_termin) ---
        skatt_bev = {t: None for t in range(1, 7)}
        skatt_count = 0
        try:
            import src.shared.regnskap.client_overrides as rco
            from ..backend.avstemming import SkatteetatenData
            if client and year:
                raw = rco.load_skatteetaten_data(client, year)
                if raw:
                    sd = SkatteetatenData.from_dict(raw)
                    for t, v in sd.mva_per_termin.items():
                        if 1 <= int(t) <= 6:
                            skatt_bev[int(t)] = float(v)
                            skatt_count += 1
        except Exception:
            log.debug("Skatteetaten load feilet for Skyldig-fane", exc_info=True)

        if not skyldig_kontoer:
            self._skyldig_info.configure(
                text="Ingen kontoer klassifisert som 'Skyldig MVA'.",
            )
        else:
            self._skyldig_info.configure(
                text=f"{len(skyldig_kontoer)} skyldig-MVA-kontoer · "
                     f"HB-bevegelse i {hb_count} terminer · "
                     f"Skatteetaten i {skatt_count} terminer",
            )

        def _fmt(val: Any) -> str:
            if val is None:
                return "—"
            try:
                return formatting.fmt_amount(float(val))
            except Exception:
                return "—"

        no_hb_classification = not skyldig_kontoer
        for t in range(1, 7):
            hb = hb_bev[t]
            sk = skatt_bev[t]
            if sk is None:
                avvik_txt = "—"
                tag = ("mangler",)
            elif no_hb_classification:
                avvik_txt = "—"
                tag = ("mangler",)
            else:
                # HB bevegelse er typisk kredit (negativ) når skyldig øker.
                # Avvik: |HB| vs Skatteetaten-beløp.
                diff = abs(hb) - float(sk)
                avvik_txt = formatting.fmt_amount(diff)
                tag = ("ok",) if abs(diff) <= 1.0 else ("avvik",)
            hb_display: Any = hb if not no_hb_classification else None
            try:
                tree.insert("", "end", values=(
                    f"T{t}", _fmt(hb_display), _fmt(sk), avvik_txt,
                ), tags=tag)
            except Exception:
                pass

        sum_hb = sum(hb_bev.values())
        sum_sk = sum((v for v in skatt_bev.values() if v is not None), 0.0) \
            if skatt_count else None
        if no_hb_classification or sum_sk is None:
            avvik = None
        else:
            avvik = abs(sum_hb) - float(sum_sk)
        sum_hb_display: Any = sum_hb if not no_hb_classification else None
        try:
            tree.insert("", "end", values=(
                "Sum",
                _fmt(sum_hb_display),
                _fmt(sum_sk),
                _fmt(avvik),
            ), tags=("sumline",))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Toolbar-callbacks: stubs foreløpig, full implementasjon i steg 7
    # ------------------------------------------------------------------

    def _open_mva_config(self) -> None:
        """Åpne MVA-oppsett-dialogen (flyttet fra Analyse-fanen i steg 7)."""
        try:
            import session as _session
            from . import config_dialog as mva_config_dialog
            client = str(getattr(_session, "client", None) or "").strip()
            if not client:
                from tkinter import messagebox
                messagebox.showinfo(
                    "MVA-oppsett",
                    "Velg en klient først for å konfigurere MVA-kode-mapping.",
                )
                return
            if mva_config_dialog.open_mva_config(self.winfo_toplevel(), client):
                self._refresh_all()
        except Exception as exc:
            log.exception("Kunne ikke åpne MVA-oppsett: %s", exc)

    def _import_skatteetaten(self) -> None:
        """Velg og importer Skatteetaten kontoutskrift (Excel)."""
        from tkinter import filedialog, messagebox

        client, year = self._get_session_client_year()
        if not client:
            messagebox.showinfo(
                "Importer Skatteetaten",
                "Velg en klient før du importerer kontoutskrift.",
            )
            return
        if not year:
            messagebox.showinfo(
                "Importer Skatteetaten",
                "Sett år på klienten før du importerer kontoutskrift.",
            )
            return

        path = filedialog.askopenfilename(
            title="Velg Skatteetaten kontoutskrift",
            filetypes=[("Excel", "*.xlsx *.xls"), ("Alle filer", "*.*")],
        )
        if not path:
            return

        try:
            from ..backend.avstemming import parse_skatteetaten_kontoutskrift
            data = parse_skatteetaten_kontoutskrift(path, year=year)
        except Exception as exc:
            log.exception("Feil ved parsing av Skatteetaten-fil")
            messagebox.showerror(
                "Importer Skatteetaten",
                f"Kunne ikke lese filen:\n{exc}",
            )
            return

        try:
            import src.shared.regnskap.client_overrides as rco
            rco.save_skatteetaten_data(client, year, data.to_dict())
        except Exception as exc:
            log.exception("Kunne ikke lagre Skatteetaten-data")
            messagebox.showerror(
                "Importer Skatteetaten",
                f"Kunne ikke lagre:\n{exc}",
            )
            return

        n_terminer = len(data.mva_per_termin)
        messagebox.showinfo(
            "Importer Skatteetaten",
            f"Importert {n_terminer} MVA-terminer for {year}.",
        )
        self._loaded_tabs.discard(2)
        self._loaded_tabs.discard(4)
        try:
            idx = self._notebook.index(self._notebook.select())
            if idx == 2:
                self._refresh_tab_avstemming()
            elif idx == 4:
                self._refresh_tab_skyldig()
        except Exception:
            pass

    def _import_mva_melding(self) -> None:
        """Velg og importer Altinn MVA-melding (JSON)."""
        from tkinter import filedialog, messagebox

        client, year = self._get_session_client_year()
        if not client:
            messagebox.showinfo(
                "Importer MVA-melding",
                "Velg en klient før du importerer MVA-melding.",
            )
            return

        path = filedialog.askopenfilename(
            title="Velg MVA-melding (JSON)",
            filetypes=[("JSON", "*.json"), ("Alle filer", "*.*")],
        )
        if not path:
            return

        try:
            from ..backend.melding_parser import parse_mva_melding
            melding = parse_mva_melding(path)
        except Exception as exc:
            log.exception("Feil ved parsing av MVA-melding")
            messagebox.showerror(
                "Importer MVA-melding",
                f"Kunne ikke lese filen:\n{exc}",
            )
            return

        save_year = melding.år or _to_int_or_default(year)
        if not save_year:
            messagebox.showerror(
                "Importer MVA-melding",
                "Klarte ikke å bestemme årstall for MVA-meldingen.",
            )
            return

        try:
            import src.shared.regnskap.client_overrides as rco
            rco.save_mva_melding(client, save_year, melding.termin, melding.to_dict())
        except Exception as exc:
            log.exception("Kunne ikke lagre MVA-melding")
            messagebox.showerror(
                "Importer MVA-melding",
                f"Kunne ikke lagre:\n{exc}",
            )
            return

        messagebox.showinfo(
            "Importer MVA-melding",
            f"Importert MVA-melding for T{melding.termin} {save_year}.",
        )
        self._loaded_tabs.discard(2)
        try:
            idx = self._notebook.index(self._notebook.select())
            if idx == 2:
                self._refresh_tab_avstemming()
        except Exception:
            pass

    def _on_tab_changed(self, _event: Any = None) -> None:
        """Lazy-refresh av sub-fane som blir synlig første gang."""
        nb = getattr(self, "_notebook", None)
        if nb is None:
            return
        try:
            idx = nb.index(nb.select())
        except Exception:
            return
        if idx in self._loaded_tabs:
            return
        self._loaded_tabs.add(idx)
        refreshers = {
            1: getattr(self, "_refresh_tab_kode_termin", None),
            2: getattr(self, "_refresh_tab_avstemming", None),
            3: getattr(self, "_refresh_tab_kontroller", None),
            4: getattr(self, "_refresh_tab_skyldig", None),
        }
        fn = refreshers.get(idx)
        if callable(fn):
            try:
                fn()
            except Exception:
                log.exception("Refresh av sub-fane %s feilet", idx)

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
        if not self._gruppe_mapping:
            self._status_lbl.configure(
                text="Ingen kontoer klassifisert. Bruk 'Klassifiser kontoer' i Analyse-fanen."
            )
            return
        import konto_klassifisering as _kk
        groups = _kk.all_groups_in_use(self._gruppe_mapping)
        mva_grps = [g for g in groups if "mva" in g.lower()]
        n_mva_kontoer = sum(
            1 for v in self._gruppe_mapping.values() if "mva" in str(v).lower()
        )
        if not mva_grps:
            self._status_lbl.configure(
                text="Ingen MVA-grupper klassifisert. Klassifiser kontoer som "
                     "'Utgående MVA', 'Inngående MVA' eller 'Skyldig MVA' i Analyse-fanen."
            )
        else:
            self._status_lbl.configure(
                text=f"{n_mva_kontoer} MVA-kontoer | {len(mva_grps)} MVA-grupper"
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

        # Kun MVA-relevante grupper vises i MVA-fanen
        mva_groups = [g for g in _MVA_GROUPS_ORDERED if g in all_groups]
        other_mva = [
            g for g in all_groups
            if "mva" in g.lower() and g not in mva_groups
        ]
        mva_groups += other_mva

        if not mva_groups:
            tree.insert("", "end", values=(
                "Ingen kontoer er klassifisert som MVA-grupper "
                "('Utgående MVA', 'Inngående MVA' eller 'Skyldig MVA'). "
                "Klassifiser kontoer i Analyse-fanen for å aktivere MVA-sammendraget.",
                "", "", "",
            ), tags=(_TAG_RECON,))
            return

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

        # Avstemming (netto utg/inn vs skyldig)
        self._insert_recon(tree, totals)

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

            # Tving refresh av alle sub-faner slik at treene har data.
            for idx, refresher in (
                (1, getattr(self, "_refresh_tab_kode_termin", None)),
                (2, getattr(self, "_refresh_tab_avstemming", None)),
                (3, getattr(self, "_refresh_tab_kontroller", None)),
                (4, getattr(self, "_refresh_tab_skyldig", None)),
            ):
                if callable(refresher):
                    try:
                        refresher()
                        self._loaded_tabs.add(idx)
                    except Exception:
                        log.exception("Kunne ikke refreshe sub-fane %s før eksport", idx)

            sheets: list[dict] = []

            sheets.append(_xls.treeview_to_sheet(
                self._summary_tree,
                title="Sammendrag",
                heading="MVA-analyse — Sammendrag",
                bold_tags=(_TAG_HEADER, _TAG_RECON, _TAG_OK, _TAG_AVVIK),
                bg_tags={_TAG_HEADER: "BDD7EE", _TAG_OK: "E8F5E9", _TAG_AVVIK: "FFEBEE"},
            ))

            sheets.append(_xls.treeview_to_sheet(
                self._konto_tree,
                title="Kontoer",
                heading=f"Kontoer: {self._selected_gruppe}" if self._selected_gruppe
                        else "Kontoer",
                bold_tags=(_TAG_HEADER,),
                bg_tags={_TAG_HEADER: "BDD7EE"},
            ))

            kode_tree = getattr(self, "_kode_termin_tree", None)
            if kode_tree is not None:
                sheets.append(_xls.treeview_to_sheet(
                    kode_tree,
                    title="Per kode termin",
                    heading="MVA-pivot per kode og termin (T1–T6)",
                    bold_tags=(_TAG_HEADER, _TAG_RECON),
                    bg_tags={_TAG_HEADER: "BDD7EE"},
                ))

            av_tree = getattr(self, "_avstemming_tree", None)
            if av_tree is not None:
                sheets.append(_xls.treeview_to_sheet(
                    av_tree,
                    title="Avstemming HB",
                    heading="3-veis avstemming: HB vs MVA-melding vs Skatteetaten",
                    bold_tags=(_TAG_HEADER, _TAG_RECON, _TAG_OK, _TAG_AVVIK),
                    bg_tags={_TAG_HEADER: "BDD7EE", _TAG_OK: "E8F5E9", _TAG_AVVIK: "FFEBEE"},
                ))

            kontroll_tree = getattr(self, "_kontroll_tree", None)
            if kontroll_tree is not None:
                sheets.append(_xls.treeview_to_sheet(
                    kontroll_tree,
                    title="Kontroller",
                    heading="MVA-kontroller K1–K6",
                    bold_tags=(_TAG_HEADER,),
                    bg_tags={_TAG_HEADER: "BDD7EE", _TAG_OK: "E8F5E9", _TAG_AVVIK: "FFEBEE"},
                ))

            skyldig_tree = getattr(self, "_skyldig_tree", None)
            if skyldig_tree is not None:
                sheets.append(_xls.treeview_to_sheet(
                    skyldig_tree,
                    title="Skyldig saldo",
                    heading="Skyldig MVA — bevegelse vs Skatteetaten",
                    bold_tags=(_TAG_HEADER, _TAG_RECON),
                    bg_tags={_TAG_HEADER: "BDD7EE", _TAG_OK: "E8F5E9", _TAG_AVVIK: "FFEBEE"},
                ))

            _xls.export_and_open(path, sheets,
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
