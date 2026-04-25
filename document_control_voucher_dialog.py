"""document_control_voucher_dialog

VoucherSetupDialog — opened from the selection studio toolbar.

Lets the user:
  1. See which Tripletex voucher PDFs are currently indexed for this client/year.
  2. Add new PDFs (browse + scan).
  3. Trigger a full rescan.
  4. See how many bilag were found in each PDF.

The dialog is lightweight and non-modal (transient).  The user sets it up
once per engagement period, then it stays cached.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any
import tkinter as tk


class VoucherSetupDialog(tk.Toplevel):
    """Setup dialog for Tripletex voucher bundle PDFs.

    Opens from the Selection Studio toolbar.  Non-blocking: uses a background
    thread for scanning so the UI stays responsive.
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        client: str | None,
        year: str | None,
    ) -> None:
        super().__init__(master)
        self.title("Last opp bilag — oppsett")
        self.geometry("760x520")
        self.minsize(600, 380)
        self.resizable(True, True)

        self._client = client
        self._year = year
        self._scanning = False

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_ui()
        self._refresh_list()

        self.grab_set()
        self.focus_set()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Header
        hdr = ttk.Frame(self, padding=(12, 10, 12, 6))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(0, weight=1)

        client_label = f"{self._client or 'ukjent klient'}  /  {self._year or 'ukjent år'}"
        ttk.Label(
            hdr, text="Last opp bilag", font=("Segoe UI", 11, "bold")
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(hdr, text=client_label, foreground="#555").grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )
        ttk.Label(
            hdr,
            text=(
                "Legg til bilag fra regnskapssystemet:\n"
                "  • Tripletex: PDF-eksport ('Bilagsjournal' eller 'Vedlegg')\n"
                "  • PowerOffice GO: ZIP-arkiv ('Bilagseksport-Bilag …')\n"
                "Systemet indekserer dem og finner riktig bilag når du åpner et."
            ),
            wraplength=700,
            foreground="#444",
        ).grid(row=2, column=0, sticky="w", pady=(6, 0))

        # Toolbar
        toolbar = ttk.Frame(self, padding=(12, 0, 12, 4))
        toolbar.grid(row=0, column=0, sticky="se")
        ttk.Button(toolbar, text="Legg til bilag-fil(er)...", command=self._add_pdfs).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(toolbar, text="Skann på nytt", command=self._rescan).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(toolbar, text="Fjern valgte", command=self._remove_selected).pack(
            side=tk.LEFT
        )

        # File list
        list_frame = ttk.Frame(self, padding=(12, 0, 12, 4))
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        cols = ("Fil", "Bilag funnet", "Status")
        self._tree = ttk.Treeview(list_frame, columns=cols, show="headings", selectmode="extended")
        self._tree.heading("Fil", text="Bilagsfil")
        self._tree.heading("Bilag funnet", text="Bilag")
        self._tree.heading("Status", text="Status")
        self._tree.column("Fil", width=380, stretch=True)
        self._tree.column("Bilag funnet", width=80, anchor="e")
        self._tree.column("Status", width=160)

        vsb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Status bar
        self._var_status = tk.StringVar(value="")
        ttk.Label(self, textvariable=self._var_status, foreground="#555", padding=(12, 2)).grid(
            row=2, column=0, sticky="w"
        )

        # Footer
        footer = ttk.Frame(self, padding=(12, 4, 12, 10))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="Lukk", command=self.destroy).grid(row=0, column=1)

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------

    def _refresh_list(self) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)

        try:
            from document_control_voucher_index import get_cached_index, get_voucher_search_dirs

            cached = get_cached_index(self._client, self._year)
            search_dirs = get_voucher_search_dirs(self._client, self._year)
        except Exception:
            cached = None
            search_dirs = []

        # Collect unique PDFs from cache
        pdf_paths: dict[str, int] = {}  # path → bilag count
        if cached:
            for entry in cached.values():
                src = str(entry.source_pdf or "")
                if src:
                    pdf_paths[src] = pdf_paths.get(src, 0) + 1

        if not pdf_paths:
            # Show search dirs so user knows where to put files
            dir_lines = "\n".join(str(d) for d in search_dirs) if search_dirs else "(ingen mappeoppføringer funnet)"
            self._tree.insert(
                "",
                tk.END,
                values=(
                    "Ingen bilagsfiler indeksert ennå",
                    "",
                    "Legg til PDF-filer nedenfor",
                ),
            )
            self._var_status.set(
                f"Søkemapper: {', '.join(str(d) for d in search_dirs) or 'ingen satt opp'}"
            )
        else:
            for pdf_path, count in sorted(pdf_paths.items()):
                fname = Path(pdf_path).name
                exists = Path(pdf_path).exists()
                status = "OK" if exists else "Fil ikke funnet"
                self._tree.insert("", tk.END, values=(fname, count, status), tags=(pdf_path,))
            total = sum(pdf_paths.values())
            self._var_status.set(
                f"{len(pdf_paths)} fil(er) indeksert — {total} bilag totalt"
            )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _add_pdfs(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self,
            title="Velg bilag-fil(er) — PDF (Tripletex) eller ZIP (PowerOffice GO)",
            filetypes=[
                ("Bilag-filer (PDF + ZIP)", "*.pdf;*.zip"),
                ("PDF-filer (Tripletex)", "*.pdf"),
                ("ZIP-filer (PowerOffice GO)", "*.zip"),
                ("Alle filer", "*.*"),
            ],
        )
        if not paths:
            return
        self._scan_paths(list(paths), copy=True)

    def _rescan(self) -> None:
        try:
            from document_control_voucher_index import get_voucher_search_dirs, scan_voucher_dirs

            search_dirs = get_voucher_search_dirs(self._client, self._year)
        except Exception as exc:
            messagebox.showerror("Feil", str(exc), parent=self)
            return

        if not search_dirs or not any(d.is_dir() for d in search_dirs):
            messagebox.showinfo(
                "Ingen mapper",
                "Ingen bilagsmapper funnet for denne klienten.\n"
                "Legg til bilag med 'Legg til bilag-fil(er)...'.",
                parent=self,
            )
            return

        self._var_status.set("Skanner...")
        self.update_idletasks()

        def _work() -> None:
            try:
                from document_control_voucher_index import rebuild_index_cache

                index = rebuild_index_cache(self._client, self._year)
                count = len(index)
                self.after(0, lambda: self._on_scan_done(f"Ferdig: {count} bilag funnet"))
            except Exception as exc:
                self.after(0, lambda: self._on_scan_error(str(exc)))

        threading.Thread(target=_work, daemon=True).start()

    def _remove_selected(self) -> None:
        selected = self._tree.selection()
        if not selected:
            return
        # Just remove from the displayed list; clearing cache entries would require
        # more complex logic — for now we just note the limitation.
        messagebox.showinfo(
            "Tips",
            "Slett filen fra bilagsmappen og klikk 'Skann på nytt' for å fjerne den fra indeksen.",
            parent=self,
        )

    def _scan_paths(self, paths: list[str], *, copy: bool) -> None:
        if self._scanning:
            return
        self._scanning = True
        self._var_status.set(f"Skanner {len(paths)} fil(er)...")
        self.update_idletasks()

        def _work() -> None:
            results: list[str] = []
            errors: list[str] = []
            for path in paths:
                try:
                    from document_control_voucher_index import import_voucher_pdf

                    entries = import_voucher_pdf(
                        path,
                        client=self._client,
                        year=self._year,
                        copy_to_vouchers=copy,
                    )
                    results.append(f"{Path(path).name}: {len(entries)} bilag")
                except Exception as exc:
                    errors.append(f"{Path(path).name}: {exc}")

            msg = "Importert:\n" + "\n".join(results)
            if errors:
                msg += "\n\nFeil:\n" + "\n".join(errors)
            self.after(0, lambda: self._on_scan_done(msg, show_popup=bool(errors)))

        threading.Thread(target=_work, daemon=True).start()

    def _on_scan_done(self, message: str, *, show_popup: bool = False) -> None:
        self._scanning = False
        self._refresh_list()
        if show_popup:
            messagebox.showinfo("Importresultat", message, parent=self)
        else:
            self._var_status.set(message.split("\n")[0])

    def _on_scan_error(self, error: str) -> None:
        self._scanning = False
        messagebox.showerror("Skanningsfeil", error, parent=self)
        self._var_status.set("Feil under skanning.")
