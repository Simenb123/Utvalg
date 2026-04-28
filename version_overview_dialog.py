"""Versions (HB/SB) dialog.

This dialog started as a simple list for the active *Hovedbok* file per
client/year. With the introduction of *Saldobalanse* (trial balance), the old
"Type" dropdown became easy to miss and therefore confusing.

This version uses tabs (Notebook) and a summary line so it is always clear:
- whether a saldobalanse exists
- which version is active

Additionally, when a SAF-T file is imported as hovedbok, we can also extract a
trial balance from the same SAF-T file (MasterFiles/GeneralLedgerAccount) and
create a saldobalanse version automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import logging
import re
import os
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import src.shared.client_store.store as client_store

_log = logging.getLogger(__name__)


DTYPE_LABELS: dict[str, str] = {
    "hb": "Hovedbok",
    "sb": "Saldobalanse",
    "kr": "Kundereskontro",
    "lr": "Leverandørreskontro",
    "saft": "SAF-T",
}


def _dtype_label(dtype: str) -> str:
    return DTYPE_LABELS.get(dtype, dtype)


def _fmt_ts(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _fmt_size(num_bytes: int) -> str:
    """Format filstørrelse i menneskelesbar form (B/KB/MB/GB)."""
    try:
        n = float(num_bytes)
    except Exception:
        return "—"
    if n < 1024:
        return f"{int(n)} B"
    n /= 1024
    if n < 1024:
        return f"{n:.0f} KB"
    n /= 1024
    if n < 1024:
        return f"{n:.1f} MB"
    n /= 1024
    return f"{n:.2f} GB"


def _version_created_ts(version) -> float:
    """Backwards-compatible timestamp accessor for version rows."""
    try:
        return float(getattr(version, "created_at", None) or getattr(version, "created_ts", None) or 0.0)
    except Exception:
        return 0.0


def _open_path(path: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        _log.exception("Failed to open path: %s", path)


def _get_active_version_id(client: str, year: int, dtype: str) -> str | None:
    if hasattr(client_store, "get_active_version_id"):
        try:
            return client_store.get_active_version_id(client, year=year, dtype=dtype)
        except Exception:
            return None

    # Backwards compatible: get_active_version() -> VersionInfo | None
    try:
        av = client_store.get_active_version(client, year=year, dtype=dtype)
        return av.id if av else None
    except Exception:
        return None


def _set_active_version_id(client: str, year: int, dtype: str, version_id: str) -> None:
    if hasattr(client_store, "set_active_version_id"):
        client_store.set_active_version_id(client, year=year, dtype=dtype, version_id=version_id)
        return

    # Backwards compatible: set_active_version(client, year, dtype, version)
    client_store.set_active_version(client, year=year, dtype=dtype, version_id=version_id)


def _label_for_version(client: str, year: int, dtype: str, version_id: str) -> str:
    """Returner et menneskelesbart navn for en versjon (filnavn eller ID)."""
    try:
        v = client_store.get_version(client, year=year, dtype=dtype, version_id=version_id)
        if v is not None:
            name = Path(getattr(v, "filename", "") or getattr(v, "path", "")).name
            return name or version_id
    except Exception:
        pass
    return version_id


def _load_version_df(client: str, year: int, dtype: str, version_id: str):
    """Last en versjon (HB eller SB) som DataFrame. Returnerer None ved feil."""
    if dtype == "hb":
        return _load_hb_version_df(client, year, version_id)
    if dtype == "sb":
        return _load_sb_version_df(client, year, version_id)
    return None


def _load_hb_version_df(client: str, year: int, version_id: str):
    """Last en HB-versjon som DataFrame. Returnerer None ved feil/manglende fil."""
    try:
        v = client_store.get_version(client, year=year, dtype="hb", version_id=version_id)
    except Exception:
        return None
    if v is None:
        return None

    # Forsøk SQLite-cache først
    try:
        dc = (getattr(v, "meta", None) or {}).get("dataset_cache", {})
        if isinstance(dc, dict) and dc.get("file"):
            import src.pages.dataset.backend.cache_sqlite as dataset_cache_sqlite
            ds_dir = client_store.datasets_dir(client, year=year, dtype="hb")
            db_path = ds_dir / str(dc["file"])
            if db_path.exists():
                df, _ = dataset_cache_sqlite.load_cache(db_path)
                if df is not None and not df.empty:
                    return df
    except Exception:
        _log.debug("Cache load failed for %s, falling back to file build", version_id)

    # Fallback: bygg fra fil med lagret mapping
    try:
        from src.pages.dataset.backend.build_fast import build_from_file

        build_info = ((getattr(v, "meta", None) or {}).get("dataset_cache") or {}).get("build") or {}
        mapping = build_info.get("mapping")
        sheet_name = build_info.get("sheet_name")
        header_row = build_info.get("header_row", 1)

        p = Path(getattr(v, "path", ""))
        if not p.exists():
            return None
        return build_from_file(p, mapping=mapping, sheet_name=sheet_name, header_row=header_row)
    except Exception:
        _log.exception("Failed to build df for HB version %s", version_id)
        return None


def _load_sb_version_df(client: str, year: int, version_id: str):
    """Last en SB-versjon som DataFrame via trial_balance_reader."""
    try:
        v = client_store.get_version(client, year=year, dtype="sb", version_id=version_id)
    except Exception:
        return None
    if v is None:
        return None
    p = Path(getattr(v, "path", ""))
    if not p.exists():
        return None
    try:
        from trial_balance_reader import read_trial_balance
        return read_trial_balance(p)
    except Exception:
        _log.exception("Failed to read SB version %s", version_id)
        return None


def _pick_compare_version(parent: tk.Misc, versions, *, exclude_id: str | None) -> str | None:
    """Modal mini-dialog: la brukeren velge hvilken HB-versjon som skal være
    "A" (sammenlignings-grunnlag). Den valgte ekskluderes (= "B" / gjeldende).
    """
    result: dict[str, str | None] = {"id": None}

    win = tk.Toplevel(parent)
    win.title("Velg sammenlignings-versjon")
    win.transient(parent)
    win.grab_set()
    try:
        win.geometry("520x360")
    except Exception:
        pass

    ttk.Label(
        win,
        text="Velg en eldre HB-versjon å sammenligne mot den valgte/aktive:",
        padding=(12, 12, 12, 6),
    ).pack(anchor="w")

    list_frame = ttk.Frame(win, padding=(12, 0, 12, 6))
    list_frame.pack(fill="both", expand=True)

    cols = ("file", "size", "created")
    tree = ttk.Treeview(list_frame, columns=cols, show="headings", selectmode="browse")
    tree.heading("file", text="Fil")
    tree.heading("size", text="Størrelse")
    tree.heading("created", text="Importert")
    tree.column("file", width=300)
    tree.column("size", width=80, anchor="e")
    tree.column("created", width=130)
    sb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    candidates = [v for v in versions if v.id != exclude_id]
    for v in sorted(candidates, key=_version_created_ts, reverse=True):
        file_path = Path(getattr(v, "path", ""))
        try:
            size = _fmt_size(file_path.stat().st_size)
        except Exception:
            size = "—"
        tree.insert("", "end", iid=v.id,
                    values=(file_path.name, size, _fmt_ts(_version_created_ts(v))))

    def _ok() -> None:
        sel = tree.selection()
        if sel:
            result["id"] = sel[0]
        win.destroy()

    def _cancel() -> None:
        win.destroy()

    btn_row = ttk.Frame(win, padding=(12, 0, 12, 12))
    btn_row.pack(fill="x")
    ttk.Button(btn_row, text="Avbryt", command=_cancel).pack(side="right", padx=(8, 0))
    ttk.Button(btn_row, text="Sammenlign", command=_ok).pack(side="right")
    tree.bind("<Double-1>", lambda _e: _ok())
    tree.bind("<Return>", lambda _e: _ok())

    win.wait_window()
    return result["id"]


class _VersionDiffDialog:
    """GUI-popup som viser versjonsdiff (HB eller SB) med faner.

    Felles dialog for HB- og SB-diff. dtype styrer hvilken Excel-modul
    som brukes for eksport, hvilke kolonner som vises, og hva sammendrag-
    teksten sier.
    """

    def __init__(
        self, parent: tk.Misc, result, *,
        client: str, year: int, dtype: str,
        a_label: str, b_label: str,
    ) -> None:
        self._parent = parent
        self._result = result
        self._client = client
        self._year = year
        self._dtype = dtype
        self._a_label = a_label
        self._b_label = b_label
        self.top: tk.Toplevel | None = None

    def show(self) -> None:
        self.top = tk.Toplevel(self._parent)
        title_main = "Hovedbok" if self._dtype == "hb" else "Saldobalanse"
        self.top.title(f"{title_main} — versjonsdiff")
        self.top.transient(self._parent)
        self.top.grab_set()

        try:
            sw = self.top.winfo_screenwidth()
            sh = self.top.winfo_screenheight()
            w = max(960, min(int(sw * 0.65), 1300))
            h = max(580, min(int(sh * 0.70), 800))
            self.top.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")
            self.top.minsize(900, 500)
        except Exception:
            pass

        frm = ttk.Frame(self.top, padding=(14, 12, 14, 12))
        frm.pack(fill="both", expand=True)

        # Header
        ttk.Label(
            frm, text=f"Versjonsdiff — {title_main}",
            font=("Segoe UI", 16, "bold"), foreground="#1a4c7a",
        ).pack(anchor="w")
        ttk.Label(
            frm, text=f"{self._a_label}  →  {self._b_label}",
            font=("Segoe UI", 10), foreground="#444",
        ).pack(anchor="w", pady=(2, 0))

        # Sammendrag — annen tekst per dtype
        s = self._result.summary
        if self._dtype == "hb":
            summary_text = (
                f"Nye bilag: {s.get('nye_bilag', 0)}  ·  "
                f"Fjernede: {s.get('fjernede_bilag', 0)}  ·  "
                f"Endrede: {s.get('endrede_bilag', 0)}  ·  "
                f"Uendrede: {s.get('uendrede_bilag', 0)}  ·  "
                f"Totalt A: {s.get('bilag_a_total', 0)}  →  B: {s.get('bilag_b_total', 0)}"
            )
        else:  # sb
            sum_a = s.get("sum_ub_a", 0.0) or 0.0
            sum_b = s.get("sum_ub_b", 0.0) or 0.0
            summary_text = (
                f"Nye konti: {s.get('nye_konti', 0)}  ·  "
                f"Fjernede: {s.get('fjernede_konti', 0)}  ·  "
                f"Endrede saldoer: {s.get('endrede_konti', 0)}  ·  "
                f"Uendrede: {s.get('uendrede_konti', 0)}  ·  "
                f"Sum UB A: {sum_a:,.0f}".replace(",", " ")
                + f"  →  B: {sum_b:,.0f}".replace(",", " ")
            )
        ttk.Label(frm, text=summary_text, foreground="#666").pack(anchor="w", pady=(4, 10))
        ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=(0, 10))

        # Notebook med faner per kategori
        nb = ttk.Notebook(frm)
        nb.pack(fill="both", expand=True)

        added = self._result.added
        removed = self._result.removed
        changed = self._result.changed

        if self._dtype == "hb":
            self._add_df_tab(nb, "Nye bilag", added, int(s.get("nye_bilag", 0) or 0))
            self._add_df_tab(nb, "Fjernede bilag", removed, int(s.get("fjernede_bilag", 0) or 0))
            self._add_hb_changed_tab(nb, "Endrede bilag", changed, int(s.get("endrede_bilag", 0) or 0))
        else:  # sb
            sb_cols = ("konto", "kontonavn", "ib", "ub")
            self._add_df_tab(nb, "Nye konti", added, int(s.get("nye_konti", 0) or 0), cols_override=sb_cols)
            self._add_df_tab(nb, "Fjernede konti", removed, int(s.get("fjernede_konti", 0) or 0), cols_override=sb_cols)
            self._add_sb_changed_tab(nb, "Endrede saldoer", changed, int(s.get("endrede_konti", 0) or 0))

        # Bunn-rad: Eksporter til Excel + Lukk
        btn_row = ttk.Frame(frm)
        btn_row.pack(fill="x", pady=(10, 0))
        ttk.Button(btn_row, text="Lukk", command=self._on_close).pack(side="right")
        ttk.Button(
            btn_row, text="Eksporter til Excel…",
            command=self._on_export,
        ).pack(side="right", padx=(0, 8))

        self.top.wait_window(self.top)

    def _add_df_tab(self, nb: ttk.Notebook, title: str, df, count: int,
                     *, cols_override: tuple[str, ...] | None = None) -> None:
        """Bygg en fane som lister rader fra et DataFrame."""
        tab = ttk.Frame(nb, padding=(2, 6, 2, 2))
        nb.add(tab, text=f"{title} ({count})")

        if df is None or df.empty:
            ttk.Label(tab, text=f"Ingen {title.lower()}.", foreground="#888").pack(
                padx=12, pady=12, anchor="w",
            )
            return

        # Kolonner: enten override (SB) eller HB-default
        if cols_override is not None:
            cols = list(cols_override)
            headers = {"konto": "Konto", "kontonavn": "Kontonavn",
                        "ib": "IB", "ub": "UB"}
            widths = {"konto": 100, "kontonavn": 280, "ib": 120, "ub": 120}
            amount_cols = {"ib", "ub"}
        else:
            candidate_cols = ["Bilag", "Dato", "Konto", "Kontonavn", "Tekst", "Beløp"]
            cols = [c for c in candidate_cols if c in df.columns]
            if not cols:
                cols = list(df.columns[:6])
            headers = {c: c for c in cols}
            widths = {"Bilag": 80, "Dato": 90, "Konto": 70, "Kontonavn": 200,
                      "Tekst": 280, "Beløp": 120}
            amount_cols = {"Beløp"}

        list_frame = ttk.Frame(tab)
        list_frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(list_frame, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            tree.heading(c, text=headers.get(c, c))
            tree.column(c, width=widths.get(c, 120),
                        anchor=("e" if c in amount_cols else "w"))
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Begrens til de første 1000 radene for ytelse — eksporten har alle.
        max_rows = 1000
        for _, row in df.head(max_rows).iterrows():
            values = []
            for c in cols:
                val = row.get(c, "")
                if c in amount_cols:
                    try:
                        values.append(f"{float(val):,.2f}".replace(",", " ").replace(".", ","))
                    except Exception:
                        values.append(str(val))
                else:
                    values.append("" if val is None else str(val))
            tree.insert("", "end", values=values)

        if len(df) > max_rows:
            ttk.Label(
                tab,
                text=f"Viser {max_rows} av {len(df)} rader. Eksporter for full liste.",
                foreground="#888",
            ).pack(anchor="w", padx=4, pady=(4, 0))

    def _add_hb_changed_tab(self, nb: ttk.Notebook, title: str, changed_df, count: int) -> None:
        """Egen visning for endrede bilag — viser sum/linjer i begge versjoner."""
        tab = ttk.Frame(nb, padding=(2, 6, 2, 2))
        nb.add(tab, text=f"{title} ({count})")

        if changed_df is None or changed_df.empty:
            ttk.Label(tab, text="Ingen endrede bilag.", foreground="#888").pack(
                padx=12, pady=12, anchor="w",
            )
            return

        cols = ("bilag", "sum_a", "sum_b", "diff_sum", "linjer_a", "linjer_b", "diff_linjer")
        list_frame = ttk.Frame(tab)
        list_frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(list_frame, columns=cols, show="headings", selectmode="browse")
        for c, h, w, anchor in [
            ("bilag", "Bilag", 90, "w"),
            ("sum_a", "Sum A", 120, "e"),
            ("sum_b", "Sum B", 120, "e"),
            ("diff_sum", "Diff sum", 120, "e"),
            ("linjer_a", "Linjer A", 80, "e"),
            ("linjer_b", "Linjer B", 80, "e"),
            ("diff_linjer", "Diff linjer", 80, "e"),
        ]:
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor=anchor)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _fmt(num) -> str:
            try:
                return f"{float(num):,.2f}".replace(",", " ").replace(".", ",")
            except Exception:
                return str(num)

        for _, row in changed_df.iterrows():
            tree.insert("", "end", values=(
                row.get("bilag", ""),
                _fmt(row.get("sum_a", 0)),
                _fmt(row.get("sum_b", 0)),
                _fmt(row.get("diff_sum", 0)),
                int(row.get("linjer_a", 0) or 0),
                int(row.get("linjer_b", 0) or 0),
                int(row.get("diff_linjer", 0) or 0),
            ))

    def _add_sb_changed_tab(self, nb: ttk.Notebook, title: str, changed_df, count: int) -> None:
        """Visning for endrede saldoer — IB og UB i begge versjoner."""
        tab = ttk.Frame(nb, padding=(2, 6, 2, 2))
        nb.add(tab, text=f"{title} ({count})")

        if changed_df is None or changed_df.empty:
            ttk.Label(tab, text="Ingen endrede saldoer.", foreground="#888").pack(
                padx=12, pady=12, anchor="w",
            )
            return

        cols = ("konto", "kontonavn", "ib_a", "ib_b", "diff_ib", "ub_a", "ub_b", "diff_ub")
        list_frame = ttk.Frame(tab)
        list_frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(list_frame, columns=cols, show="headings", selectmode="browse")
        for c, h, w, anchor in [
            ("konto", "Konto", 90, "w"),
            ("kontonavn", "Kontonavn", 240, "w"),
            ("ib_a", "IB A", 110, "e"),
            ("ib_b", "IB B", 110, "e"),
            ("diff_ib", "Diff IB", 100, "e"),
            ("ub_a", "UB A", 110, "e"),
            ("ub_b", "UB B", 110, "e"),
            ("diff_ub", "Diff UB", 100, "e"),
        ]:
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor=anchor)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _fmt(num) -> str:
            try:
                return f"{float(num):,.2f}".replace(",", " ").replace(".", ",")
            except Exception:
                return str(num)

        for _, row in changed_df.iterrows():
            tree.insert("", "end", values=(
                row.get("konto", ""),
                row.get("kontonavn", ""),
                _fmt(row.get("ib_a", 0)),
                _fmt(row.get("ib_b", 0)),
                _fmt(row.get("diff_ib", 0)),
                _fmt(row.get("ub_a", 0)),
                _fmt(row.get("ub_b", 0)),
                _fmt(row.get("diff_ub", 0)),
            ))

    def _on_export(self) -> None:
        """Eksporter diff-resultatet til Excel — riktig modul per dtype."""
        if self._dtype == "hb":
            module_name = "hb_version_diff_excel"
            builder_name = "build_hb_diff_workpaper"
            title = "Eksporter HB versjonsdiff"
            base_name = "HB_Versjonsdiff"
        else:  # sb
            module_name = "sb_version_diff_excel"
            builder_name = "build_sb_diff_workpaper"
            title = "Eksporter SB versjonsdiff"
            base_name = "SB_Versjonsdiff"

        try:
            module = __import__(module_name)
            builder = getattr(module, builder_name)
        except Exception as exc:
            messagebox.showerror("Eksport", f"Eksport-modul mangler: {exc}", parent=self.top)
            return

        safe_client = "".join(
            ch if ch.isalnum() or ch in {" ", "_", "-"} else "_"
            for ch in str(self._client)
        ).strip()
        base = f"{base_name} {safe_client} {self._year}".strip()
        path = filedialog.asksaveasfilename(
            parent=self.top,
            title=title,
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
            initialfile=base + ".xlsx",
        )
        if not path:
            return
        try:
            wb = builder(
                self._result,
                client=self._client,
                year=self._year,
                version_a_label=self._a_label,
                version_b_label=self._b_label,
            )
            wb.save(path)
        except Exception as exc:
            _log.exception("Failed to save %s diff workpaper", self._dtype.upper())
            messagebox.showerror(
                "Eksport", f"Kunne ikke lagre: {exc}", parent=self.top,
            )
            return
        messagebox.showinfo("Eksport", f"Lagret: {path}", parent=self.top)
        try:
            _open_path(Path(path))
        except Exception:
            pass

    def _on_close(self) -> None:
        if self.top is not None:
            try:
                self.top.destroy()
            except Exception:
                pass


@dataclass
class _DialogState:
    client: str
    year: int
    dtype: str


class _VersionsDialog:
    def __init__(
        self,
        parent: tk.Misc,
        state: _DialogState,
        current_path_getter,
        on_use_version=None,
        on_use_sb_version=None,
        on_after_change=None,
        on_export_hb=None,
        dtypes: list[str] | None = None,
    ):
        self._parent = parent
        self._state = state
        self._current_path_getter = current_path_getter
        self._on_use_version = on_use_version
        self._on_use_sb_version = on_use_sb_version
        self._on_after_change = on_after_change
        # Callback som trigger HB-eksport (selve eksport-logikken bor i
        # DatasetPage som vet om _last_df, filvelger, async-kjøring).
        self._on_export_hb = on_export_hb

        self._dtypes = list(dict.fromkeys(dtypes or [state.dtype]))

        # We keep versions per dtype so we can show a summary.
        self._versions_by_dtype: dict[str, dict[str, object]] = {}
        # Sporing av hvilke dtypes som har fått treet rendret. Brukes til
        # lazy-load slik at vi unngår å iterere over alle dtypes ved oppstart.
        self._loaded_dtypes: set[str] = set()

        self.top: tk.Toplevel | None = None
        self.lbl_title: ttk.Label | None = None
        self.lbl_summary: ttk.Label | None = None
        self.nb: ttk.Notebook | None = None
        self.trees: dict[str, ttk.Treeview] = {}

        # Buttons — slankere sett etter rydding:
        # - "Ny versjon fra filfelt" fjernet (Importer fil… dekker samme behov).
        # - "Bruk valgt" fjernet (dobbeltklikk eller Enter velger versjonen).
        # - "Markert: X rad" fjernet (overflødig støy).
        # - "Lag saldobalanse fra SAF-T" fjernet (SB auto-genereres ved
        #   SAF-T-import; re-generering er edge-case).
        self.btn_import: ttk.Button | None = None
        self.btn_open_file: ttk.Button | None = None
        self.btn_open_folder: ttk.Button | None = None
        self.btn_delete: ttk.Button | None = None
        self.btn_export: ttk.Button | None = None
        self.btn_compare: ttk.Button | None = None

        self.lbl_hint: ttk.Label | None = None

    # ------------------------- lifecycle -------------------------
    def show_modal(self):
        self.top = tk.Toplevel(self._parent)
        self.top.title("Versjoner")
        # Modal grab uten transient: gir standard window-controls
        # (minimer / maksimer / lukk) som er fjernet hvis transient brukes.
        self.top.grab_set()

        # Adaptiv start-størrelse: 65 % bredde / 70 % høyde, klemt mellom
        # min/max så popupen ser bra ut på både laptop og stor skjerm.
        try:
            sw = self.top.winfo_screenwidth()
            sh = self.top.winfo_screenheight()
            win_w = max(960, min(int(sw * 0.65), 1300))
            win_h = max(560, min(int(sh * 0.70), 800))
            x = max(0, (sw - win_w) // 2)
            y = max(0, (sh - win_h) // 3)
            self.top.geometry(f"{win_w}x{win_h}+{x}+{y}")
            self.top.minsize(900, 500)
        except Exception:
            try:
                self.top.geometry("980x520")
            except Exception:
                pass

        self._build_ui(self.top)

        # Initial tab — SAF-T-fanen er nå indeks 0, dtypes følger fra
        # indeks 1 og oppover.
        if self.nb is not None:
            try:
                if self._state.dtype == "saft":
                    self.nb.select(0)  # SAF-T-fanen
                elif self._state.dtype in self._dtypes:
                    self.nb.select(self._dtypes.index(self._state.dtype) + 1)
            except Exception:
                pass

        # Lazy-load: kun aktiv tab rendres nå. Andre rendres ved tab-bytte.
        # Header-summary får data fra alle dtypes likevel (lett kall).
        self._reload_initial()
        # Hvis SAF-T-fanen er aktiv ved oppstart, last SAF-T-listen også.
        if self._current_dtype() == "saft":
            self._reload_saft()
        self._loaded_dtypes = {self._current_dtype()}
        self._update_buttons_and_hint()

        self.top.wait_window(self.top)

    # ------------------------- UI -------------------------
    def _build_ui(self, parent: tk.Misc) -> None:
        frm = ttk.Frame(parent, padding=(14, 12, 14, 12))
        frm.pack(fill="both", expand=True)

        # Header-card: tittel + klient/år, med diskret bunnramme.
        header = ttk.Frame(frm)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(
            header, text="Versjoner",
            font=("Segoe UI", 16, "bold"), foreground="#1a4c7a",
        ).pack(anchor="w")
        self.lbl_title = ttk.Label(
            header, text="",
            font=("Segoe UI", 10), foreground="#444",
        )
        self.lbl_title.pack(anchor="w", pady=(2, 0))
        # Sub-summary med versjonsstatus per dtype
        self.lbl_summary = ttk.Label(
            header, text="",
            font=("Segoe UI", 9), foreground="#666",
        )
        self.lbl_summary.pack(anchor="w", pady=(4, 0))

        ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=(0, 10))

        # Action-rad — gruppert etter formål:
        #   [Skape: Importer <dtype>-fil…]   — label endres per fane
        #   [Lese:  Åpne fil | Åpne mappe]
        #   [Eksport: Eksporter til Excel]   — kun aktiv på HB-fanen
        #   [Destruktiv: Slett versjon] — separert til høyre
        frm_btns = ttk.Frame(frm)
        frm_btns.pack(fill="x", pady=(0, 8))

        # Importer-knappen får dynamisk label per fane (oppdateres i
        # _update_buttons_and_hint). Default-label: "Importer fil…".
        self.btn_import = ttk.Button(
            frm_btns, text="Importer fil…", command=self._on_import_file,
        )
        self.btn_import.pack(side="left")

        # Skille mellom skape og lese
        ttk.Separator(frm_btns, orient="vertical").pack(side="left", fill="y", padx=12, pady=2)

        self.btn_open_file = ttk.Button(frm_btns, text="Åpne fil", command=self._on_open_file)
        self.btn_open_file.pack(side="left")

        self.btn_open_folder = ttk.Button(frm_btns, text="Åpne mappe", command=self._on_open_folder)
        self.btn_open_folder.pack(side="left", padx=(6, 0))

        # Eksport — kun aktiv på HB-fanen og kun hvis callback er satt.
        # Trigger DatasetPage's eksport-flyt (filvelger + async-eksport).
        self.btn_export = ttk.Button(
            frm_btns, text="Eksporter til Excel…", command=self._on_export_clicked,
        )
        self.btn_export.pack(side="left", padx=(6, 0))

        # Sammenlign HB-versjoner: kun aktiv på HB-fanen når ≥2 versjoner finnes.
        self.btn_compare = ttk.Button(
            frm_btns, text="Sammenlign…", command=self._on_compare_clicked,
        )
        self.btn_compare.pack(side="left", padx=(6, 0))

        # Destruktiv handling i høyre side, klart adskilt
        self.btn_delete = ttk.Button(frm_btns, text="Slett versjon", command=self._on_delete)
        self.btn_delete.pack(side="right")

        # Notebook: SAF-T-fanen FØRST (kilden), deretter dtype-fanene.
        # Rekkefølgen matcher pillene på Datasett-fanen: SAF-T | HB | SB | KR | LR.
        self.nb = ttk.Notebook(frm)
        self.nb.pack(fill="both", expand=True, pady=(2, 0))
        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self._on_tab_changed())

        # SAF-T-fane først — én SAF-T-fil inneholder data for alle dtypes.
        self._saft_tab = ttk.Frame(self.nb, padding=(2, 6, 2, 2))
        self.nb.add(self._saft_tab, text="SAF-T")
        self._build_saft_tab(self._saft_tab)

        for dtype in self._dtypes:
            tab = ttk.Frame(self.nb, padding=(2, 6, 2, 2))
            self.nb.add(tab, text=_dtype_label(dtype))
            tree = self._make_tree(tab, dtype)
            self.trees[dtype] = tree

        # Footer — kun hint + Lukk-knapp. "Bruk valgt" er fjernet siden
        # dobbeltklikk eller Enter på en rad gjør samme.
        frm_footer = ttk.Frame(frm)
        frm_footer.pack(fill="x", pady=(6, 0))

        self.lbl_hint = ttk.Label(frm_footer, text="", justify="left", foreground="#666")
        self.lbl_hint.pack(side="left", anchor="w")

        ttk.Button(frm_footer, text="Lukk", command=self._on_close).pack(side="right")

    def _make_tree(self, parent: tk.Misc, dtype: str) -> ttk.Treeview:
        frm_list = ttk.Frame(parent)
        frm_list.pack(fill="both", expand=True)

        # Kolonner: Aktiv, Fil, Type, Størrelse, Opprettet — gir mer info
        # for å skille versjoner uten å åpne fila.
        cols = ("active", "file", "type", "size", "created")
        tree = ttk.Treeview(frm_list, columns=cols, show="headings", selectmode="browse")
        tree.heading("active", text="Aktiv")
        tree.heading("file", text="Fil")
        tree.heading("type", text="Type")
        tree.heading("size", text="Størrelse")
        tree.heading("created", text="Opprettet")

        tree.column("active", width=60, anchor="center", stretch=False)
        tree.column("file", width=460, anchor="w", stretch=True)
        tree.column("type", width=80, anchor="center", stretch=False)
        tree.column("size", width=90, anchor="e", stretch=False)
        tree.column("created", width=150, anchor="w", stretch=False)

        # Tag-styling: aktiv versjon får grønn bakgrunn så den fanges
        # umiddelbart. Bytter "*"-tegnet med "✓" for tydelighet.
        try:
            tree.tag_configure("active_row", background="#E8F5E9")
        except Exception:
            pass

        # Klikk-sortering på Fil/Type/Opprettet via standard sortering-helper.
        try:
            from src.shared.ui.treeview_sort import enable_treeview_sorting
            enable_treeview_sorting(tree, columns=("file", "type", "size", "created"))
        except Exception:
            pass

        vsb = ttk.Scrollbar(frm_list, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)

        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        tree.bind("<Double-1>", lambda _e: self._on_use_and_close())
        tree.bind("<Return>", lambda _e: self._on_use_and_close())
        tree.bind("<<TreeviewSelect>>", lambda _e: self._update_buttons_and_hint())

        return tree

    # ------------------------- SAF-T-fane -------------------------
    def _build_saft_tab(self, parent: tk.Widget) -> None:
        """Oversiktsliste over SAF-T-filer (HB-versjoner med .zip/.xml).

        Brukerverdi: én SAF-T-fil inneholder data for alle 4 dtypes (HB,
        SB, KR, LR). Denne fanen samler kildene slik at man ser hvilke
        SAF-T-filer som er importert, og kan re-ekstrahere SB/KR/LR
        derfra ved behov (re-extract kommer i senere runde).
        """
        ttk.Label(
            parent,
            text="SAF-T-kilder",
            font=("Segoe UI", 11, "bold"), foreground="#1a4c7a",
        ).pack(anchor="w", padx=2, pady=(0, 4))
        ttk.Label(
            parent,
            text=("Én SAF-T-fil inneholder data for alle dtypes (HB, SB, KR, LR). "
                  "Denne listen viser SAF-T-filer som er lagret som hovedbok-versjoner."),
            foreground="#666", wraplength=900,
        ).pack(anchor="w", padx=2, pady=(0, 8))

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="both", expand=True)

        cols = ("active", "file", "size", "created")
        tree = ttk.Treeview(list_frame, columns=cols, show="headings", selectmode="browse")
        tree.heading("active", text="Aktiv som HB")
        tree.heading("file", text="SAF-T-fil")
        tree.heading("size", text="Størrelse")
        tree.heading("created", text="Importert")
        tree.column("active", width=110, anchor="center", stretch=False)
        tree.column("file", width=520, anchor="w", stretch=True)
        tree.column("size", width=90, anchor="e", stretch=False)
        tree.column("created", width=150, anchor="w", stretch=False)

        try:
            tree.tag_configure("active_row", background="#E8F5E9")
        except Exception:
            pass

        try:
            from src.shared.ui.treeview_sort import enable_treeview_sorting
            enable_treeview_sorting(tree, columns=("file", "size", "created"))
        except Exception:
            pass

        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Tom-tilstand: vises kun når listen er tom.
        self._saft_empty_lbl = ttk.Label(
            parent,
            text="Ingen SAF-T-filer importert ennå. Importer en SAF-T-fil "
                 "(.zip eller .xml) under Hovedbok-fanen.",
            foreground="#888",
        )

        self._saft_tree = tree

    def _reload_saft(self) -> None:
        """Fyll SAF-T-fanen fra HB-versjoner med .zip/.xml-suffix."""
        tree = getattr(self, "_saft_tree", None)
        if tree is None:
            return

        try:
            hb_versions = client_store.list_versions(
                self._state.client, year=self._state.year, dtype="hb",
            )
        except Exception:
            hb_versions = []

        try:
            active_hb = _get_active_version_id(
                self._state.client, year=self._state.year, dtype="hb",
            )
        except Exception:
            active_hb = None

        # Filtrer på .zip/.xml — det er disse som regnes som SAF-T-kilder.
        saft_versions = [
            v for v in hb_versions
            if Path(v.path).suffix.lower() in {".zip", ".xml"}
        ]

        for item in tree.get_children():
            tree.delete(item)

        for v in sorted(saft_versions, key=_version_created_ts, reverse=True):
            is_active = bool(active_hb and v.id == active_hb)
            mark = "✓" if is_active else ""
            file_path = Path(v.path)
            try:
                size = _fmt_size(file_path.stat().st_size)
            except Exception:
                size = "—"
            tags = ("active_row",) if is_active else ()
            tree.insert(
                "", "end", iid=v.id,
                values=(mark, file_path.name, size, _fmt_ts(_version_created_ts(v))),
                tags=tags,
            )

        # Vis tom-tilstand-tekst hvis ingen rader
        if saft_versions:
            try:
                self._saft_empty_lbl.pack_forget()
            except Exception:
                pass
        else:
            try:
                self._saft_empty_lbl.pack(anchor="w", padx=2, pady=(8, 0))
            except Exception:
                pass

    # ------------------------- state helpers -------------------------
    def _current_dtype(self) -> str:
        """Map notebook-indeks til dtype.

        Indeks 0 = SAF-T-fanen (returnerer "saft").
        Indeks 1+ = dtype-fanene (HB, SB, KR, LR i den rekkefølgen som
        ble registrert).
        """
        if self.nb is None:
            return self._state.dtype
        try:
            idx = self.nb.index(self.nb.select())
            if idx == 0:
                return "saft"  # SAF-T-fanen er nå første
            dtype = self._dtypes[idx - 1]  # offset med 1 for SAF-T-fanen
            self._state.dtype = dtype
            return dtype
        except Exception:
            return self._state.dtype

    def _current_tree(self) -> ttk.Treeview | None:
        return self.trees.get(self._current_dtype())

    def _get_selected_version_id(self, dtype: str | None = None) -> str | None:
        dtype = dtype or self._current_dtype()
        tree = self.trees.get(dtype)
        if tree is None:
            return None
        sel = tree.selection()
        return sel[0] if sel else None

    def _get_version_info(self, dtype: str, version_id: str):
        # VersionInfo is an internal project type; keep it opaque.
        return client_store.get_version(self._state.client, year=self._state.year, dtype=dtype, version_id=version_id)

    # ------------------------- reload -------------------------
    def _reload_all(self, *, focus_dtype: str | None = None, select_id: str | None = None) -> None:
        """Last alle dtypes på en gang. Brukes etter mutasjoner (importer/slett)
        slik at header-summary er korrekt på tvers.

        Ved første visning bruker vi i stedet :py:meth:`_reload_initial` for
        å laste kun aktiv tab + ha summary-info klar i bakgrunn.
        """
        for dt in self._dtypes:
            self._reload_dtype(dt, select_id=select_id if dt == (focus_dtype or self._current_dtype()) else None)
            self._loaded_dtypes.add(dt)
        self._update_header_summary()

    def _reload_initial(self) -> None:
        """Lazy-load: render kun aktiv tab nå, last andre når brukeren klikker.

        Header-summary trenger likevel data fra alle dtypes (for å vise
        "HB: N | SB: M"). Vi henter list_versions for ikke-aktive dtypes
        kun for summary, uten å rendre treet — det skjer ved tab-bytte.
        """
        active_dtype = self._current_dtype()
        for dt in self._dtypes:
            if dt == active_dtype:
                self._reload_dtype(dt)
            else:
                # Kun fyll _versions_by_dtype for summary; tre rendres senere.
                try:
                    versions = client_store.list_versions(
                        self._state.client, year=self._state.year, dtype=dt,
                    )
                except Exception:
                    versions = []
                self._versions_by_dtype[dt] = {v.id: v for v in versions}
        self._update_header_summary()

    def _reload_dtype(self, dtype: str, select_id: str | None = None) -> None:
        tree = self.trees.get(dtype)
        if tree is None:
            return

        # Keep versions dict per dtype for summary/lookup
        try:
            versions = client_store.list_versions(self._state.client, year=self._state.year, dtype=dtype)
        except Exception:
            versions = []

        versions_by_id = {v.id: v for v in versions}
        self._versions_by_dtype[dtype] = versions_by_id

        active_id = _get_active_version_id(self._state.client, year=self._state.year, dtype=dtype)

        # Clear
        for item in tree.get_children():
            tree.delete(item)

        # Insert — ✓ med farget bakgrunn på aktiv rad. Type/Størrelse hentes
        # fra fila hvis den finnes (ellers tom + grå).
        for v in sorted(versions, key=_version_created_ts, reverse=True):
            is_active = bool(active_id and v.id == active_id)
            mark = "✓" if is_active else ""
            file_path = Path(v.path)
            file_type = file_path.suffix.lstrip(".").upper() or "—"
            try:
                size_bytes = file_path.stat().st_size
                size_str = _fmt_size(size_bytes)
            except Exception:
                size_str = "—"
            tags = ("active_row",) if is_active else ()
            tree.insert(
                "", "end", iid=v.id,
                values=(mark, file_path.name, file_type, size_str, _fmt_ts(_version_created_ts(v))),
                tags=tags,
            )

        # KR/LR: hvis ingen egne versjoner finnes, fall tilbake til SAF-T-
        # filer (HB-versjoner med .zip/.xml-suffix). Én SAF-T-fil inneholder
        # data for alle 4 dtypes, så det er meningsfullt å vise SAF-T-fila
        # som "kilden" til KR/LR helt til en egen ekstrahering kommer.
        if dtype in {"kr", "lr"} and not versions:
            self._insert_saft_fallback_rows(tree, dtype)

        # Select
        preferred = select_id or active_id
        if preferred and preferred in versions_by_id:
            try:
                tree.selection_set(preferred)
                tree.see(preferred)
            except Exception:
                pass

    def _insert_saft_fallback_rows(self, tree: ttk.Treeview, dtype: str) -> None:
        """Vis SAF-T-filer som virtuelle KR/LR-versjoner.

        Markeres med Type=SAF-T og iid=saft:<hb_version_id> så de ikke
        kolliderer med ekte KR/LR-versjoner senere. Aktiv-pillen følger
        aktiv HB-versjon (det er der SAF-T-data ekstraheres fra).
        """
        try:
            hb_versions = client_store.list_versions(
                self._state.client, year=self._state.year, dtype="hb",
            )
        except Exception:
            hb_versions = []
        try:
            active_hb = _get_active_version_id(
                self._state.client, year=self._state.year, dtype="hb",
            )
        except Exception:
            active_hb = None

        saft_versions = [
            v for v in hb_versions
            if Path(v.path).suffix.lower() in {".zip", ".xml"}
        ]
        for v in sorted(saft_versions, key=_version_created_ts, reverse=True):
            is_active = bool(active_hb and v.id == active_hb)
            mark = "✓" if is_active else ""
            file_path = Path(v.path)
            try:
                size = _fmt_size(file_path.stat().st_size)
            except Exception:
                size = "—"
            tags = ("active_row",) if is_active else ()
            tree.insert(
                "", "end", iid=f"saft:{v.id}",
                values=(
                    mark,
                    f"{file_path.name}  (fra SAF-T)",
                    "SAF-T",
                    size,
                    _fmt_ts(_version_created_ts(v)),
                ),
                tags=tags,
            )

    def _update_header_summary(self) -> None:
        if self.lbl_title is None or self.lbl_summary is None:
            return

        self.lbl_title.config(
            text=f"{self._state.client}  ·  {self._state.year}",
        )

        # Sjekk SAF-T-fallback én gang for hele rekken — KR/LR uten egne
        # versjoner får data fra SAF-T-fila.
        try:
            hb_versions = client_store.list_versions(
                self._state.client, year=self._state.year, dtype="hb",
            )
            has_saft = any(
                Path(v.path).suffix.lower() in {".zip", ".xml"}
                for v in hb_versions
            )
        except Exception:
            has_saft = False

        # Kompakt status-pille per dtype: "HB: 3 ✓ · SB: 1 ✓ · KR: 0 (SAF-T) · LR: 0"
        # ✓ markerer at en versjon er aktiv. KR/LR med SAF-T-fallback får
        # "(SAF-T)" suffix så det er tydelig hvor dataene kommer fra.
        parts: list[str] = []
        short_labels = {"hb": "HB", "sb": "SB", "kr": "KR", "lr": "LR"}
        for dt in self._dtypes:
            versions = self._versions_by_dtype.get(dt, {})
            active_id = _get_active_version_id(
                self._state.client, year=self._state.year, dtype=dt,
            )
            short = short_labels.get(dt, _dtype_label(dt))
            count = len(versions)
            mark = " ✓" if (count > 0 and active_id in versions) else ""
            label = f"{short}: {count}{mark}"
            if dt in {"kr", "lr"} and count == 0 and has_saft:
                label += " (SAF-T)"
            parts.append(label)

        self.lbl_summary.config(text="  ·  ".join(parts))

    # ------------------------- buttons & hint -------------------------
    _IMPORT_LABELS: dict[str, str] = {
        "saft": "Importer SAF-T-fil…",
        "hb":   "Importer HB-fil…",
        "sb":   "Importer SB-fil…",
        "kr":   "Importer KR-fil…",
        "lr":   "Importer LR-fil…",
    }

    def _update_buttons_and_hint(self) -> None:
        dtype = self._current_dtype()

        # Dynamisk label på import-knappen så det er tydelig hva som
        # importeres når brukeren bytter fane.
        if self.btn_import is not None:
            self.btn_import.config(
                text=self._IMPORT_LABELS.get(dtype, "Importer fil…"),
            )

        # SAF-T-fanen er en oversiktsvisning — Åpne fil/mappe, Slett,
        # Eksport og Sammenlign gjelder dtype-versjoner, så de disables her.
        if dtype == "saft":
            for btn in (self.btn_open_file, self.btn_open_folder, self.btn_delete,
                        self.btn_export, self.btn_compare):
                if btn is not None:
                    btn.config(state="disabled")
            if self.lbl_hint is not None:
                self.lbl_hint.config(
                    text="SAF-T-kilder. Importer ny SAF-T-fil med knappen over.",
                )
            return

        selected_id = self._get_selected_version_id(dtype)
        is_saft_fallback = bool(selected_id and selected_id.startswith("saft:"))

        # Enable/disable kontekstuelle knapper. SAF-T-fallback-rader (på
        # KR/LR-fanen) er virtuelle — Åpne fil/mappe virker (peker til
        # SAF-T-fila), men Slett versjon må disables for å unngå at
        # brukeren sletter HB-versjonen via KR/LR-fanen ved et uhell.
        for btn in (self.btn_open_file, self.btn_open_folder):
            if btn is not None:
                btn.config(state=("normal" if selected_id else "disabled"))
        if self.btn_delete is not None:
            self.btn_delete.config(
                state=("normal" if (selected_id and not is_saft_fallback) else "disabled"),
            )

        # Eksport: kun aktiv på HB-fanen, og kun når en callback er satt.
        # Selve eksporten bruker det aktive datasettet i hovedappen, så
        # det er ikke knyttet til radvalg i popupen.
        if self.btn_export is not None:
            can_export = bool(dtype == "hb" and self._on_export_hb is not None)
            self.btn_export.config(state=("normal" if can_export else "disabled"))

        # Sammenlign: aktiv på HB- og SB-fanen når det finnes ≥2 versjoner.
        if self.btn_compare is not None:
            count = len(self._versions_by_dtype.get(dtype, {}))
            can_compare = bool(dtype in {"hb", "sb"} and count >= 2)
            self.btn_compare.config(state=("normal" if can_compare else "disabled"))

        # Hint — kontekstuell. SAF-T-fallback har egen melding siden den
        # ikke kan "brukes" på samme måte som en native versjon.
        if self.lbl_hint is not None:
            if is_saft_fallback:
                self.lbl_hint.config(
                    text="SAF-T-kilde inneholder denne datatypen. "
                         "Native ekstrahering kommer senere.",
                )
            else:
                self.lbl_hint.config(
                    text="Dobbeltklikk eller Enter for å bruke valgt versjon.",
                )

    # ------------------------- events -------------------------
    def _on_tab_changed(self) -> None:
        dtype = self._current_dtype()  # updates state
        # Lazy-render: trefylles første gang brukeren bytter til en ny tab.
        loaded = getattr(self, "_loaded_dtypes", None)
        if dtype == "saft":
            # SAF-T-fanen leses fra HB-versjonene — fyll alltid på nytt
            # i tilfelle bruker har importert nye SAF-T-filer i mellomtiden.
            self._reload_saft()
        elif loaded is not None and dtype not in loaded:
            self._reload_dtype(dtype)
            loaded.add(dtype)
        self._update_buttons_and_hint()

    def _after_change(self) -> None:
        if self._on_after_change:
            try:
                self._on_after_change()
            except Exception:
                _log.exception("on_after_change failed")

    # ------------------------- actions -------------------------
    def _on_import_file(self) -> None:
        dtype = self._current_dtype()

        # File filters per fane
        excel = ("Excel-filer", "*.xlsx *.xls *.xlsm")
        csv = ("CSV", "*.csv")
        saft = ("SAF-T", "*.zip *.xml")
        allf = ("Alle filer", "*.*")

        # Tittel + filtype-utvalg per fane
        if dtype == "saft":
            title = "Velg SAF-T-fil"
            ftypes = [saft, allf]
        elif dtype == "hb":
            title = "Velg hovedbok-fil"
            ftypes = [excel, csv, saft, allf]
        elif dtype == "sb":
            title = "Velg saldobalanse-fil"
            ftypes = [excel, csv, saft, allf]
        elif dtype == "kr":
            title = "Velg kundereskontro-fil"
            ftypes = [excel, csv, allf]
        elif dtype == "lr":
            title = "Velg leverandørreskontro-fil"
            ftypes = [excel, csv, allf]
        else:
            title = "Velg fil"
            ftypes = [allf]

        src = filedialog.askopenfilename(title=title, filetypes=ftypes)
        if not src:
            return

        src_path = Path(src)

        # SAF-T-import: lagres som HB-versjon (én SAF-T-fil = HB+SB+KR+LR-kilde).
        # SB auto-genereres fra SAF-T-en. Dette gjelder både SAF-T-fanen og
        # HB-fanen når brukeren velger en .zip/.xml-fil.
        is_saft_file = src_path.suffix.lower() in {".zip", ".xml"}
        if dtype == "saft" or (dtype == "hb" and is_saft_file):
            try:
                v = client_store.create_version(
                    self._state.client,
                    year=self._state.year,
                    dtype="hb",
                    src_path=src_path,
                    make_active=True,
                )
            except Exception:
                _log.exception("Failed to create SAF-T version")
                messagebox.showerror(
                    "Versjoner", "Kunne ikke importere SAF-T-fila.", parent=self.top,
                )
                return
            # Auto-generer SB fra SAF-T-en
            self._auto_create_sb_from_saft(src_path)
            self._reload_all(focus_dtype="hb", select_id=v.id)
            self._after_change()
            return

        # SB-fra-SAF-T: tilsvarer å importere SAF-T og generere SB fra den.
        if dtype == "sb" and is_saft_file:
            sb_id = self._import_sb_from_saft(src_path, make_active=True)
            if sb_id:
                self._reload_all(focus_dtype="sb", select_id=sb_id)
                if self.nb is not None and "sb" in self._dtypes:
                    try:
                        # SAF-T-fanen er på indeks 0, SB-fanen er på
                        # _dtypes.index("sb") + 1.
                        self.nb.select(self._dtypes.index("sb") + 1)
                    except Exception:
                        pass
                self._after_change()
            return

        # Vanlig import for HB/SB/KR/LR med ikke-SAF-T-fil.
        try:
            client_store.create_version(
                self._state.client,
                year=self._state.year,
                dtype=dtype,
                src_path=Path(src_path),
                make_active=True,
            )
        except Exception:
            _log.exception("Failed to create version")
            messagebox.showerror("Versjoner", "Kunne ikke importere filen.", parent=self.top)
            return

        self._reload_all(focus_dtype=dtype)
        self._after_change()

        # Reload and focus
        self._reload_all(focus_dtype=dtype, select_id=v.id)
        self._after_change()

        # Only HB updates the main dataset field
        if self._on_use_version and dtype == "hb":
            try:
                self._on_use_version(v.id)
            except Exception:
                _log.exception("on_use_version failed")

    def _resolve_path_for_action(self, dtype: str, vid: str) -> "Path | None":
        """Mappe vid til en faktisk filsti. SAF-T-fallback-rader har iid
        på formen "saft:<hb_version_id>" — slå da opp HB-versjonen.
        """
        if vid.startswith("saft:"):
            real_id = vid[len("saft:"):]
            try:
                v = self._get_version_info("hb", real_id)
                return Path(v.path)
            except Exception:
                return None
        try:
            v = self._get_version_info(dtype, vid)
            return Path(v.path)
        except Exception:
            return None

    def _on_compare_clicked(self) -> None:
        """Sammenlign to versjoner (HB eller SB) og vis diff-dialog.

        B = valgt versjon i tabellen (eller aktiv hvis ingen valgt).
        A = brukeren velger via mini-dialog blant øvrige versjoner.
        """
        dtype = self._current_dtype()
        if dtype not in {"hb", "sb"}:
            return

        # B = valgt versjon (eller aktiv for dtype)
        b_id = self._get_selected_version_id(dtype)
        if not b_id or b_id.startswith("saft:"):
            try:
                b_id = _get_active_version_id(
                    self._state.client, year=self._state.year, dtype=dtype,
                )
            except Exception:
                b_id = None
        if not b_id:
            messagebox.showinfo(
                "Sammenlign",
                "Velg en versjon i listen først, eller aktiver én via dobbeltklikk.",
                parent=self.top,
            )
            return

        versions = list(self._versions_by_dtype.get(dtype, {}).values())
        if len(versions) < 2:
            messagebox.showinfo(
                "Sammenlign",
                "Det må finnes minst to versjoner for å kunne sammenligne.",
                parent=self.top,
            )
            return

        # Plukk A — bruker velger blant øvrige versjoner
        a_id = _pick_compare_version(self.top, versions, exclude_id=b_id)
        if not a_id:
            return

        # Last begge DataFrames — flyten er litt forskjellig for HB vs SB
        a_df = _load_version_df(self._state.client, self._state.year, dtype, a_id)
        b_df = _load_version_df(self._state.client, self._state.year, dtype, b_id)
        if a_df is None or a_df.empty:
            messagebox.showerror(
                "Sammenlign",
                "Kunne ikke laste sammenlignings-versjonen.",
                parent=self.top,
            )
            return
        if b_df is None or b_df.empty:
            messagebox.showerror(
                "Sammenlign",
                "Kunne ikke laste den valgte versjonen.",
                parent=self.top,
            )
            return

        # Beregn diff (forskjellig modul per dtype)
        try:
            if dtype == "hb":
                import src.audit_actions.diff.hb_engine as hb_version_diff
                result = hb_version_diff.diff_hb_versions(a_df, b_df)
            else:  # sb
                import src.audit_actions.diff.sb_engine as sb_version_diff
                result = sb_version_diff.diff_sb_versions(a_df, b_df)
        except Exception as exc:
            _log.exception("%s diff failed", dtype.upper())
            messagebox.showerror(
                "Sammenlign",
                f"Feil ved beregning av versjonsdiff:\n\n{exc}",
                parent=self.top,
            )
            return

        # Hent versjonsnavn for label
        a_label = _label_for_version(self._state.client, self._state.year, dtype, a_id)
        b_label = _label_for_version(self._state.client, self._state.year, dtype, b_id)

        # Vis i dedikert dialog
        _VersionDiffDialog(
            self.top, result,
            client=self._state.client,
            year=self._state.year,
            dtype=dtype,
            a_label=a_label,
            b_label=b_label,
        ).show()

    def _on_export_clicked(self) -> None:
        """Trigger HB-eksport via callback. Selve flyten (filvelger,
        async-kjøring, åpne fila etterpå) bor i DatasetPage som vet om
        det aktive datasettet.
        """
        if self._on_export_hb is None:
            return
        try:
            self._on_export_hb()
        except Exception:
            _log.exception("Export HB callback failed")

    def _on_open_file(self) -> None:
        dtype = self._current_dtype()
        vid = self._get_selected_version_id(dtype)
        if not vid:
            return
        path = self._resolve_path_for_action(dtype, vid)
        if path is None:
            return
        try:
            _open_path(path)
        except Exception:
            _log.exception("Failed to open version file")

    def _on_open_folder(self) -> None:
        dtype = self._current_dtype()
        vid = self._get_selected_version_id(dtype)
        if not vid:
            return
        path = self._resolve_path_for_action(dtype, vid)
        if path is None:
            return
        try:
            _open_path(path.parent)
        except Exception:
            _log.exception("Failed to open folder")

    def _on_delete(self) -> None:
        dtype = self._current_dtype()
        vid = self._get_selected_version_id(dtype)
        if not vid:
            return

        # Vis filnavn og advar hvis dette er den aktive versjonen — gir
        # brukeren konkret kontekst før destruktiv handling.
        version_name = vid
        is_active = False
        try:
            v = self._get_version_info(dtype, vid)
            version_name = Path(v.path).name
        except Exception:
            pass
        try:
            active_id = _get_active_version_id(self._state.client, year=self._state.year, dtype=dtype)
            is_active = bool(active_id and active_id == vid)
        except Exception:
            pass

        msg = f"Slette versjon?\n\n{version_name}"
        if is_active:
            msg += (
                "\n\n⚠ Dette er den aktive versjonen. Ved sletting må du "
                "velge en annen versjon før du fortsetter."
            )

        ok = messagebox.askyesno(
            "Slett versjon", msg, parent=self.top, icon="warning",
        )
        if not ok:
            return

        try:
            client_store.delete_version(self._state.client, year=self._state.year, dtype=dtype, version_id=vid)
        except Exception:
            _log.exception("Failed to delete version")
            messagebox.showerror("Versjoner", "Kunne ikke slette versjonen.", parent=self.top)
            return

        self._reload_all(focus_dtype=dtype)
        self._after_change()

    def _on_use_and_close(self) -> None:
        dtype = self._current_dtype()
        vid = self._get_selected_version_id(dtype)
        if not vid:
            return

        # SAF-T-fallback-rader (iid="saft:...") representerer HB-kilden,
        # ikke en native KR/LR-versjon. Vi kan ikke "aktivere" dem som
        # KR/LR — vis info i stedet for å feile stille.
        if vid.startswith("saft:"):
            messagebox.showinfo(
                "SAF-T-kilde",
                "Denne raden viser SAF-T-fila som inneholder "
                f"{_dtype_label(dtype).lower()}-data. Native ekstrahering "
                "til egen versjon kommer i en senere runde.",
                parent=self.top,
            )
            return

        try:
            _set_active_version_id(self._state.client, year=self._state.year, dtype=dtype, version_id=vid)
        except Exception:
            _log.exception("Failed to set active version")
            messagebox.showerror("Versjoner", "Kunne ikke bruke valgt versjon.", parent=self.top)
            return

        if self._on_use_version and dtype == "hb":
            try:
                self._on_use_version(vid)
            except Exception:
                _log.exception("on_use_version failed")
        elif self._on_use_sb_version and dtype == "sb":
            try:
                self._on_use_sb_version(vid)
            except Exception:
                _log.exception("on_use_sb_version failed")

        self._after_change()
        self._on_close()

    def _on_close(self) -> None:
        if self.top is not None:
            self.top.destroy()

    # ------------------------- SAF-T -> SB helpers -------------------------
    def _auto_create_sb_from_saft(self, saft_path: Path) -> None:
        """Try to create SB version from SAF-T. Never raises."""
        try:
            self._import_sb_from_saft(saft_path, make_active_if_missing=True)
        except Exception:
            _log.exception("Auto SB from SAF-T failed")

    def _import_sb_from_saft(self, saft_path: Path, *, make_active: bool = False, make_active_if_missing: bool = False) -> str | None:
        """Extract trial balance from SAF-T and store as SB version.

        Returns the created SB version id or None.
        """

        try:
            from src.shared.saft.trial_balance import make_trial_balance_xlsx_from_saft
        except Exception:
            _log.exception("src.shared.saft.trial_balance module missing")
            messagebox.showerror("Versjoner", "Mangler modul for SAF-T saldobalanse.", parent=self.top)
            return None

        # Decide active behaviour
        if make_active_if_missing:
            active_sb = _get_active_version_id(self._state.client, year=self._state.year, dtype="sb")
            make_active = not bool(active_sb)

        # Create a temp xlsx derived from the SAF-T file
        safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", saft_path.stem)
        tmp_dir = Path(tempfile.mkdtemp(prefix="utvalg_sb_"))
        tmp_xlsx = tmp_dir / f"saldobalanse_fra_{safe_stem}.xlsx"

        try:
            make_trial_balance_xlsx_from_saft(saft_path, tmp_xlsx)
        except Exception:
            _log.exception("Failed to extract trial balance from SAF-T")
            messagebox.showwarning(
                "Versjoner",
                "Kunne ikke hente saldobalanse fra SAF-T. Du kan importere saldobalanse manuelt (Excel) i Saldobalanse-fanen.",
                parent=self.top,
            )
            return None

        try:
            sb_v = client_store.create_version(
                self._state.client,
                year=self._state.year,
                dtype="sb",
                src_path=tmp_xlsx,
                make_active=bool(make_active),
            )
        except Exception:
            _log.exception("Failed to create SB version")
            messagebox.showwarning(
                "Versjoner",
                "Klarte å hente saldobalanse fra SAF-T, men kunne ikke lagre som versjon.",
                parent=self.top,
            )
            return None

        # Suksess-melding fjernet — pillene HB/SB/SAF-T viser status visuelt.
        # Behold warnings for feil-tilfeller (over).
        return sb_v.id


def open_versions_dialog(
    parent: tk.Misc,
    client: str,
    year: int,
    dtype: str,
    current_path_getter,
    on_use_version=None,
    on_use_sb_version=None,
    on_after_change=None,
    on_export_hb=None,
    dtypes: list[str] | None = None,
) -> None:
    """Open dialog.

    When dtype is hb/sb we automatically include both in the dialog to make it
    obvious whether saldobalanse exists.
    """

    # Default-utvalg av faner: alle 4 dtypes vises i én dialog så brukeren
    # kan se alle datakildene samlet. KR/LR kan være tomme i praksis ennå
    # men fanene viser dette tydelig (tom-tilstand i treet).
    if dtypes is None:
        dtypes = ["hb", "sb", "kr", "lr"]

    dlg = _VersionsDialog(
        parent,
        state=_DialogState(client=client, year=year, dtype=dtype),
        current_path_getter=current_path_getter,
        on_use_version=on_use_version,
        on_use_sb_version=on_use_sb_version,
        on_after_change=on_after_change,
        on_export_hb=on_export_hb,
        dtypes=dtypes,
    )
    dlg.show_modal()
