from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

import pandas as pd

from document_control_app_service import (
    analyze_document_for_bilag,
    load_saved_review,
    save_document_review,
    suggest_documents_for_bilag,
)
from document_control_finder import DocumentSuggestion
from document_control_viewer import DocumentPreviewFrame, preview_target_from_evidence
from document_engine.models import DocumentAnalysisResult


FIELD_ORDER = [
    ("supplier_name", "Leverandor"),
    ("supplier_orgnr", "Organisasjonsnummer"),
    ("invoice_number", "Fakturanummer"),
    ("invoice_date", "Fakturadato"),
    ("due_date", "Forfallsdato"),
    ("subtotal_amount", "Belop ekskl. mva"),
    ("vat_amount", "Mva"),
    ("total_amount", "Total"),
    ("currency", "Valuta"),
]


class DocumentControlDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        *,
        bilag: str,
        df_bilag: pd.DataFrame,
        client: str | None = None,
        year: str | None = None,
    ) -> None:
        super().__init__(master)
        self.title("Dokumentkontroll")
        self.geometry("1180x820")
        self.minsize(960, 660)
        self.resizable(True, True)
        if os.name != "nt":
            self.transient(master.winfo_toplevel())

        self._bilag = str(bilag)
        self._df_bilag = df_bilag.copy()
        self._client = client
        self._year = year
        self._analysis: DocumentAnalysisResult | None = None
        self._suggestions: list[DocumentSuggestion] = []
        self._field_evidence_by_key: dict[str, Any] = {}
        self._highlight_field_lookup: dict[str, str] = {}
        self._field_entries: dict[str, ttk.Entry] = {}

        self.var_file_path = tk.StringVar(value="")
        self.var_suggestion = tk.StringVar(value="")
        self.var_status = tk.StringVar(value="1. Velg dokument. 2. Klikk Les opplysninger. 3. Sjekk resultatet.")
        self.var_tab_help = tk.StringVar(value="")
        self.var_highlight_field = tk.StringVar(value="")
        self.field_vars = {key: tk.StringVar(value="") for key, _ in FIELD_ORDER}

        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        self._build_ui()
        self._load_saved_record()
        self._refresh_suggestions(auto_select=not bool(self.var_file_path.get().strip()))
        self._update_tab_help_text()

        self.grab_set()
        self.focus_set()

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=12)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = f"Dokumentkontroll for bilag {self._bilag}"
        if self._client or self._year:
            title += f"  ({self._client or 'ukjent klient'} / {self._year or 'ukjent år'})"
        ttk.Label(header, text=title, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=self._build_context_summary(), wraplength=1080).grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )

        file_bar = ttk.Frame(self, padding=(12, 0, 12, 8))
        file_bar.grid(row=1, column=0, sticky="ew")
        file_bar.columnconfigure(1, weight=1)

        ttk.Label(file_bar, text="Dokument").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(file_bar, textvariable=self.var_file_path).grid(row=0, column=1, sticky="ew")
        ttk.Button(file_bar, text="Velg dokument...", command=self._choose_file).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(file_bar, text="Les opplysninger", command=self._run_analysis).grid(row=0, column=3, padx=(8, 0))
        ttk.Button(file_bar, text="Apne fil", command=self._open_file).grid(row=0, column=4, padx=(8, 0))
        ttk.Label(file_bar, textvariable=self.var_status, wraplength=1080).grid(
            row=1, column=0, columnspan=5, sticky="w", pady=(8, 0)
        )

        ttk.Label(file_bar, text="Mulige dokumenter").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self.cmb_suggestions = ttk.Combobox(file_bar, textvariable=self.var_suggestion, state="readonly")
        self.cmb_suggestions.grid(row=2, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(file_bar, text="Finn mulige dokumenter", command=self._refresh_suggestions).grid(
            row=2, column=2, padx=(8, 0), pady=(8, 0)
        )
        ttk.Button(file_bar, text="Velg dette dokumentet", command=self._use_selected_suggestion).grid(
            row=2, column=3, padx=(8, 0), pady=(8, 0)
        )

        help_bar = ttk.Frame(self, padding=(12, 0, 12, 8))
        help_bar.grid(row=2, column=0, sticky="ew")
        help_bar.columnconfigure(0, weight=1)
        ttk.Label(help_bar, textvariable=self.var_tab_help, wraplength=1080).grid(row=0, column=0, sticky="w")

        self.body = ttk.Notebook(self)
        self.body.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 8))
        self.body.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._tab_document = ttk.Frame(self.body, padding=12)
        self._tab_document.columnconfigure(0, weight=1)
        self._tab_document.rowconfigure(1, weight=1)
        self.body.add(self._tab_document, text="Dokument")

        document_toolbar = ttk.Frame(self._tab_document)
        document_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        document_toolbar.columnconfigure(1, weight=1)

        ttk.Label(document_toolbar, text="Marker felt").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.cmb_highlight_field = ttk.Combobox(
            document_toolbar,
            textvariable=self.var_highlight_field,
            state="disabled",
        )
        self.cmb_highlight_field.grid(row=0, column=1, sticky="ew")
        self.cmb_highlight_field.bind("<<ComboboxSelected>>", self._on_highlight_field_selected)
        ttk.Button(document_toolbar, text="Vis i dokumentet", command=self._highlight_selected_field).grid(
            row=0, column=2, padx=(8, 0)
        )
        ttk.Button(document_toolbar, text="Fjern markering", command=self._clear_viewer_highlight).grid(
            row=0, column=3, padx=(8, 0)
        )

        self.preview = DocumentPreviewFrame(self._tab_document)
        self.preview.grid(row=1, column=0, sticky="nsew")

        tab_fields = ttk.Frame(self.body, padding=12)
        tab_fields.columnconfigure(1, weight=1)
        self.body.add(tab_fields, text="Opplysninger")

        for row_index, (key, label) in enumerate(FIELD_ORDER):
            ttk.Label(tab_fields, text=label).grid(row=row_index, column=0, sticky="w", padx=(0, 10), pady=4)
            entry = ttk.Entry(tab_fields, textvariable=self.field_vars[key])
            entry.grid(row=row_index, column=1, sticky="ew", pady=4)
            entry.bind("<FocusIn>", lambda _event, field_key=key: self._focus_field_in_viewer(field_key))
            self._field_entries[key] = entry

        tab_checks = ttk.Frame(self.body, padding=12)
        tab_checks.columnconfigure(0, weight=1)
        tab_checks.rowconfigure(1, weight=1)
        self.body.add(tab_checks, text="Sjekk mot bilaget")
        ttk.Label(
            tab_checks,
            text="Her ser du om opplysningene fra dokumentet stemmer mot de valgte bilagslinjene.",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.txt_validation = tk.Text(tab_checks, wrap="word", height=18)
        self.txt_validation.grid(row=1, column=0, sticky="nsew")
        validation_scroll = ttk.Scrollbar(tab_checks, orient="vertical", command=self.txt_validation.yview)
        self.txt_validation.configure(yscrollcommand=validation_scroll.set)
        validation_scroll.grid(row=1, column=1, sticky="ns")

        tab_text = ttk.Frame(self.body, padding=12)
        tab_text.columnconfigure(0, weight=1)
        tab_text.rowconfigure(0, weight=1)
        self.body.add(tab_text, text="Lest tekst")
        self.txt_raw = tk.Text(tab_text, wrap="word")
        self.txt_raw.grid(row=0, column=0, sticky="nsew")
        raw_scroll = ttk.Scrollbar(tab_text, orient="vertical", command=self.txt_raw.yview)
        self.txt_raw.configure(yscrollcommand=raw_scroll.set)
        raw_scroll.grid(row=0, column=1, sticky="ns")

        tab_evidence = ttk.Frame(self.body, padding=12)
        tab_evidence.columnconfigure(0, weight=1)
        tab_evidence.rowconfigure(0, weight=1)
        self.body.add(tab_evidence, text="Hvor fant vi det?")
        self.txt_evidence = tk.Text(tab_evidence, wrap="word")
        self.txt_evidence.grid(row=0, column=0, sticky="nsew")
        evidence_scroll = ttk.Scrollbar(tab_evidence, orient="vertical", command=self.txt_evidence.yview)
        self.txt_evidence.configure(yscrollcommand=evidence_scroll.set)
        evidence_scroll.grid(row=0, column=1, sticky="ns")

        tab_metadata = ttk.Frame(self.body, padding=12)
        tab_metadata.columnconfigure(0, weight=1)
        tab_metadata.rowconfigure(0, weight=1)
        self.body.add(tab_metadata, text="Teknisk info")
        self.txt_metadata = tk.Text(tab_metadata, wrap="word")
        self.txt_metadata.grid(row=0, column=0, sticky="nsew")
        metadata_scroll = ttk.Scrollbar(tab_metadata, orient="vertical", command=self.txt_metadata.yview)
        self.txt_metadata.configure(yscrollcommand=metadata_scroll.set)
        metadata_scroll.grid(row=0, column=1, sticky="ns")

        notes_frame = ttk.LabelFrame(self, text="Notater", padding=12)
        notes_frame.grid(row=4, column=0, sticky="nsew", padx=12, pady=(0, 12))
        notes_frame.columnconfigure(0, weight=1)
        self.txt_notes = tk.Text(notes_frame, height=5, wrap="word")
        self.txt_notes.grid(row=0, column=0, sticky="ew")
        notes_scroll = ttk.Scrollbar(notes_frame, orient="vertical", command=self.txt_notes.yview)
        self.txt_notes.configure(yscrollcommand=notes_scroll.set)
        notes_scroll.grid(row=0, column=1, sticky="ns")

        footer = ttk.Frame(self, padding=(12, 0, 12, 12))
        footer.grid(row=5, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="Lagre vurdering", command=self._save_record).grid(row=0, column=1, sticky="e")
        ttk.Button(footer, text="Lukk", command=self.destroy).grid(row=0, column=2, sticky="e", padx=(8, 0))

    def _build_context_summary(self) -> str:
        row_count = len(self._df_bilag)
        amount_col = next((name for name in ("Beløp", "Belop", "Amount") if name in self._df_bilag.columns), None)
        date_col = next((name for name in ("Dato", "Dokumentdato", "Bokf.dato") if name in self._df_bilag.columns), None)

        parts = [f"{row_count} regnskapslinjer"]
        if amount_col:
            series = pd.to_numeric(self._df_bilag[amount_col], errors="coerce").dropna()
            if not series.empty:
                parts.append(f"netto {series.sum():,.2f}")
                parts.append(f"absolutt {series.abs().sum():,.2f}")
        if date_col:
            dates = sorted({str(value).strip() for value in self._df_bilag[date_col].dropna().tolist() if str(value).strip()})
            if dates:
                parts.append(f"datoer: {', '.join(dates[:4])}")
        return "Dette sammenlignes mot bilaget: " + " | ".join(parts)

    def _on_tab_changed(self, _event: tk.Event[tk.Misc]) -> None:
        self._update_tab_help_text()

    def _update_tab_help_text(self) -> None:
        try:
            current_tab = self.body.tab(self.body.select(), "text")
        except Exception:
            current_tab = "Dokument"

        help_text = {
            "Dokument": "Se dokumentet her. Velg et felt i listen for a hoppe til stedet der det ble funnet.",
            "Opplysninger": "Her ser du hvilke opplysninger dokumentleseren fant. Rett dem hvis noe er feil.",
            "Sjekk mot bilaget": "Her ser du om dokumentet stemmer mot de valgte bilagslinjene.",
            "Lest tekst": "Dette er teksten som ble lest ut av dokumentet. Mest nyttig ved feilsoking.",
            "Hvor fant vi det?": "Her ser du hvor hvert felt kom fra, hvilken side det ble funnet pa, og hvor sikkert treffet var.",
            "Teknisk info": "Teknisk informasjon om tekstkilder, profiler og motorvalg. Nyttig ved feilsoking.",
        }.get(current_tab, "")
        self.var_tab_help.set(help_text)

    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Velg dokument til bilagskontroll",
            filetypes=[
                ("Dokumenter", "*.pdf *.xml *.txt *.png *.jpg *.jpeg *.tif *.tiff *.bmp"),
                ("Alle filer", "*.*"),
            ],
        )
        if not path:
            return
        self.var_file_path.set(path)
        self._reset_analysis_view_state()
        self.preview.load_file(path)
        self.var_status.set("Dokument valgt. Klikk Les opplysninger for a hente ut verdier fra dokumentet.")
        self._save_record(silent=True)

    def _open_file(self) -> None:
        path_text = self.var_file_path.get().strip()
        if not path_text:
            messagebox.showinfo("Dokumentkontroll", "Velg et dokument først.")
            return
        path = Path(path_text)
        if not path.exists():
            messagebox.showerror("Dokumentkontroll", f"Fant ikke filen:\n{path}")
            return
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("Dokumentkontroll", f"Kunne ikke åpne filen.\n\n{exc}")

    def _run_analysis(self) -> None:
        path_text = self.var_file_path.get().strip()
        if not path_text:
            messagebox.showinfo("Dokumentkontroll", "Velg et dokument før analyse.")
            return

        self.preview.load_file(path_text)

        try:
            analysis = analyze_document_for_bilag(path_text, df_bilag=self._df_bilag)
        except Exception as exc:
            messagebox.showerror("Dokumentkontroll", f"Kunne ikke analysere dokumentet.\n\n{exc}")
            return

        self._analysis = analysis
        self._apply_analysis(analysis)
        found_count = sum(1 for value in analysis.fields.values() if value)
        checked_count = sum(
            1
            for evidence in (analysis.field_evidence or {}).values()
            if getattr(evidence, "validated_against_voucher", None) is not None
        )
        self.var_status.set(
            f"Ferdig. Fant {found_count} opplysninger. "
            f"Sjekk Opplysninger-fanen og Sjekk mot bilaget-fanen"
            f"{'' if checked_count <= 0 else f' ({checked_count} kontroller klare)'}."
        )
        self._save_record(silent=True)

    def _apply_analysis(self, analysis: DocumentAnalysisResult) -> None:
        for key, _label in FIELD_ORDER:
            self.field_vars[key].set(analysis.fields.get(key, ""))

        self._field_evidence_by_key = dict(analysis.field_evidence or {})
        self.preview.load_file(analysis.file_path or self.var_file_path.get().strip())
        self._refresh_highlight_options()

        self._replace_text(self.txt_validation, "\n".join(analysis.validation_messages))
        self._replace_text(self.txt_raw, analysis.raw_text_excerpt)
        self._replace_text(self.txt_evidence, self._format_evidence_text(analysis))
        self._replace_text(self.txt_metadata, self._format_metadata_text(analysis))
        self._highlight_first_available_field(select_tab=False)

    def _load_saved_record(self) -> None:
        payload = load_saved_review(self._client, self._year, self._bilag)
        if not payload:
            self._reset_analysis_view_state(clear_notes=True)
            self.preview.load_file(None)
            return

        self.var_file_path.set(payload.get("file_path", ""))
        self.var_status.set(
            "Fant en tidligere lagret vurdering. Du kan lese dokumentet pa nytt eller justere opplysningene manuelt."
        )

        for key, _label in FIELD_ORDER:
            self.field_vars[key].set(payload.get("fields", {}).get(key, ""))

        self._field_evidence_by_key = dict(payload.get("field_evidence", {}) or {})
        self._refresh_highlight_options()
        self.preview.load_file(self.var_file_path.get().strip())

        self._replace_text(self.txt_validation, "\n".join(payload.get("validation_messages", [])))
        self._replace_text(self.txt_raw, payload.get("raw_text_excerpt", ""))
        self._replace_text(self.txt_evidence, self._format_saved_evidence(payload))
        self._replace_text(self.txt_metadata, self._format_saved_metadata(payload))
        self._replace_text(self.txt_notes, payload.get("notes", ""))
        self._highlight_first_available_field(select_tab=False)

    def _refresh_suggestions(self, auto_select: bool = False) -> None:
        self._suggestions = suggest_documents_for_bilag(
            client=self._client,
            year=self._year,
            bilag=self._bilag,
            df_bilag=self._df_bilag,
        )

        labels = [suggestion.display_label() for suggestion in self._suggestions]
        self.cmb_suggestions.configure(values=labels)

        if not labels:
            self.var_suggestion.set("")
            if auto_select and not self.var_file_path.get().strip():
                self.var_status.set("Fant ingen gode dokumentforslag automatisk. Du kan fortsatt velge fil manuelt.")
            return

        self.var_suggestion.set(labels[0])
        if auto_select and not self.var_file_path.get().strip():
            self._use_selected_suggestion(show_status=False)
            self.var_status.set(f"Fant {len(labels)} mulige dokumenter. Det beste treffet er valgt automatisk.")

    def _use_selected_suggestion(self, show_status: bool = True) -> None:
        label = self.var_suggestion.get().strip()
        if not label or not self._suggestions:
            if show_status:
                self.var_status.set("Ingen dokumentforslag valgt.")
            return

        index = next((idx for idx, suggestion in enumerate(self._suggestions) if suggestion.display_label() == label), 0)
        suggestion = self._suggestions[index]
        self.var_file_path.set(suggestion.path)
        self._reset_analysis_view_state()
        self.preview.load_file(suggestion.path)
        if show_status:
            reason_text = ", ".join(suggestion.reasons[:3])
            self.var_status.set(f"Valgte {Path(suggestion.path).name}. Grunnlag: {reason_text}.")

    def _save_record(self, silent: bool = False) -> None:
        payload = save_document_review(
            client=self._client,
            year=self._year,
            bilag=self._bilag,
            file_path=self.var_file_path.get().strip(),
            field_values={key: var.get().strip() for key, var in self.field_vars.items()},
            validation_messages=self._read_lines(self.txt_validation),
            raw_text_excerpt=self.txt_raw.get("1.0", "end").strip(),
            notes=self.txt_notes.get("1.0", "end").strip(),
            analysis=self._analysis,
        )
        if not silent:
            if payload.get("supplier_profile_key"):
                self.var_status.set(
                    "Vurderingen er lagret lokalt. Denne dokumenttypen vil bli lettere a kjenne igjen neste gang."
                )
            else:
                self.var_status.set("Vurderingen er lagret lokalt for dette bilaget.")
            messagebox.showinfo("Dokumentkontroll", "Vurderingen er lagret.")

    def _on_highlight_field_selected(self, _event: tk.Event[tk.Misc]) -> None:
        self._highlight_selected_field()

    def _highlight_selected_field(self, *, select_tab: bool = True) -> bool:
        label = self.var_highlight_field.get().strip()
        field_key = self._highlight_field_lookup.get(label)
        if not field_key:
            return False
        return self._focus_field_in_viewer(field_key, select_tab=select_tab)

    def _focus_field_in_viewer(self, field_key: str, *, select_tab: bool = True) -> bool:
        label = dict(FIELD_ORDER).get(field_key, field_key)
        target = preview_target_from_evidence(field_key, self._field_evidence_by_key, label=label)
        if target is None:
            return False
        if select_tab:
            self.body.select(self._tab_document)
        self.preview.set_highlight(target)
        matching_label = next(
            (display_label for display_label, key in self._highlight_field_lookup.items() if key == field_key),
            "",
        )
        if matching_label:
            self.var_highlight_field.set(matching_label)
        return True

    def _clear_viewer_highlight(self) -> None:
        self.preview.set_highlight(None)
        if self.cmb_highlight_field.cget("state") != "disabled":
            self.var_highlight_field.set("")

    def _refresh_highlight_options(self) -> None:
        values: list[str] = []
        self._highlight_field_lookup.clear()

        for key, label in FIELD_ORDER:
            evidence = self._field_evidence_by_key.get(key)
            if not evidence:
                continue
            page = self._evidence_value(evidence, "page")
            bbox = self._evidence_value(evidence, "bbox")
            source = str(self._evidence_value(evidence, "source") or "")
            if page is None and not bbox:
                continue
            suffix_parts: list[str] = []
            if page is not None:
                suffix_parts.append(f"side {page}")
            if bbox:
                suffix_parts.append("markering")
            if source:
                suffix_parts.append(source)
            display = label if not suffix_parts else f"{label} ({', '.join(suffix_parts)})"
            values.append(display)
            self._highlight_field_lookup[display] = key

        state = "readonly" if values else "disabled"
        self.cmb_highlight_field.configure(values=values, state=state)
        if self.var_highlight_field.get().strip() not in self._highlight_field_lookup:
            self.var_highlight_field.set(values[0] if values else "")

    def _highlight_first_available_field(self, *, select_tab: bool) -> bool:
        if not self._highlight_field_lookup:
            return False
        if not self.var_highlight_field.get().strip():
            first_label = next(iter(self._highlight_field_lookup))
            self.var_highlight_field.set(first_label)
        return self._highlight_selected_field(select_tab=select_tab)

    def _clear_loaded_evidence(self) -> None:
        self._field_evidence_by_key = {}
        self._refresh_highlight_options()
        self.preview.set_highlight(None)

    def _reset_analysis_view_state(self, *, clear_notes: bool = False) -> None:
        self._analysis = None
        self._clear_loaded_evidence()
        for key, _label in FIELD_ORDER:
            self.field_vars[key].set("")
        self._replace_text(self.txt_validation, "")
        self._replace_text(self.txt_raw, "")
        self._replace_text(self.txt_evidence, "")
        self._replace_text(self.txt_metadata, "")
        if clear_notes:
            self._replace_text(self.txt_notes, "")

    @staticmethod
    def _evidence_value(evidence: Any, key: str) -> Any:
        if isinstance(evidence, dict):
            return evidence.get(key)
        return getattr(evidence, key, None)

    @staticmethod
    def _replace_text(widget: tk.Text, value: str) -> None:
        widget.delete("1.0", "end")
        if value:
            widget.insert("1.0", value)

    @staticmethod
    def _read_lines(widget: tk.Text) -> list[str]:
        content = widget.get("1.0", "end").strip()
        if not content:
            return []
        return [line.strip() for line in content.splitlines() if line.strip()]

    @staticmethod
    def _format_metadata_text(analysis: DocumentAnalysisResult) -> str:
        metadata = analysis.metadata or {}
        lines = [
            f"Kilde: {analysis.source}",
            f"OCR brukt: {'ja' if metadata.get('ocr_used') else 'nei'}",
            f"Profilstatus: {analysis.profile_status or 'none'}",
        ]
        if metadata.get("page_count") is not None:
            lines.append(f"Sider: {metadata.get('page_count')}")
        if metadata.get("text_char_count") is not None:
            lines.append(f"Tegn i valgt tekstkilde: {metadata.get('text_char_count')}")
        if metadata.get("line_count") is not None:
            lines.append(f"Antall linjer i valgt tekstkilde: {metadata.get('line_count')}")
        if metadata.get("selected_score") is not None:
            lines.append(f"Valgt kandidatscore: {metadata.get('selected_score')}")
        if metadata.get("matched_profile_key"):
            lines.append(f"Matchet leverandørprofil: {metadata.get('matched_profile_key')}")
        if metadata.get("matched_profile_score") is not None:
            lines.append(f"Profilscore: {metadata.get('matched_profile_score')}")
        if metadata.get("matched_profile_samples") is not None:
            lines.append(f"Profilen bygger på {metadata.get('matched_profile_samples')} lagrede dokument(er)")
        applied_fields = metadata.get("profile_applied_fields") or []
        if applied_fields:
            lines.append(f"Profilerte felter brukt: {', '.join(applied_fields)}")

        candidate_sources = metadata.get("candidate_sources") or []
        if candidate_sources:
            lines.append("")
            lines.append("Kandidater:")
            for candidate in candidate_sources:
                lines.append(
                    f"- {candidate.get('source')}: score {candidate.get('score')}, "
                    f"OCR={candidate.get('ocr_used')}, tegn={candidate.get('char_count')}"
                )

        return "\n".join(lines)

    @staticmethod
    def _format_evidence_text(analysis: DocumentAnalysisResult) -> str:
        lines: list[str] = []
        for key, label in FIELD_ORDER:
            evidence = analysis.field_evidence.get(key)
            if evidence is None or not evidence.normalized_value:
                continue
            lines.append(f"{label}: {evidence.normalized_value}")
            lines.append(f"  kilde: {evidence.source or 'ukjent'}")
            if evidence.raw_value and evidence.raw_value != evidence.normalized_value:
                lines.append(f"  råverdi: {evidence.raw_value}")
            lines.append(f"  confidence: {evidence.confidence:.2f}")
            if evidence.page is not None:
                lines.append(f"  side: {evidence.page}")
            if evidence.bbox is not None:
                bbox = ", ".join(f"{value:.1f}" for value in evidence.bbox)
                lines.append(f"  bbox: ({bbox})")
            lines.append(f"  profilutfylt: {'ja' if evidence.inferred_from_profile else 'nei'}")
            if evidence.validated_against_voucher is not None:
                lines.append(
                    f"  validert mot bilag: {'ja' if evidence.validated_against_voucher else 'nei'}"
                )
            if evidence.validation_note:
                lines.append(f"  validering: {evidence.validation_note}")
            lines.append("")
        return "\n".join(lines).strip()

    @classmethod
    def _format_saved_metadata(cls, payload: dict[str, Any]) -> str:
        source = payload.get("analysis_source", "")
        metadata = payload.get("analysis_metadata", {}) or {}
        if payload.get("supplier_profile_key") and not metadata.get("matched_profile_key"):
            metadata = dict(metadata)
            metadata["matched_profile_key"] = payload.get("supplier_profile_key")
            metadata["matched_profile_samples"] = payload.get("supplier_profile_samples")
        analysis = DocumentAnalysisResult(
            file_path=payload.get("file_path", ""),
            file_type="",
            source=source or "ukjent",
            metadata=metadata,
            profile_status=str(payload.get("profile_status", "") or "none"),
        )
        return cls._format_metadata_text(analysis)

    @staticmethod
    def _format_saved_evidence(payload: dict[str, Any]) -> str:
        evidence_map = dict(payload.get("field_evidence", {}) or {})
        lines: list[str] = []
        for key, label in FIELD_ORDER:
            evidence = evidence_map.get(key)
            if not evidence:
                continue
            lines.append(f"{label}: {evidence.get('normalized_value', '')}")
            lines.append(f"  kilde: {evidence.get('source', '') or 'ukjent'}")
            if evidence.get("raw_value") and evidence.get("raw_value") != evidence.get("normalized_value"):
                lines.append(f"  råverdi: {evidence.get('raw_value')}")
            if evidence.get("confidence") is not None:
                lines.append(f"  confidence: {float(evidence.get('confidence', 0.0) or 0.0):.2f}")
            if evidence.get("page") is not None:
                lines.append(f"  side: {evidence.get('page')}")
            if evidence.get("bbox"):
                bbox = ", ".join(f"{float(value):.1f}" for value in list(evidence.get("bbox") or []))
                lines.append(f"  bbox: ({bbox})")
            lines.append("")
        return "\n".join(lines).strip()
