"""document_control_batch_dialog

BatchDocumentControlDialog — runs document extraction + analysis for all bilag
in the current selection and shows the results in a table.

Opened from the Selection Studio toolbar ("Massekjøring...").
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import messagebox, ttk

from document_control_batch_service import BatchDocumentResult, run_batch_document_analysis


# Colour tags
_TAG_OK = "row_ok"
_TAG_AVVIK = "row_avvik"
_TAG_IKKE = "row_ikke_funnet"
_TAG_FEIL = "row_feil"

_STATUS_TAG: dict[str, str] = {
    "ok": _TAG_OK,
    "avvik": _TAG_AVVIK,
    "ikke_funnet": _TAG_IKKE,
    "feil": _TAG_FEIL,
}


def _fmt(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return ""
    try:
        rounded = round(float(value), decimals)
        s = f"{rounded:,.{decimals}f}"
        return s.replace(",", "\u00a0").replace(".", ",")
    except Exception:
        return str(value)


class BatchDocumentControlDialog(tk.Toplevel):
    """Batch document control dialog.

    Processes every bilag in *bilag_keys*: extracts the sub-PDF from the
    voucher index, analyses it, and shows a summary table.
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        bilag_keys: list[str],
        df_all: Any,            # pd.DataFrame
        client: str | None,
        year: str | None,
    ) -> None:
        super().__init__(master)
        self.title("Massekjøring — dokumentkontroll")
        self.geometry("1100x640")
        self.minsize(800, 480)
        self.resizable(True, True)

        self._bilag_keys = bilag_keys
        self._df_all = df_all
        self._client = client
        self._year = year
        self._results: list[BatchDocumentResult] = []
        self._running = False

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_ui()
        self.grab_set()
        self.focus_set()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Header + controls
        hdr = ttk.Frame(self, padding=(12, 10, 12, 6))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)

        client_text = f"{self._client or ''}  /  {self._year or ''}"
        ttk.Label(hdr, text="Massekjøring — dokumentkontroll", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(hdr, text=client_text, foreground="#555").grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )
        ttk.Label(
            hdr,
            text=(
                f"{len(self._bilag_keys)} bilag i utvalget. "
                "Systemet vil hente ut og analysere dokumentet for hvert bilag og sammenligne mot regnskapet."
            ),
            foreground="#444",
            wraplength=700,
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))

        # Run button + progress
        ctrl = ttk.Frame(hdr)
        ctrl.grid(row=0, column=2, rowspan=3, sticky="ne")
        self._btn_run = ttk.Button(ctrl, text="Kjør analyse", command=self._start_run)
        self._btn_run.pack(side=tk.TOP, anchor="e", pady=(0, 6))
        self._progressbar = ttk.Progressbar(ctrl, length=200, mode="determinate")
        self._progressbar.pack(side=tk.TOP, anchor="e")
        self._var_progress = tk.StringVar(value="")
        ttk.Label(ctrl, textvariable=self._var_progress, foreground="#555").pack(
            side=tk.TOP, anchor="e", pady=(2, 0)
        )

        # Results table
        table_frame = ttk.Frame(self, padding=(12, 0, 12, 4))
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        cols = (
            "Bilag",
            "Leverandør",
            "Fakturanr",
            "Fakturadato",
            "PDF-beløp",
            "Regnsk.-beløp",
            "Differanse",
            "Avvik",
            "Status",
        )
        self._tree = ttk.Treeview(
            table_frame, columns=cols, show="headings", selectmode="browse"
        )
        self._tree.heading("Bilag", text="Bilag")
        self._tree.heading("Leverandør", text="Leverandør")
        self._tree.heading("Fakturanr", text="Fakturanr")
        self._tree.heading("Fakturadato", text="Dato (PDF)")
        self._tree.heading("PDF-beløp", text="Beløp (PDF)")
        self._tree.heading("Regnsk.-beløp", text="Beløp (regnsk.)")
        self._tree.heading("Differanse", text="Differanse")
        self._tree.heading("Avvik", text="Avvik")
        self._tree.heading("Status", text="Status")

        self._tree.column("Bilag", width=70, anchor="e", stretch=False)
        self._tree.column("Leverandør", width=180, anchor="w")
        self._tree.column("Fakturanr", width=90, anchor="w", stretch=False)
        self._tree.column("Fakturadato", width=90, anchor="w", stretch=False)
        self._tree.column("PDF-beløp", width=110, anchor="e", stretch=False)
        self._tree.column("Regnsk.-beløp", width=110, anchor="e", stretch=False)
        self._tree.column("Differanse", width=110, anchor="e", stretch=False)
        self._tree.column("Avvik", width=220, anchor="w")
        self._tree.column("Status", width=90, anchor="center", stretch=False)

        self._tree.tag_configure(_TAG_OK, foreground="#1a7a1a")
        self._tree.tag_configure(_TAG_AVVIK, foreground="#b52020")
        self._tree.tag_configure(_TAG_IKKE, foreground="#888")
        self._tree.tag_configure(_TAG_FEIL, foreground="#b52020", background="#fff0f0")

        vsb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self._tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self._tree.bind("<Double-1>", self._on_double_click)

        # Summary + footer
        self._var_summary = tk.StringVar(value="")
        ttk.Label(self, textvariable=self._var_summary, foreground="#555", padding=(12, 2)).grid(
            row=2, column=0, sticky="w"
        )

        footer = ttk.Frame(self, padding=(12, 4, 12, 10))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self._btn_review = ttk.Button(footer, text="Gjennomgang ►", command=self._open_review)
        self._btn_review.grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="Eksporter Excel", command=self._export_excel).grid(
            row=0, column=1, padx=(0, 8)
        )
        ttk.Button(footer, text="Lukk", command=self.destroy).grid(row=0, column=2)

    # ------------------------------------------------------------------
    # Running
    # ------------------------------------------------------------------

    def _start_run(self) -> None:
        if self._running:
            return
        self._running = True
        self._btn_run.configure(state="disabled")
        self._progressbar.configure(maximum=max(len(self._bilag_keys), 1), value=0)
        self._var_progress.set(f"0 / {len(self._bilag_keys)}")
        self._var_summary.set("")

        for item in self._tree.get_children():
            self._tree.delete(item)

        threading.Thread(target=self._run_worker, daemon=True).start()

    def _run_worker(self) -> None:
        def _progress(current: int, total: int, bilag_nr: str) -> None:
            self.after(0, lambda c=current, t=total, b=bilag_nr: self._on_progress(c, t, b))

        try:
            results = run_batch_document_analysis(
                self._bilag_keys,
                client=self._client,
                year=self._year,
                df_all=self._df_all,
                save_results=True,
                progress_callback=_progress,
            )
            self.after(0, lambda r=results: self._on_done(r))
        except Exception as exc:
            self.after(0, lambda e=exc: self._on_error(str(e)))

    def _on_progress(self, current: int, total: int, bilag_nr: str) -> None:
        self._progressbar.configure(value=current)
        if bilag_nr:
            self._var_progress.set(f"{current} / {total}  (bilag {bilag_nr})")
        else:
            self._var_progress.set(f"{current} / {total}")

    def _on_done(self, results: list[BatchDocumentResult]) -> None:
        self._running = False
        self._results = results
        self._btn_run.configure(state="normal")

        for r in results:
            avvik_text = "; ".join(r.validation_messages[:2]) if r.validation_messages else ""
            if len(r.validation_messages) > 2:
                avvik_text += f" (+{len(r.validation_messages) - 2} til)"

            diff_text = _fmt(r.amount_diff) if r.amount_diff is not None else ""

            values = (
                r.bilag_nr,
                r.supplier_name,
                r.invoice_number,
                r.invoice_date,
                _fmt(r.invoice_total) if r.invoice_total is not None else "",
                _fmt(r.accounting_ref),
                diff_text,
                avvik_text,
                r.status_label,
            )
            tag = _STATUS_TAG.get(r.status, "")
            self._tree.insert("", tk.END, values=values, tags=(tag,) if tag else ())

        n_ok = sum(1 for r in results if r.status == "ok")
        n_avvik = sum(1 for r in results if r.status == "avvik")
        n_ikke = sum(1 for r in results if r.status == "ikke_funnet")
        n_feil = sum(1 for r in results if r.status == "feil")
        self._var_summary.set(
            f"Ferdig: {n_ok} OK  |  {n_avvik} avvik  |  {n_ikke} ikke funnet  |  {n_feil} feil"
        )
        self._var_progress.set(f"{len(results)} / {len(results)}  — ferdig")

    def _on_error(self, error: str) -> None:
        self._running = False
        self._btn_run.configure(state="normal")
        messagebox.showerror("Feil", f"Massekjøring feilet:\n\n{error}", parent=self)

    # ------------------------------------------------------------------
    # Interactions
    # ------------------------------------------------------------------

    def _on_double_click(self, _evt: tk.Event) -> None:  # type: ignore[type-arg]
        """Open document control dialog for the selected bilag."""
        selection = self._tree.selection()
        if not selection:
            return
        values = self._tree.item(selection[0], "values")
        if not values:
            return
        bilag_nr = str(values[0])

        try:
            from document_control_dialog import DocumentControlDialog
            from document_engine.engine import normalize_bilag_key

            bilag_key = normalize_bilag_key(bilag_nr)
            df = self._df_all
            if df is not None and not df.empty and "Bilag" in df.columns:
                mask = df["Bilag"].map(normalize_bilag_key) == bilag_key
                df_bilag = df.loc[mask].copy()
            else:
                import pandas as pd
                df_bilag = pd.DataFrame()

            DocumentControlDialog(
                self,
                bilag=bilag_key,
                df_bilag=df_bilag,
                client=self._client,
                year=self._year,
            )
        except Exception as exc:
            messagebox.showerror("Feil", str(exc), parent=self)

    def _open_review(self) -> None:
        if not self._results:
            messagebox.showinfo("Gjennomgang", "Kjør analyse først.", parent=self)
            return
        from document_control_review_dialog import DocumentControlReviewDialog
        DocumentControlReviewDialog(
            self,
            results=self._results,
            df_all=self._df_all,
            client=self._client,
            year=self._year,
        )

    def _export_excel(self) -> None:
        if not self._results:
            messagebox.showinfo("Eksporter", "Ingen resultater å eksportere.", parent=self)
            return
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Lagre massekjøring som Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=f"Dokumentkontroll_{self._client or 'klient'}_{self._year or ''}.xlsx",
        )
        if not path:
            return
        try:
            import pandas as pd
            rows = []
            for r in self._results:
                rows.append({
                    "Bilag": r.bilag_nr,
                    "Status": r.status_label,
                    "Leverandør": r.supplier_name,
                    "Fakturanr": r.invoice_number,
                    "Fakturadato": r.invoice_date,
                    "PDF-beløp": r.invoice_total,
                    "Regnskapsbeløp": r.accounting_ref,
                    "Differanse": r.amount_diff,
                    "Avvik": "; ".join(r.validation_messages),
                    "Dokumentsti": r.extracted_path,
                })
            pd.DataFrame(rows).to_excel(path, index=False)
            messagebox.showinfo("Eksporter", "Ferdig.", parent=self)
        except Exception as exc:
            messagebox.showerror("Eksporter", str(exc), parent=self)
