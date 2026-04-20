from __future__ import annotations

from datetime import datetime
import json
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

import account_detail_classification
import analyse_mapping_service
import app_paths
import classification_config
import classification_workspace
import konto_klassifisering
import payroll_classification
import regnskap_config
import regnskapslinje_suggest
import session
from account_profile import AccountProfileDocument
from regnskap_mapping import normalize_regnskapslinjer
from page_saldobalanse import _resolve_sb_views

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore


# Helpers flyttet til page_admin_helpers.py (refaktor PR 3).
from page_admin_helpers import (
    _CATALOG_AREA_CONTROL_TAGS,
    _CATALOG_AREA_LEGACY_GROUPS,
    _CATALOG_AREA_PAYROLL_GROUPS,
    _CATALOG_AREA_PAYROLL_TAGS,
    _alias_concept_preview_text,
    _alias_preview_text,
    _catalog_area_config,
    _catalog_area_matches,
    _catalog_area_options,
    _clean_text,
    _client_year,
    _effective_sb_rows,
    _format_amount,
    _format_special_add_lines,
    _int_list,
    _mirror_rulebook_to_a07_storage,
    _multiline_text,
    _normalize_alias_document,
    _normalize_catalog_document,
    _normalize_regnskapslinje_rulebook_document,
    _normalize_rulebook_document,
    _normalize_threshold_document,
    _parse_special_add_lines,
    _saved_status_text,
    _string_list,
)


# Preview-dialoger flyttet til page_admin_preview.py (refaktor PR 4).
from page_admin_preview import (
    _RL_PREVIEW_FILTER_OPTIONS,
    _format_rl_baseline,
    _format_rl_current,
    _format_rl_mapping_source,
    _format_rl_override,
    _format_rl_suggestion,
    _has_preview_state,
    _preview_detail,
    _preview_next_action_text,
    _preview_status_text,
    _rl_mapping_source_explanation,
    _rl_preview_detail,
    _rl_preview_is_ready_for_suggestion,
    _rl_preview_next_action_text,
    _rl_preview_status_text,
)


# Editor-dialoger er splittet per type (refaktor PR 5).
from page_admin_actions import _ActionLibraryEditor
from page_admin_alias import _AliasEditor
from page_admin_workpapers import _WorkpaperLibraryEditor
from page_admin_catalog import _CatalogEditor
from page_admin_detail_class import _DetailClassEditor
from page_admin_editor_base import _JsonEditor
from page_admin_rulebook import _RulebookEditor
from page_admin_threshold import _ThresholdEditor



# RL-datatyper, konstanter og helpers (refaktor PR 6).
from page_admin_rl_models import (
    LINJETYPE_SUMPOST,
    LINJETYPE_VANLIG,
    RL_FILTER_ALLE,
    RL_FILTER_MED_FIN,
    RL_FILTER_SUMPOST,
    RL_FILTER_UTEN_FIN,
    RL_FILTER_VALUES,
    RL_FILTER_VANLIG,
    RLBaselineRow,
    _format_baseline_source_line,
    _format_kontointervall_text,
    _format_overlay_source_line,
    _format_sumtilknytning_text,
    _parse_kontointervall_text,
    _raw_cell_text,
    _rl_row_matches_filter,
    build_rl_baseline_rows,
)
from page_admin_rl import _RegnskapslinjeEditor


# Panel-splits (refaktor PR 7) — Preview/Test- og RL-kontroll-fanene er flyttet
# ut som frie funksjoner som tar ``page: AdminPage``. AdminPage-metodene er
# tynne wrappers som kaller inn hit.
import page_admin_preview_panel
import page_admin_rl_panel



class AdminPage(ttk.Frame):  # type: ignore[misc]
    def __init__(self, master: Any = None) -> None:
        super().__init__(master)
        self._analyse_page: Any = None
        self._preview_rows = pd.DataFrame(columns=["Konto", "Kontonavn", "IB", "Endring", "UB"])
        self._preview_items: dict[str, classification_workspace.ClassificationWorkspaceItem] = {}
        # Preview/Test lastes lazy ved fanebytte slik at åpning av Admin og
        # Regnskapslinjer ikke trigger tung preview-bygging.
        self._preview_loaded_once: bool = False
        self._preview_dirty: bool = True
        # RL-kontroll: canonical RL-admin rows for the dedicated RL control tab.
        self._rl_rows: dict[str, analyse_mapping_service.RLAdminRow] = {}
        self._preview_search_var = tk.StringVar(value="") if tk is not None else None
        self._preview_filter_var = tk.StringVar(value="Alle") if tk is not None else None
        self._rl_search_var = tk.StringVar(value="") if tk is not None else None
        self._rl_filter_var = tk.StringVar(value="Alle") if tk is not None else None
        self._status_var = tk.StringVar(value="Admin påvirker bare regler og forslag.") if tk is not None else None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky="nsew")
        self._notebook = notebook

        self._aliases_editor = _AliasEditor(
            notebook,
            title="Konseptaliaser",
            loader=self._load_aliases_document,
            saver=self._save_aliases_document,
            on_saved=self._notify_rule_change,
        )
        self._detail_class_editor = _DetailClassEditor(
            notebook,
            title="Kontoklassifisering",
            loader=self._load_account_detail_classification_document,
            saver=self._save_account_detail_classification_document,
            on_saved=self._notify_rule_change,
        )
        self._rulebook_editor = _RulebookEditor(
            notebook,
            title="A07-regler",
            loader=self._load_rulebook_document,
            saver=self._save_rulebook_document,
            on_saved=self._notify_rule_change,
        )
        self._catalog_editor = _CatalogEditor(
            notebook,
            title="RF-1022 og flagg",
            loader=self._load_catalog_document,
            saver=self._save_catalog_document,
            on_saved=self._notify_rule_change,
        )
        self._regnskapslinje_editor = _RegnskapslinjeEditor(
            notebook,
            title="Regnskapslinjer",
            loader=self._load_regnskapslinje_rulebook_document,
            saver=self._save_regnskapslinje_rulebook_document,
            on_saved=self._notify_rule_change,
        )
        self._thresholds_editor = _ThresholdEditor(
            notebook,
            title="Terskler",
            loader=self._load_thresholds_document,
            saver=self._save_thresholds_document,
            on_saved=self._notify_rule_change,
        )
        # RL-kontroll er deaktivert i runtime. Framet og handlers står parkert
        # lenger nede i filen, men bygges og refreshes IKKE ved oppstart eller
        # regelendring. Regnskapslinjer er den eneste synlige RL-adminflaten.
        self._rl_control_tab = ttk.Frame(self)
        self._actions_editor = _ActionLibraryEditor(notebook, title="Handlinger")
        self._workpapers_editor = _WorkpaperLibraryEditor(notebook, title="Arbeidspapir")
        try:
            from page_admin_brreg_mapping import _BrregMappingEditor
            self._brreg_mapping_editor = _BrregMappingEditor(
                notebook, title="BRREG-mapping",
            )
        except Exception:
            self._brreg_mapping_editor = None  # type: ignore[assignment]
        self._preview_tab = ttk.Frame(notebook)
        notebook.add(self._aliases_editor, text="Konseptaliaser")
        notebook.add(self._detail_class_editor, text="Kontoklassifisering")
        notebook.add(self._rulebook_editor, text="A07-regler")
        notebook.add(self._catalog_editor, text="RF-1022 og flagg")
        notebook.add(self._regnskapslinje_editor, text="Regnskapslinjer")
        notebook.add(self._thresholds_editor, text="Terskler")
        notebook.add(self._actions_editor, text="Handlinger")
        notebook.add(self._workpapers_editor, text="Arbeidspapir")
        if self._brreg_mapping_editor is not None:
            notebook.add(self._brreg_mapping_editor, text="BRREG-mapping")
        notebook.add(self._preview_tab, text="Preview/Test")
        self._build_preview_ui()
        try:
            notebook.bind("<<NotebookTabChanged>>", self._on_admin_tab_changed, add="+")
        except Exception:
            pass
        bottom = ttk.Frame(self)
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        ttk.Label(
            bottom,
            textvariable=self._status_var,
            style="Muted.TLabel",
            padding=(8, 0, 8, 8),
            anchor="w",
            justify="left",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            bottom,
            text="Oppsett…",
            style="Secondary.TButton",
            command=self._on_open_settings,
        ).grid(row=0, column=1, sticky="e", padx=(4, 8), pady=(0, 8))

    def set_analyse_page(self, page: Any) -> None:
        self._analyse_page = page
        # Marker preview som utdatert, men ikke last tungt her. Preview/Test
        # lastes når brukeren faktisk åpner fanen.
        self._preview_dirty = True
        if self._is_preview_tab_active():
            self._ensure_preview_loaded()

    def refresh_from_session(self, *_args: Any, **_kwargs: Any) -> None:
        # Marker preview som utdatert. Hvis Preview/Test er aktiv akkurat nå,
        # refresher vi med en gang; ellers venter vi til brukeren åpner fanen.
        self._preview_dirty = True
        if self._is_preview_tab_active():
            self._ensure_preview_loaded()
        if self._status_var is not None:
            if self._preview_loaded_once and not self._preview_dirty:
                self._status_var.set("Preview oppfrisket fra gjeldende regler.")
            else:
                self._status_var.set(
                    "Admin er klar. Preview/Test lastes når fanen åpnes."
                )

    def _is_preview_tab_active(self) -> bool:
        notebook = getattr(self, "_notebook", None)
        preview_tab = getattr(self, "_preview_tab", None)
        if notebook is None or preview_tab is None:
            return False
        try:
            selected = notebook.select()
        except Exception:
            return False
        if not selected:
            return False
        try:
            return str(selected) == str(preview_tab)
        except Exception:
            return False

    def _on_admin_tab_changed(self, _event: Any = None) -> None:
        if not self._is_preview_tab_active():
            return
        self._ensure_preview_loaded()

    def _ensure_preview_loaded(self) -> None:
        if self._preview_loaded_once and not self._preview_dirty:
            return
        try:
            self._refresh_preview_rows()
        except Exception:
            return
        self._preview_loaded_once = True
        self._preview_dirty = False

    def _load_aliases_document(self) -> tuple[Any, str]:
        document = classification_config.load_alias_library_document()
        return document, str(classification_config.resolve_alias_path())

    def _save_aliases_document(self, document: Any) -> str:
        path = classification_config.save_alias_library_document(document)
        return str(path)

    def _load_account_detail_classification_document(self) -> tuple[Any, str]:
        document = classification_config.load_account_detail_classification_document()
        return document, str(classification_config.resolve_account_detail_classification_path())

    def _save_account_detail_classification_document(self, document: Any) -> str:
        path = classification_config.save_account_detail_classification_document(document)
        return str(path)

    def _load_catalog_document(self) -> tuple[Any, str]:
        document = classification_config.load_catalog_document()
        return document, str(classification_config.resolve_catalog_path())

    def _save_catalog_document(self, document: Any) -> str:
        path = classification_config.save_catalog_document(document)
        return str(path)

    def _load_rulebook_document(self) -> tuple[Any, str]:
        document = classification_config.load_rulebook_document()
        return document, str(classification_config.resolve_rulebook_path())

    def _save_rulebook_document(self, document: Any) -> str:
        path = classification_config.save_rulebook_document(document)
        _mirror_rulebook_to_a07_storage(str(path))
        return str(path)

    def _load_thresholds_document(self) -> tuple[Any, str]:
        document = classification_config.load_thresholds_document()
        return document, str(classification_config.resolve_thresholds_path())

    def _save_thresholds_document(self, document: Any) -> str:
        path = classification_config.save_thresholds_document(document)
        return str(path)

    def _load_regnskapslinje_rulebook_document(self) -> tuple[Any, str]:
        document = classification_config.load_regnskapslinje_rulebook_document()
        return document, str(classification_config.resolve_regnskapslinje_rulebook_path())

    def _save_regnskapslinje_rulebook_document(self, document: Any) -> str:
        path = regnskapslinje_suggest.save_rulebook_document(document)
        return str(path)

    def _notify_rule_change(self) -> None:
        try:
            payroll_classification.invalidate_runtime_caches()
        except Exception:
            pass
        app = getattr(session, "APP", None)
        for attr_name in ("page_saldobalanse", "page_a07", "page_analyse"):
            page = getattr(app, attr_name, None)
            refresh = getattr(page, "refresh_from_session", None)
            if callable(refresh):
                try:
                    refresh(session)
                except Exception:
                    continue
        # Preview er nå utdatert. Hvis Preview/Test er aktiv, last på nytt med
        # en gang; ellers venter vi til brukeren åpner fanen.
        self._preview_dirty = True
        if self._is_preview_tab_active():
            self._ensure_preview_loaded()
        if self._status_var is not None:
            if self._preview_loaded_once and not self._preview_dirty:
                self._status_var.set(
                    "Regelendringer lagret. Forslags-cache er nullstilt, og Analyse, Saldobalanse, A07 og preview er oppfrisket."
                )
            else:
                self._status_var.set(
                    "Regelendringer lagret. Forslags-cache er nullstilt. Preview/Test oppdateres når fanen åpnes."
                )

    def _on_open_settings(self) -> None:
        """Åpne globale innstillinger (datamappe, klientliste, eksportvalg)."""
        try:
            import settings_entry
        except Exception as exc:
            if messagebox is not None:
                messagebox.showerror("Innstillinger", f"Kunne ikke åpne innstillinger: {exc}")
            return

        root = self.winfo_toplevel()

        def _on_data_dir_changed() -> None:
            self._notify_rule_change()

        def _on_clients_changed() -> None:
            self._notify_rule_change()

        settings_entry.open_settings(
            root,
            on_data_dir_changed=_on_data_dir_changed,
            on_clients_changed=_on_clients_changed,
        )

    def _build_rl_control_ui(self) -> None:
        # RL-kontroll-fanen samler hele RL-mappingflyten; parkert i runtime.
        page_admin_rl_panel.build_rl_control_ui(self)

    def _build_preview_ui(self) -> None:
        # Preview/Test-fanen er forbeholdt lønnsrelevante kontoer.
        page_admin_preview_panel.build_preview_ui(self)

    def _preview_filter_value(self) -> str:
        return page_admin_preview_panel.preview_filter_value(self)

    def _preview_filter_options(self) -> tuple[str, ...]:
        return page_admin_preview_panel.preview_filter_options(self)

    _PAYROLL_PREVIEW_COLUMNS = ("Konto", "Kontonavn", "Status", "Neste", "UB")
    _RL_PREVIEW_COLUMNS = (
        "Konto",
        "Kontonavn",
        "Status",
        "Mappingkilde",
        "Baseline",
        "Override",
        "Effektiv",
        "Forslag",
        "Belop",
    )

    def _preview_matches_filter(self, item: classification_workspace.ClassificationWorkspaceItem) -> bool:
        return page_admin_preview_panel.preview_matches_filter(self, item)

    def _rl_filter_value(self) -> str:
        return page_admin_rl_panel.rl_filter_value(self)

    def _rl_matches_filter(self, row: Any) -> bool:
        return page_admin_rl_panel.rl_matches_filter(self, row)

    def _populate_preview_tree(self) -> None:
        page_admin_preview_panel.populate_preview_tree(self)

    def _refresh_preview_rows(self) -> None:
        page_admin_preview_panel.refresh_preview_rows(self)

    def _refresh_rl_control_rows(self) -> None:
        # Parkert: RL-kontroll er deaktivert i runtime.
        page_admin_rl_panel.refresh_rl_control_rows(self)

    def _update_rl_control_banner(self) -> None:
        page_admin_rl_panel.update_rl_control_banner(self)

    def _populate_rl_control_tree(self) -> None:
        page_admin_rl_panel.populate_rl_control_tree(self)

    def _selected_rl_account(self) -> str:
        return page_admin_rl_panel.selected_rl_account(self)

    def _selected_rl_accounts(self) -> list[str]:
        return page_admin_rl_panel.selected_rl_accounts(self)

    def _update_rl_control_details(self) -> None:
        page_admin_rl_panel.update_rl_control_details(self)

    def _selected_preview_account(self) -> str:
        return page_admin_preview_panel.selected_preview_account(self)

    def _selected_preview_accounts(self) -> list[str]:
        return page_admin_preview_panel.selected_preview_accounts(self)

    def _on_rl_set_override_clicked(self) -> None:
        page_admin_rl_panel.on_rl_set_override_clicked(self)

    def _on_rl_clear_override_clicked(self) -> None:
        page_admin_rl_panel.on_rl_clear_override_clicked(self)

    def _on_rl_use_suggestion_clicked(self) -> None:
        page_admin_rl_panel.on_rl_use_suggestion_clicked(self)

    def _on_rl_open_in_analyse_clicked(self) -> None:
        page_admin_rl_panel.on_rl_open_in_analyse_clicked(self)

    def _after_rl_override_change(self) -> None:
        page_admin_rl_panel.after_rl_override_change(self)

    def _update_preview_details(self) -> None:
        page_admin_preview_panel.update_preview_details(self)
