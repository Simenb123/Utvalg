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
from src.pages.saldobalanse.frontend.page import _resolve_sb_views

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore


# Helpers flyttet til page_admin_helpers.py (refaktor PR 3).
from page_admin_helpers import (
    _CATALOG_AREA_LEGACY_GROUPS,
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

        self._aliases_editor = None
        self._detail_class_editor = _DetailClassEditor(
            notebook,
            title="Kontoklassifisering",
            loader=self._load_account_detail_classification_document,
            saver=self._save_account_detail_classification_document,
            on_saved=self._notify_rule_change,
        )
        self._rulebook_editor = _RulebookEditor(
            notebook,
            title="A07-regler og alias",
            loader=self._load_rulebook_document,
            saver=self._save_rulebook_document,
            on_saved=self._notify_rule_change,
        )
        self._catalog_editor = _CatalogEditor(
            notebook,
            title="Flagg og analysegrupper",
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
        notebook.add(self._detail_class_editor, text="Kontoklassifisering")
        notebook.add(self._rulebook_editor, text="A07-regler")
        notebook.add(self._catalog_editor, text="Flagg og grupper")
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
            text="Ytelsesmonitor…",
            style="Secondary.TButton",
            command=self._on_open_monitoring,
        ).grid(row=0, column=1, sticky="e", padx=(4, 4), pady=(0, 8))
        ttk.Button(
            bottom,
            text="Oppsett…",
            style="Secondary.TButton",
            command=self._on_open_settings,
        ).grid(row=0, column=2, sticky="e", padx=(4, 8), pady=(0, 8))

        # Landing-overlay som dekker hele admin-siden inntil bruker
        # låser opp via "Oppsett…"-knappen. Sørger for at sensitive
        # admin-faner (Kontoklassifisering, A07-regler osv.) ikke vises
        # for uautorisert bruker.
        self._build_admin_landing()

    def _build_admin_landing(self) -> None:
        """Lag og vis landing-overlay over admin-innholdet."""
        try:
            import vaak_tokens as _vt
            bg_color = "#" + _vt.BG_SAND_SOFT
            text_color = "#" + _vt.FOREST
            font_family = _vt.FONT_FAMILY_BODY
        except Exception:
            bg_color = "#F4EDDC"
            text_color = "#325B1E"
            font_family = "Segoe UI"

        landing = tk.Frame(self, background=bg_color, borderwidth=0)
        # place(...) i stedet for grid: lar overlayen dekke ALT i admin,
        # uavhengig av hvilke rader/kolonner som er konfigurert.
        landing.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Hold logo-bildet i live så GC ikke fjerner det.
        self._landing_logo_img = self._load_aarvaaken_logo()
        if self._landing_logo_img is not None:
            tk.Label(
                landing,
                image=self._landing_logo_img,
                background=bg_color,
                borderwidth=0,
            ).pack(pady=(120, 24))
        else:
            # Fallback hvis bildet ikke kan lastes — vis tekst-banner.
            tk.Label(
                landing,
                text="AarVaaken",
                background=bg_color,
                foreground=text_color,
                font=(font_family, 32, "bold"),
            ).pack(pady=(160, 24))

        tk.Label(
            landing,
            text="Admin-tilgang krever passord",
            background=bg_color,
            foreground=text_color,
            font=(font_family, 11),
        ).pack(pady=(0, 12))

        # Passord-felt direkte på landing — bruker slipper popup-dialog.
        self._landing_password_var = tk.StringVar(value="")
        pw_entry = ttk.Entry(
            landing,
            textvariable=self._landing_password_var,
            show="*",
            width=30,
            justify="center",
        )
        pw_entry.pack(pady=(0, 24))
        # Enter i passord-feltet utløser samme handling som "Gå til Admin".
        pw_entry.bind("<Return>", lambda _e: self._on_landing_unlock())
        self._landing_password_entry = pw_entry

        btn_row = tk.Frame(landing, background=bg_color)
        btn_row.pack()

        ttk.Button(
            btn_row,
            text="Ytelsesmonitor…",
            style="Secondary.TButton",
            command=self._on_open_monitoring,
        ).pack(side="left", padx=6)

        ttk.Button(
            btn_row,
            text="Oppsett…",
            style="Secondary.TButton",
            command=self._on_open_settings,
        ).pack(side="left", padx=6)

        ttk.Button(
            btn_row,
            text="Gå til Admin",
            style="Primary.TButton",
            command=self._on_landing_unlock,
        ).pack(side="left", padx=6)

        self._landing_frame = landing

        # Skjul landing umiddelbart hvis admin allerede er låst opp i denne
        # økten (kan skje hvis AdminPage rebygges etter unlock).
        try:
            app = self.winfo_toplevel()
            if getattr(app, "_admin_unlocked", False):
                self.hide_admin_landing()
        except Exception:
            pass

    def _load_aarvaaken_logo(self):
        """Last AarVaaken-logoen som PhotoImage. Returnerer None ved feil."""
        try:
            from PIL import Image, ImageTk  # type: ignore[import-untyped]
            from pathlib import Path
            import sys

            candidates = []
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                candidates.append(Path(meipass) / "doc" / "pictures" / "AarVaaken.png")
            candidates.append(Path(__file__).resolve().parent / "doc" / "pictures" / "AarVaaken.png")

            pic_path = next((p for p in candidates if p.exists()), None)
            if pic_path is None:
                return None

            img = Image.open(str(pic_path))
            # Auto-crop near-white kanter (samme prinsipp som splash).
            try:
                gray = img.convert("L")
                bw = gray.point(lambda p: 255 if p < 250 else 0)
                bbox = bw.getbbox()
                if bbox:
                    img = img.crop(bbox)
            except Exception:
                pass

            # Skaler til ~40% av skjermbredden, behold aspekt-ratio.
            try:
                screen_w = self.winfo_screenwidth()
            except Exception:
                screen_w = 1280
            target_w = int(screen_w * 0.40)
            ratio = target_w / img.width
            target_h = int(img.height * ratio)
            img = img.resize((target_w, target_h), Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def hide_admin_landing(self) -> None:
        """Skjul landing-overlayen så det egentlige admin-innholdet vises."""
        landing = getattr(self, "_landing_frame", None)
        if landing is None:
            return
        try:
            landing.place_forget()
        except Exception:
            pass

    def show_admin_landing(self) -> None:
        """Vis landing-overlayen igjen (f.eks. ved sesjons-låsing)."""
        landing = getattr(self, "_landing_frame", None)
        if landing is None:
            return
        try:
            landing.place(relx=0, rely=0, relwidth=1, relheight=1)
            landing.lift()
        except Exception:
            pass

    def _on_landing_unlock(self) -> None:
        """Klikk på 'Gå til Admin' (eller Enter i passord-feltet) — valider
        passordet fra input-feltet og lås opp admin ved riktig passord."""
        var = getattr(self, "_landing_password_var", None)
        password = ""
        try:
            password = (var.get() if var is not None else "") or ""
        except Exception:
            password = ""

        if not password:
            # Sett fokus i passord-feltet så bruker ser hvor de skal skrive.
            entry = getattr(self, "_landing_password_entry", None)
            if entry is not None:
                try:
                    entry.focus_set()
                except Exception:
                    pass
            return

        # Hent passord-konstant fra ui_main (faller tilbake på "123").
        admin_password = "123"
        try:
            admin_password = getattr(
                __import__("ui_main"), "_ADMIN_PASSWORD", admin_password
            )
        except Exception:
            pass

        if password == admin_password:
            try:
                app = self.winfo_toplevel()
                app._admin_unlocked = True
            except Exception:
                pass
            # Tøm feltet før vi gjemmer landing — slik at neste tilbakekomst
            # (hvis lås gjenopptas) starter blankt.
            try:
                if var is not None:
                    var.set("")
            except Exception:
                pass
            self.hide_admin_landing()
            return

        # Feil passord — vis melding og tøm feltet for ny innskriving.
        try:
            if messagebox is not None:
                messagebox.showerror("Admin", "Feil passord.", parent=self)
        except Exception:
            pass
        try:
            if var is not None:
                var.set("")
        except Exception:
            pass
        entry = getattr(self, "_landing_password_entry", None)
        if entry is not None:
            try:
                entry.focus_set()
            except Exception:
                pass

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

    def show_a07_rulebook(self, rule_id: object | None = None) -> None:
        notebook = getattr(self, "_notebook", None)
        rulebook_editor = getattr(self, "_rulebook_editor", None)
        if notebook is not None and rulebook_editor is not None:
            try:
                notebook.select(rulebook_editor)
            except Exception:
                pass
        reload_editor = getattr(rulebook_editor, "reload", None)
        if callable(reload_editor):
            try:
                reload_editor(select_key=rule_id)
            except TypeError:
                try:
                    reload_editor()
                except Exception:
                    pass
            except Exception:
                pass
        if self._status_var is not None:
            self._status_var.set("A07-regler er primaer flate for A07-aliaser, ekskluderinger og basis.")

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

    def _on_open_monitoring(self) -> None:
        """Åpne ytelsesmonitor-popup (src/monitoring/dashboard.py)."""
        try:
            from src.monitoring.dashboard import open_as_popup
        except Exception as exc:
            if messagebox is not None:
                try:
                    messagebox.showerror(
                        "Ytelsesmonitor",
                        f"Kunne ikke åpne ytelsesmonitor: {exc}",
                    )
                except Exception:
                    pass
            return
        try:
            open_as_popup(self.winfo_toplevel())
        except Exception as exc:
            if messagebox is not None:
                try:
                    messagebox.showerror(
                        "Ytelsesmonitor",
                        f"Kunne ikke åpne ytelsesmonitor: {exc}",
                    )
                except Exception:
                    pass

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
