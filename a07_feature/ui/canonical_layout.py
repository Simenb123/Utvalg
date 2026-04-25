from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .control_layout import A07PageControlLayoutMixin
from .groups_popup import A07PageGroupsPopupMixin
from .support_layout import A07PageSupportLayoutMixin


class A07PageCanonicalUiMixin(
    A07PageControlLayoutMixin,
    A07PageSupportLayoutMixin,
    A07PageGroupsPopupMixin,
):
    """Canonical A07 layout.

    Guided workspace with fixed A07/RF-1022 work surfaces.
    """

    def _build_ui_canonical(self) -> None:
        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="Last A07", command=self._load_a07_clicked).pack(side="left")
        ttk.Button(toolbar, text="Oppdater", command=self._refresh_clicked).pack(side="left", padx=(6, 0))
        ttk.Label(toolbar, text="Beløpsbasis:").pack(side="right", padx=(12, 4))
        self.basis_widget = ttk.Combobox(
            toolbar,
            state="readonly",
            width=10,
            values=[self._basis_labels[key] for key in self._basis_labels],
            textvariable=self.basis_var,
        )
        self.basis_widget.pack(side="right")
        self.basis_widget.bind("<<ComboboxSelected>>", lambda _event: self._on_basis_changed())

        tools_btn = ttk.Menubutton(toolbar, text="Verktøy")
        tools_menu = self._build_tools_menu(tools_btn)
        tools_btn["menu"] = tools_menu
        tools_btn.pack(side="left", padx=(12, 0))
        ttk.Label(
            toolbar,
            textvariable=self.summary_var,
            style="Muted.TLabel",
        ).pack(side="left", fill="x", expand=True, padx=(12, 0))

        workspace_host = ttk.Frame(self, padding=(8, 0, 8, 8))
        workspace_host.pack(fill="both", expand=True)

        tab_control = ttk.Frame(workspace_host)
        tab_control.pack(fill="both", expand=True)
        self.tab_control = tab_control

        control_workspace = ttk.Frame(tab_control)
        control_workspace.pack(fill="both", expand=True, pady=(2, 0))
        self.control_workspace = control_workspace

        control_vertical = ttk.Panedwindow(control_workspace, orient="vertical")
        control_vertical.pack(fill="both", expand=True)
        control_top_host = ttk.Frame(control_vertical)
        control_lower = ttk.Frame(control_vertical)
        control_vertical.add(control_top_host, weight=5)
        control_vertical.add(control_lower, weight=2)
        self.control_vertical_panes = control_vertical
        self.control_lower_panel = control_lower

        self._build_control_top_panel(control_top_host)
        self._build_control_status_panel(control_lower)

        lower_body = ttk.Panedwindow(control_lower, orient="horizontal")
        lower_body.pack(fill="both", expand=True, pady=(2, 0))
        self.control_lower_body = lower_body

        suggestions_host = ttk.LabelFrame(lower_body, text="Forslag", padding=(6, 6))
        accounts_host = ttk.LabelFrame(lower_body, text="Koblinger", padding=(6, 6))
        lower_body.add(suggestions_host, weight=1)
        lower_body.add(accounts_host, weight=1)
        self.control_groups_panel = None
        self._groups_popup = None
        self.tree_groups = None
        self.btn_create_group = None
        self.btn_rename_group = None
        self.btn_remove_group = None
        self.btn_focus_group = None

        self._build_support_workspace(suggestions_host, accounts_host)
        self._bind_canonical_events()

        self._sync_control_alternative_view()
        sync_work_level_ui = getattr(self, "_sync_control_work_level_ui", None)
        if callable(sync_work_level_ui):
            sync_work_level_ui()
        self._set_control_advanced_visible(False)
        self._set_control_details_visible(True)
        self._sync_control_panel_visibility()
        self._sync_groups_panel_visibility()

    @property
    def _basis_labels(self):
        from ..page_a07_constants import _BASIS_LABELS

        return _BASIS_LABELS

    def _build_tools_menu(self, tools_btn) -> object:
        tools_menu = tk.Menu(tools_btn, tearoff=0)
        tools_menu.add_command(label="Avansert mapping", command=self._open_manual_mapping_clicked)
        tools_menu.add_command(label="Eksporter", command=self._export_clicked)
        tools_menu.add_command(
            label="Åpne saldobalanse",
            command=lambda: self._open_saldobalanse_workspace(status_text="Apnet Saldobalanse."),
        )
        tools_menu.add_command(label="Kilder...", command=self._open_source_overview)
        tools_menu.add_command(label="Kontrolloppstilling...", command=self._open_control_statement_window)
        tools_menu.add_separator()
        tools_menu.add_command(label="Bruk aktiv saldobalanse", command=self._sync_active_tb_clicked)
        tools_menu.add_separator()
        tools_menu.add_command(label="Last mapping", command=self._load_mapping_clicked)
        tools_menu.add_command(label="Lagre mapping", command=self._save_mapping_clicked)
        tools_menu.add_command(label="Vis mappinger", command=self._open_mapping_overview)
        advanced_menu = tk.Menu(tools_menu, tearoff=0)
        advanced_menu.add_command(label="Last regelsett", command=self._load_rulebook_clicked)
        tools_menu.add_cascade(label="Avansert", menu=advanced_menu)
        tools_menu.add_command(label="A07-regler...", command=self._open_a07_rulebook_admin)
        return tools_menu


__all__ = ["A07PageCanonicalUiMixin"]
