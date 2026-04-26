"""page_skatt.py — Skatteanalyse fane.

Henter regnskapstall direkte fra Analyse-siden og beregner:
  - Nominell skatt (22 % av resultat før skatt)
  - Bokført skattekostnad (regnr 260)
  - Effektiv skattesats
  - Avvik (permanente + midlertidige forskjeller)
  - Utsatt skatt (BS)
  - Betalbar skatt (BS)

Brukeren kan legge inn permanente og midlertidige forskjeller manuelt —
disse lagres per klient via preferences.
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
# Konstanter
# ---------------------------------------------------------------------------

_SKATT_SATS     = 0.22          # 22 % selskapsskatt
_REGNR_FØR_SKATT = 160          # Resultat før skattekostnad
_REGNR_SKATT_KST  = 260         # Skattekostnad (RS)
_REGNR_BETBAR     = 800         # Skattetrekk og offentlige avgifter (BS, typisk for skyldig skatt)
# Merk: Betalbar skatt på BS er ofte konto 2500 (regnr varierer).
# Vi bruker konto_klassifisering gruppen "Betalbar skatt" som primærkilde.
# Fallback: regnr 800.

_TAG_HEADER = "header"
_TAG_AUTO   = "auto"
_TAG_INPUT  = "input_row"
_TAG_OK     = "ok"
_TAG_AVVIK  = "avvik"
_TAG_INFO   = "info"


# ---------------------------------------------------------------------------
# Hjelpefunksjoner
# ---------------------------------------------------------------------------

def _ub_for_regnr(rl_df: Any, regnr: int) -> float:
    """Hent UB for ett regnr fra rl_df. Respekterer credit-inversjon."""
    try:
        from regnskap_data import ub_lookup
        lkp = ub_lookup(rl_df, "ub")
        return float(lkp.get(regnr, 0.0))
    except Exception:
        return 0.0


def _sum_ub_for_gruppe(sb_df: Any, gruppe_mapping: dict[str, str],
                        gruppe: str, col_map: dict[str, str]) -> float:
    """Sum UB for alle kontoer i gitt klassifiseringsgruppe."""
    import pandas as pd
    kontoer = {k for k, v in gruppe_mapping.items() if v == gruppe}
    if not kontoer:
        return 0.0
    konto_src = col_map.get("konto", "")
    ub_col    = col_map.get("ub", "")
    if not konto_src or not ub_col:
        return 0.0
    mask = sb_df[konto_src].astype(str).isin(kontoer)
    return float(pd.to_numeric(sb_df[mask][ub_col], errors="coerce").fillna(0.0).sum())


def _resolve_sb_columns(sb_df: Any) -> dict[str, str]:
    col_map: dict[str, str] = {}
    for c in sb_df.columns:
        cl = c.lower()
        if cl == "konto":
            col_map["konto"] = c
        elif cl == "kontonavn":
            col_map["kontonavn"] = c
        elif cl in ("netto", "endring"):
            col_map["endring"] = c
        elif cl == "ub":
            col_map["ub"] = c
    return col_map


# ---------------------------------------------------------------------------
# Hoved-side
# ---------------------------------------------------------------------------

class SkattPage(ttk.Frame):  # type: ignore[misc]

    def __init__(self, master: Any) -> None:
        super().__init__(master)
        self._analyse_page: Any = None
        self._rl_df: Any = None
        self._sb_df: Any = None
        self._gruppe_mapping: dict[str, str] = {}
        self._col_map: dict[str, str] = {}
        self._client: str = ""

        # Input-felter for manuell justering
        self._perm_var:   Any = None
        self._midf_var:   Any = None

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
        tb = ttk.Frame(self, padding=(6, 4))
        tb.grid(row=0, column=0, sticky="ew")

        ttk.Label(tb, text="Skatteanalyse",
                  font=("TkDefaultFont", 11, "bold")).pack(side="left", padx=(0, 12))
        ttk.Button(tb, text="Beregn", command=self._refresh_all,
                   width=10).pack(side="left")
        ttk.Button(tb, text="Eksporter til Excel\u2026",
                   command=self._export_excel).pack(side="left", padx=(6, 0))
        self._status_lbl = ttk.Label(tb, text="", foreground="#555")
        self._status_lbl.pack(side="left", padx=(12, 0))

        # Hoved-layout: venstre = beregning, høyre = forklaringer
        main = ttk.Frame(self)
        main.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        main.columnconfigure(0, weight=2)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        # Venstre: beregningstabell
        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        ttk.Label(left, text="Beregning",
                  font=("TkDefaultFont", 10, "bold")).grid(
                      row=0, column=0, sticky="w", pady=(0, 4))

        self._calc_tree = self._make_calc_tree(left)
        self._calc_tree.grid(row=1, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(left, orient="vertical",
                             command=self._calc_tree.yview)
        vsb.grid(row=1, column=1, sticky="ns")
        self._calc_tree.configure(yscrollcommand=vsb.set)

        # Input-seksjon (under beregningstabell)
        inp = ttk.LabelFrame(left, text="Justeringer (manuelle)", padding=(8, 4))
        inp.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        inp.columnconfigure(1, weight=1)

        self._perm_var = tk.StringVar(value="0")
        self._midf_var = tk.StringVar(value="0")

        ttk.Label(inp, text="Permanente forskjeller:").grid(
            row=0, column=0, sticky="w", padx=(0, 8))
        perm_e = ttk.Entry(inp, textvariable=self._perm_var, width=18)
        perm_e.grid(row=0, column=1, sticky="w", pady=2)
        perm_e.bind("<Return>", lambda _e: self._refresh_all())
        perm_e.bind("<FocusOut>", lambda _e: self._refresh_all())

        ttk.Label(inp, text="Midlertidige forskjeller (endring):").grid(
            row=1, column=0, sticky="w", padx=(0, 8))
        midf_e = ttk.Entry(inp, textvariable=self._midf_var, width=18)
        midf_e.grid(row=1, column=1, sticky="w", pady=2)
        midf_e.bind("<Return>", lambda _e: self._refresh_all())
        midf_e.bind("<FocusOut>", lambda _e: self._refresh_all())

        ttk.Label(inp, text="Positive = øker skattegrunnlaget.",
                  foreground="#888").grid(row=2, column=0, columnspan=2,
                                          sticky="w", pady=(2, 0))

        # Høyre: forklaring + effektiv sats
        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)

        ttk.Label(right, text="Nøkkeltall",
                  font=("TkDefaultFont", 10, "bold")).grid(
                      row=0, column=0, sticky="w", pady=(0, 4))

        self._kpi_text = tk.Text(right, width=28, height=14,
                                  state="disabled", relief="flat",
                                  bg="#F4F6F9", font=("TkDefaultFont", 10),
                                  wrap="word")
        self._kpi_text.grid(row=1, column=0, sticky="nsew")
        right.rowconfigure(1, weight=1)
        self._kpi_text.tag_configure("bold",  font=("TkDefaultFont", 10, "bold"))
        self._kpi_text.tag_configure("green", foreground="#1B7F35")
        self._kpi_text.tag_configure("red",   foreground="#C0392B")
        self._kpi_text.tag_configure("gray",  foreground="#888888")

    def _make_calc_tree(self, parent: Any) -> Any:
        cols = ("post", "beregnet", "bokfort", "avvik")
        tree = ttk.Treeview(parent, columns=cols, show="headings",
                             selectmode="none", height=14)
        tree.heading("post",      text="Post",       anchor="w")
        tree.heading("beregnet",  text="Beregnet",   anchor="e")
        tree.heading("bokfort",   text="Bokført",    anchor="e")
        tree.heading("avvik",     text="Avvik",      anchor="e")
        tree.column("post",      width=300, anchor="w", stretch=True)
        tree.column("beregnet",  width=130, anchor="e", stretch=False)
        tree.column("bokfort",   width=130, anchor="e", stretch=False)
        tree.column("avvik",     width=120, anchor="e", stretch=False)
        tree.tag_configure(_TAG_HEADER, background="#E8EFF7",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure(_TAG_AUTO,   foreground="#1A56A0")
        tree.tag_configure(_TAG_INFO,   foreground="#555555",
                           font=("TkDefaultFont", 9, "italic"))
        tree.tag_configure(_TAG_OK,     foreground="#1B7F35",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure(_TAG_AVVIK,  foreground="#C0392B",
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
                title="Eksporter Skatteanalyse",
                default_filename=f"skatteanalyse_{client}_{year}.xlsx".strip("_"),
                master=self,
            )
            if not path:
                return
            calc_sheet = _xls.treeview_to_sheet(
                self._calc_tree,
                title="Beregning",
                heading="Skatteanalyse — Beregning",
                bold_tags=(_TAG_HEADER, _TAG_OK, _TAG_AVVIK),
                bg_tags={_TAG_HEADER: "BDD7EE", _TAG_OK: "E8F5E9", _TAG_AVVIK: "FFEBEE"},
            )
            _xls.export_and_open(path, [calc_sheet],
                                  title="Skatteanalyse", client=client, year=year)
        except Exception as e:
            log.exception("Skatt Excel-eksport feilet: %s", e)

    def _load_data(self) -> None:
        import pandas as pd
        self._rl_df = None
        self._sb_df = None
        self._gruppe_mapping = {}
        self._col_map = {}
        self._client = ""

        page = self._analyse_page
        if page is None:
            return

        self._rl_df = getattr(page, "_rl_df", None)

        sb_df = getattr(page, "_rl_sb_df", None)
        if sb_df is not None and isinstance(sb_df, pd.DataFrame) and not sb_df.empty:
            try:
                sb_df = page._get_effective_sb_df()
            except Exception:
                pass
            self._sb_df = sb_df
            self._col_map = _resolve_sb_columns(sb_df)

        try:
            import konto_klassifisering as _kk
            import session as _session
            self._client = getattr(_session, "client", None) or ""
            if self._client:
                self._gruppe_mapping = _kk.load(self._client)
        except Exception:
            pass

        # Last lagrede justeringer
        self._load_adjustments()

    def _load_adjustments(self) -> None:
        try:
            import preferences
            safe = "".join(c if c.isalnum() else "_"
                           for c in (self._client or "default"))
            perm = preferences.get(f"skatt.{safe}.perm_forskj") or "0"
            midf = preferences.get(f"skatt.{safe}.midf") or "0"
            if self._perm_var is not None:
                self._perm_var.set(str(perm))
            if self._midf_var is not None:
                self._midf_var.set(str(midf))
        except Exception:
            pass

    def _save_adjustments(self) -> None:
        try:
            import preferences
            safe = "".join(c if c.isalnum() else "_"
                           for c in (self._client or "default"))
            if self._perm_var is not None:
                preferences.set(f"skatt.{safe}.perm_forskj",
                                 self._perm_var.get())
            if self._midf_var is not None:
                preferences.set(f"skatt.{safe}.midf",
                                 self._midf_var.get())
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Beregning
    # ------------------------------------------------------------------

    def _get_float_input(self, var: Any) -> float:
        try:
            raw = (var.get() if var is not None else "0")
            return float(str(raw).replace(",", ".").replace(" ", "") or "0")
        except (ValueError, TypeError):
            return 0.0

    def _refresh_all(self) -> None:
        self._save_adjustments()
        self._populate_calc()
        self._update_kpi()

    def _compute(self) -> dict[str, float]:
        """Beregn alle skattetall. Returner dict med nøkler."""
        r: dict[str, float] = {}

        # Resultat før skatt (RS, regnr 160 — positiv = overskudd)
        r["res_for_skatt"] = _ub_for_regnr(self._rl_df, _REGNR_FØR_SKATT) \
            if self._rl_df is not None else 0.0

        # Bokført skattekostnad (RS, regnr 260 — kostnad er positiv)
        r["bokfort_skatt_kst"] = _ub_for_regnr(self._rl_df, _REGNR_SKATT_KST) \
            if self._rl_df is not None else 0.0

        # Betalbar skatt på BS — fra klassifisering om tilgjengelig
        r["betbar_bs"] = 0.0
        if self._sb_df is not None:
            grp_betbar = _sum_ub_for_gruppe(
                self._sb_df, self._gruppe_mapping,
                "Betalbar skatt", self._col_map)
            if grp_betbar:
                r["betbar_bs"] = grp_betbar
            else:
                r["betbar_bs"] = _ub_for_regnr(
                    self._rl_df, _REGNR_BETBAR) \
                    if self._rl_df is not None else 0.0

        # Utsatt skatt på BS — fra klassifisering om tilgjengelig
        r["utsatt_bs"] = 0.0
        if self._sb_df is not None:
            r["utsatt_bs"] = _sum_ub_for_gruppe(
                self._sb_df, self._gruppe_mapping,
                "Utsatt skatt", self._col_map)

        # Justeringer
        r["perm"]  = self._get_float_input(self._perm_var)
        r["midf"]  = self._get_float_input(self._midf_var)

        # Grunnlag betalbar skatt
        r["grunnlag"] = r["res_for_skatt"] + r["perm"] + r["midf"]

        # Nominell skatt
        r["nominell"]  = r["res_for_skatt"] * _SKATT_SATS
        r["beregnet_betbar"] = r["grunnlag"] * _SKATT_SATS if r["grunnlag"] > 0 else 0.0

        # Effektiv skattesats
        r["effektiv_sats"] = (
            r["bokfort_skatt_kst"] / r["res_for_skatt"]
            if abs(r["res_for_skatt"]) > 1 else 0.0
        )

        # Avvik
        r["avvik_betbar"]  = r["beregnet_betbar"] - abs(r["betbar_bs"])
        r["avvik_totskatt"] = r["nominell"] - r["bokfort_skatt_kst"]

        return r

    def _populate_calc(self) -> None:
        tree = self._calc_tree
        tree.delete(*tree.get_children())

        if self._rl_df is None:
            tree.insert("", "end", values=("Ingen data. Last inn en datafil.", "", "", ""),
                        tags=(_TAG_INFO,))
            return

        v = self._compute()
        F = formatting.fmt_amount
        na = ""

        def row(post: str, bere: str = "", bokf: str = "", avv: str = "",
                tag: str = "") -> None:
            tags = (tag,) if tag else ()
            tree.insert("", "end", values=(post, bere, bokf, avv), tags=tags)

        # --- Resultatskatt ---
        row("RESULTATSBASERT SKATT", tag=_TAG_HEADER)
        row("  Resultat før skattekostnad",
            bere=F(v["res_for_skatt"]), bokf=na)
        row(f"  Nominell skatt ({_SKATT_SATS*100:.0f} %)",
            bere=F(v["nominell"]), bokf=na)
        row("  Bokført skattekostnad (regnr 260)",
            bere=na, bokf=F(v["bokfort_skatt_kst"]))

        diff_tot = v["avvik_totskatt"]
        ok_tot = abs(diff_tot) < max(500.0, abs(v["nominell"]) * 0.05)
        tot_tag = _TAG_OK if ok_tot else _TAG_AVVIK
        diff_label = "✓" if ok_tot else f"⚠ {F(diff_tot)}"
        row(f"  Avvik nom. vs bokført  {diff_label}",
            bere=na, bokf=na, avv=F(diff_tot), tag=tot_tag)

        # --- Grunnlag betalbar skatt ---
        row("BETALBAR SKATT", tag=_TAG_HEADER)
        row("  Resultat før skattekostnad",
            bere=F(v["res_for_skatt"]), bokf=na)
        row("  + Permanente forskjeller (manuelt)",
            bere=F(v["perm"]), bokf=na)
        row("  + Endring midlertidige forskjeller (manuelt)",
            bere=F(v["midf"]), bokf=na)
        row("  = Grunnlag betalbar skatt",
            bere=F(v["grunnlag"]), bokf=na, tag=_TAG_HEADER)
        row(f"  Beregnet betalbar skatt ({_SKATT_SATS*100:.0f} %)",
            bere=F(v["beregnet_betbar"]), bokf=na)
        row("  Betalbar skatt på balansen",
            bere=na, bokf=F(v["betbar_bs"]))

        diff_betbar = v["avvik_betbar"]
        ok_betbar = abs(diff_betbar) < max(500.0, abs(v["beregnet_betbar"]) * 0.05)
        betbar_tag = _TAG_OK if ok_betbar else _TAG_AVVIK
        betbar_label = "✓" if ok_betbar else f"⚠ {F(diff_betbar)}"
        row(f"  Avvik beregnet vs balanse  {betbar_label}",
            bere=na, bokf=na, avv=F(diff_betbar), tag=betbar_tag)

        # --- Utsatt skatt ---
        row("UTSATT SKATT (BALANSE)", tag=_TAG_HEADER)
        row("  Utsatt skatt / skattefordel",
            bere=na, bokf=F(v["utsatt_bs"]),
            tag=_TAG_AUTO if v["utsatt_bs"] else _TAG_INFO)

    def _update_kpi(self) -> None:
        if self._rl_df is None:
            self._kpi_write([("Ingen data.", "gray")])
            self._status_lbl.configure(text="Ingen data")
            return

        v = self._compute()
        F = formatting.fmt_amount

        eff_pct = v["effektiv_sats"] * 100
        nom_pct = _SKATT_SATS * 100
        avvik_pct = eff_pct - nom_pct

        lines: list[tuple[str, str]] = []
        lines.append((f"Resultat før skatt\n{F(v['res_for_skatt'])}\n\n", "bold"))

        lines.append(("Nominell skattesats\n", ""))
        lines.append((f"{nom_pct:.1f} %\n\n", "bold"))

        lines.append(("Effektiv skattesats\n", ""))
        color = "green" if abs(avvik_pct) < 2.0 else "red"
        lines.append((f"{eff_pct:.1f} %  ({avvik_pct:+.1f} pp)\n\n", color))

        lines.append(("Bokført skattekostnad\n", ""))
        lines.append((f"{F(v['bokfort_skatt_kst'])}\n\n", "bold"))

        lines.append(("Betalbar skatt (BS)\n", ""))
        lines.append((f"{F(v['betbar_bs'])}\n\n", "bold"))

        if v["utsatt_bs"]:
            lines.append(("Utsatt skatt (BS)\n", ""))
            lines.append((f"{F(v['utsatt_bs'])}\n\n", "bold"))

        self._kpi_write(lines)
        self._status_lbl.configure(
            text=f"Effektiv sats: {eff_pct:.1f} %  |  Nominell: {nom_pct:.0f} %"
        )

    def _kpi_write(self, parts: list[tuple[str, str]]) -> None:
        try:
            self._kpi_text.configure(state="normal")
            self._kpi_text.delete("1.0", "end")
            for text, tag in parts:
                if tag:
                    self._kpi_text.insert("end", text, tag)
                else:
                    self._kpi_text.insert("end", text)
            self._kpi_text.configure(state="disabled")
        except Exception:
            pass
