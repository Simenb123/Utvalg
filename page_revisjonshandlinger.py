"""Revisjonshandlinger tab — shows audit actions from CRMSystem.

Read-only view of substantive and control audit procedures for the
active client, loaded from the shared CRM database.  Each action is
matched to a regnskapslinje (financial statement line) when possible.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

import action_workpaper_store as workpaper_store
from action_workpaper_store import ActionWorkpaper


class RevisjonshandlingerPage(ttk.Frame):
    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent, padding=0)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self._client: str | None = None
        self._year: str | None = None
        self._actions: list[Any] = []
        self._engagement: Any = None
        self._match_by_action_id: dict[int, Any] = {}  # action_id → ActionMatch
        self._local_assignments: dict[int, str] = {}  # action_id → "SB" / "SB, TN"
        self._local_link_counts: dict[int, int] = {}  # action_id → antall lokale koblinger
        self._workpapers: dict[int, ActionWorkpaper] = {}  # action_id → bekreftelse
        self._rl_list: list[Any] = []  # cache av RegnskapslinjeInfo for dropdown

        self.var_status = tk.StringVar(value="Last inn klient for å se revisjonshandlinger.")
        self.var_filter_type = tk.StringVar(value="Alle")
        self.var_filter_status = tk.StringVar(value="Alle")
        self.var_filter_area = tk.StringVar(value="Alle")
        self.var_filter_regnr = tk.StringVar(value="Alle")
        self.var_search = tk.StringVar()

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ── Top bar ──
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        top.columnconfigure(10, weight=1)

        ttk.Label(top, textvariable=self.var_status, foreground="#667085").grid(row=0, column=0, sticky="w")
        self._btn_confirm = ttk.Button(
            top, text="Bekreft RL",
            command=self._on_confirm_current, state="disabled",
        )
        self._btn_confirm.grid(row=0, column=8, sticky="e", padx=(6, 0))
        self._btn_override = ttk.Button(
            top, text="Velg RL…",
            command=self._on_override_regnr, state="disabled",
        )
        self._btn_override.grid(row=0, column=9, sticky="e", padx=(6, 0))
        self._btn_clear = ttk.Button(
            top, text="Fjern bekreftelse",
            command=self._on_clear_confirmation, state="disabled",
        )
        self._btn_clear.grid(row=0, column=10, sticky="e", padx=(6, 0))
        ttk.Button(top, text="Oppdater", command=self._refresh).grid(row=0, column=11, sticky="e", padx=(6, 0))

        # Filters
        filt = ttk.Frame(self)
        filt.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 0))

        ttk.Label(filt, text="Type:").pack(side="left")
        cb_type = ttk.Combobox(filt, textvariable=self.var_filter_type, state="readonly",
                               values=["Alle", "substantive", "control"], width=12)
        cb_type.pack(side="left", padx=(2, 12))
        cb_type.bind("<<ComboboxSelected>>", lambda _: self._apply_filter())

        ttk.Label(filt, text="Status:").pack(side="left")
        self._cb_status = ttk.Combobox(filt, textvariable=self.var_filter_status, state="readonly",
                                       values=["Alle"], width=14)
        self._cb_status.pack(side="left", padx=(2, 12))
        self._cb_status.bind("<<ComboboxSelected>>", lambda _: self._apply_filter())

        ttk.Label(filt, text="Område:").pack(side="left")
        self._cb_area = ttk.Combobox(filt, textvariable=self.var_filter_area, state="readonly",
                                     values=["Alle"], width=24)
        self._cb_area.pack(side="left", padx=(2, 12))
        self._cb_area.bind("<<ComboboxSelected>>", lambda _: self._apply_filter())

        ttk.Label(filt, text="Regnskapslinje:").pack(side="left")
        self._cb_regnr = ttk.Combobox(filt, textvariable=self.var_filter_regnr, state="readonly",
                                      values=["Alle"], width=28)
        self._cb_regnr.pack(side="left", padx=(2, 12))
        self._cb_regnr.bind("<<ComboboxSelected>>", lambda _: self._apply_filter())

        ttk.Label(filt, text="Søk:").pack(side="left")
        ent_search = ttk.Entry(filt, textvariable=self.var_search, width=20)
        ent_search.pack(side="left", padx=(2, 0))
        ent_search.bind("<KeyRelease>", lambda _: self._apply_filter())

        # ── Treeview ──
        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(4, 0))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        cols = ("regnr", "regnskapslinje", "kilde", "omraade", "type", "handling", "timing",
                "eier", "tilordnet", "status", "frist")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")

        self._tree.heading("regnr", text="Regnr")
        self._tree.heading("regnskapslinje", text="Regnskapslinje")
        self._tree.heading("kilde", text="Kilde")
        self._tree.heading("omraade", text="Område")
        self._tree.heading("type", text="Type")
        self._tree.heading("handling", text="Handling")
        self._tree.heading("timing", text="Timing")
        self._tree.heading("eier", text="Eier (CRM)")
        self._tree.heading("tilordnet", text="Tilordnet")
        self._tree.heading("status", text="Status")
        self._tree.heading("frist", text="Frist")

        self._tree.column("regnr", width=50, minwidth=40)
        self._tree.column("regnskapslinje", width=180, minwidth=100)
        self._tree.column("kilde", width=90, minwidth=70, anchor="center")
        self._tree.column("omraade", width=150, minwidth=80)
        self._tree.column("type", width=90, minwidth=60)
        self._tree.column("handling", width=300, minwidth=150)
        self._tree.column("timing", width=80, minwidth=50)
        self._tree.column("eier", width=130, minwidth=80)
        self._tree.column("tilordnet", width=80, minwidth=60, anchor="center")
        self._tree.column("status", width=100, minwidth=60)
        self._tree.column("frist", width=90, minwidth=70)

        self._tree.tag_configure("wp_confirmed", background="#E6F4EA")
        self._tree.tag_configure("wp_auto", background="#FFFFFF")
        self._tree.tag_configure("wp_unmatched", background="#FFF4DD")

        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=yscroll.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")

        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # ── Detail panel ──
        detail = ttk.LabelFrame(self, text="Detaljer", padding=6)
        detail.grid(row=3, column=0, sticky="ew", padx=8, pady=(4, 8))
        detail.columnconfigure(0, weight=1)

        self._detail_var = tk.StringVar(value="")
        self._detail_label = ttk.Label(detail, textvariable=self._detail_var, wraplength=900, anchor="w", justify="left")
        self._detail_label.grid(row=0, column=0, sticky="w")

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def on_client_changed(self, client: str | None, year: str | None) -> None:
        self._client = client
        self._year = year
        self._refresh()

    def filter_by_regnr(self, regnr: int | str | None) -> None:
        """Sett regnskapslinje-filteret til matchende verdi og kjør filter."""
        if regnr in (None, ""):
            self.var_filter_regnr.set("Alle")
            self._apply_filter()
            return
        target = str(regnr).strip()
        values = self._cb_regnr.cget("values") or []
        match = "Alle"
        for val in values:
            head = str(val).split()[0] if val else ""
            if head == target:
                match = str(val)
                break
        self.var_filter_regnr.set(match)
        self._apply_filter()

    def _refresh(self) -> None:
        if not self._client or not self._year:
            self._actions = []
            self._engagement = None
            self._match_by_action_id = {}
            self._workpapers = {}
            self._rl_list = []
            self._tree.delete(*self._tree.get_children())
            self.var_status.set("Last inn klient for å se revisjonshandlinger.")
            self._detail_var.set("")
            self._update_action_buttons()
            return

        self.var_status.set("Henter handlinger fra CRM ...")
        self.update_idletasks()

        try:
            from crmsystem_actions import load_audit_actions
            result = load_audit_actions(self._client, self._year)
        except Exception as exc:
            self.var_status.set(f"Feil: {exc}")
            return

        if result.error:
            self.var_status.set(result.error)
            self._actions = []
            self._engagement = None
            self._match_by_action_id = {}
            self._tree.delete(*self._tree.get_children())
            return

        self._engagement = result.engagement
        self._actions = result.actions

        # Run regnskapslinje matching
        self._match_by_action_id = {}
        self._run_matching()

        # Load workpaper confirmations (revisors overstyringer)
        try:
            self._workpapers = workpaper_store.load_workpapers(self._client, self._year)
        except Exception:
            self._workpapers = {}

        # Load local assignments (konto- og RL-koblinger per action_id)
        self._load_local_assignments()

        # Update filter dropdowns
        areas = sorted({a.area_name for a in self._actions if a.area_name})
        statuses = sorted({a.status for a in self._actions if a.status})
        self._cb_area.configure(values=["Alle"] + areas)
        self._cb_status.configure(values=["Alle"] + statuses)

        # Build regnr filter values
        regnr_labels = sorted(
            {f"{m.regnr} {m.regnskapslinje}" for m in self._match_by_action_id.values() if m.regnr},
            key=lambda s: int(s.split()[0]) if s.split()[0].isdigit() else 0,
        )
        self._cb_regnr.configure(values=["Alle", "Uten match"] + regnr_labels)

        self._apply_filter()

        n = len(self._actions)
        matched = sum(1 for m in self._match_by_action_id.values() if m.regnr)
        eng = result.engagement
        label = f"{eng.client_name} ({eng.client_number}) — {eng.engagement_name} — {n} handlinger ({matched} matchet)"
        self.var_status.set(label)

    def _load_local_assignments(self) -> None:
        """Samle ``assigned_to`` per action_id fra konto- og RL-koblinger."""
        self._local_assignments = {}
        self._local_link_counts = {}
        if not self._client or not self._year:
            return
        try:
            import regnskap_client_overrides as _rco
        except Exception:
            return
        try:
            account_map = _rco.load_account_action_links(self._client, self._year)
        except Exception:
            account_map = {}
        try:
            rl_map = _rco.load_rl_action_links(self._client, self._year)
        except Exception:
            rl_map = {}

        per_action: dict[int, list[str]] = {}
        counts: dict[int, int] = {}
        for links in list(account_map.values()) + list(rl_map.values()):
            for lnk in links:
                try:
                    aid = int(lnk.get("action_id") or 0)
                except Exception:
                    continue
                if aid <= 0:
                    continue
                counts[aid] = counts.get(aid, 0) + 1
                assigned = str(lnk.get("assigned_to") or "").strip().upper()
                if assigned:
                    per_action.setdefault(aid, [])
                    if assigned not in per_action[aid]:
                        per_action[aid].append(assigned)
        self._local_assignments = {aid: ", ".join(vals) for aid, vals in per_action.items()}
        self._local_link_counts = counts

    def _run_matching(self) -> None:
        """Match actions to regnskapslinjer."""
        try:
            from crmsystem_action_matching import (
                RegnskapslinjeInfo,
                match_actions_to_regnskapslinjer,
            )
            from regnskap_config import load_regnskapslinjer

            df = load_regnskapslinjer()
            rl_list = [
                RegnskapslinjeInfo(
                    nr=str(row["nr"]).strip(),
                    regnskapslinje=str(row["regnskapslinje"]).strip(),
                )
                for _, row in df.iterrows()
            ]
            matches = match_actions_to_regnskapslinjer(self._actions, rl_list)
            self._match_by_action_id = {m.action.action_id: m for m in matches}
            self._rl_list = rl_list
        except Exception:
            # Matching is optional — don't block the tab if it fails
            self._match_by_action_id = {}
            self._rl_list = []

    def _apply_filter(self) -> None:
        self._tree.delete(*self._tree.get_children())

        type_filter = self.var_filter_type.get()
        status_filter = self.var_filter_status.get()
        area_filter = self.var_filter_area.get()
        regnr_filter = self.var_filter_regnr.get()
        search = self.var_search.get().strip().lower()

        shown = 0
        for a in self._actions:
            if type_filter != "Alle" and a.action_type != type_filter:
                continue
            if status_filter != "Alle" and a.status != status_filter:
                continue
            if area_filter != "Alle" and a.area_name != area_filter:
                continue

            # Regnskapslinje (bekreftet > auto)
            match = self._match_by_action_id.get(a.action_id)
            auto_regnr = match.regnr if match else ""
            auto_rl = match.regnskapslinje if match else ""
            regnr, rl_name, source = workpaper_store.resolve_effective_regnr(
                a.action_id, auto_regnr, auto_rl, self._workpapers,
            )

            if regnr_filter == "Uten match" and regnr:
                continue
            if regnr_filter not in ("Alle", "Uten match"):
                filter_nr = regnr_filter.split()[0] if regnr_filter else ""
                if regnr != filter_nr:
                    continue

            if search and search not in a.procedure_name.lower() and search not in a.area_name.lower() and search not in (a.owner or "").lower():
                continue

            status_display = a.status or ""
            tilordnet = self._local_assignments.get(a.action_id, "")
            kilde_label = {
                "confirmed": "bekreftet",
                "auto": "auto",
            }.get(source, "")
            tag = {
                "confirmed": "wp_confirmed",
                "auto": "wp_auto",
            }.get(source, "wp_unmatched")
            self._tree.insert("", "end", iid=str(a.action_id), values=(
                regnr,
                rl_name,
                kilde_label,
                a.area_name,
                a.action_type,
                a.procedure_name,
                a.timing,
                a.owner,
                tilordnet,
                status_display,
                a.due_date,
            ), tags=(tag,))
            shown += 1

        # Update status with filter count if different from total
        if shown != len(self._actions) and self._engagement:
            self.var_status.set(
                f"{self._engagement.client_name} — viser {shown} av {len(self._actions)} handlinger"
            )

    def _on_select(self, _event: tk.Event | None = None) -> None:
        sel = self._tree.selection()
        if not sel:
            self._detail_var.set("")
            self._update_action_buttons()
            return

        action_id = int(sel[0])
        action = next((a for a in self._actions if a.action_id == action_id), None)
        if not action:
            self._detail_var.set("")
            self._update_action_buttons()
            return

        lines = [f"{action.area_name}  /  {action.procedure_name}"]

        # Show match info (auto)
        match = self._match_by_action_id.get(action.action_id)
        if match and match.regnr:
            method_labels = {"prefix": "nummerprefix", "alias": "nøkkelord", "fuzzy": "fuzzy-match"}
            method_label = method_labels.get(match.match_method, match.match_method)
            lines.append(
                f"Auto-match: {match.regnr} {match.regnskapslinje}  "
                f"({method_label}, {match.confidence:.0%})"
            )
        else:
            lines.append("Auto-match: (ingen)")

        # Show workpaper confirmation
        wp = self._workpapers.get(action.action_id)
        if wp:
            rl_part = f" {wp.confirmed_regnskapslinje}" if wp.confirmed_regnskapslinje else ""
            who = f" av {wp.confirmed_by}" if wp.confirmed_by else ""
            when = f" ({wp.confirmed_at})" if wp.confirmed_at else ""
            lines.append(f"Bekreftet: {wp.confirmed_regnr}{rl_part}{who}{when}")
            if wp.note:
                lines.append(f"Notat: {wp.note}")

        if action.owner:
            lines.append(f"Eier (CRM): {action.owner}")
        tilordnet = self._local_assignments.get(action.action_id, "")
        if tilordnet:
            n_links = self._local_link_counts.get(action.action_id, 0)
            suffix = f" ({n_links} lokale koblinger)" if n_links else ""
            lines.append(f"Tilordnet lokalt: {tilordnet}{suffix}")
        if action.timing:
            lines.append(f"Timing: {action.timing}")
        if action.status:
            lines.append(f"Status: {action.status}")
        if action.due_date:
            lines.append(f"Frist: {action.due_date}")
        if action.comments:
            lines.append("")
            lines.append("Kommentarer:")
            for c in action.comments:
                by = f" ({c.created_by})" if c.created_by else ""
                lines.append(f"  {c.created_at}{by}: {c.comment}")

        self._detail_var.set("\n".join(lines))
        self._update_action_buttons()

    # ------------------------------------------------------------------
    # Workpaper actions
    # ------------------------------------------------------------------

    def _update_action_buttons(self) -> None:
        sel = self._tree.selection()
        action_id = int(sel[0]) if sel else 0
        match = self._match_by_action_id.get(action_id) if action_id else None
        has_auto = bool(match and match.regnr)
        has_wp = action_id in self._workpapers
        client_ready = bool(self._client and self._year)

        def _state(enabled: bool) -> str:
            return "normal" if enabled else "disabled"

        self._btn_confirm.configure(state=_state(client_ready and action_id > 0 and has_auto))
        self._btn_override.configure(state=_state(client_ready and action_id > 0 and bool(self._rl_list)))
        self._btn_clear.configure(state=_state(client_ready and has_wp))

    def _selected_action(self):
        sel = self._tree.selection()
        if not sel:
            return None
        action_id = int(sel[0])
        return next((a for a in self._actions if a.action_id == action_id), None)

    def _persist_confirmation(self, action_id: int, regnr: str, regnskapslinje: str) -> None:
        if not self._client or not self._year:
            return
        try:
            workpaper_store.confirm_regnr(
                self._client, self._year, action_id,
                regnr=regnr, regnskapslinje=regnskapslinje,
            )
        except Exception as exc:
            messagebox.showerror("Bekreft RL", f"Kunne ikke lagre bekreftelse: {exc}", parent=self)
            return
        self._workpapers = workpaper_store.load_workpapers(self._client, self._year)
        self._apply_filter()
        try:
            self._tree.selection_set(str(action_id))
            self._on_select()
        except Exception:
            self._update_action_buttons()

    def _on_confirm_current(self) -> None:
        action = self._selected_action()
        if not action:
            return
        match = self._match_by_action_id.get(action.action_id)
        if not match or not match.regnr:
            messagebox.showinfo(
                "Bekreft RL",
                "Ingen auto-match å bekrefte. Bruk 'Velg RL…' for å sette regnskapslinje manuelt.",
                parent=self,
            )
            return
        self._persist_confirmation(action.action_id, match.regnr, match.regnskapslinje)

    def _on_override_regnr(self) -> None:
        action = self._selected_action()
        if not action or not self._rl_list:
            return
        picked = _RegnrPickerDialog.ask(self, self._rl_list)
        if not picked:
            return
        regnr, regnskapslinje = picked
        self._persist_confirmation(action.action_id, regnr, regnskapslinje)

    def _on_clear_confirmation(self) -> None:
        action = self._selected_action()
        if not action or not self._client or not self._year:
            return
        if action.action_id not in self._workpapers:
            return
        try:
            workpaper_store.clear_confirmation(self._client, self._year, action.action_id)
        except Exception as exc:
            messagebox.showerror("Fjern bekreftelse", str(exc), parent=self)
            return
        self._workpapers = workpaper_store.load_workpapers(self._client, self._year)
        self._apply_filter()
        try:
            self._tree.selection_set(str(action.action_id))
            self._on_select()
        except Exception:
            self._update_action_buttons()


class _RegnrPickerDialog(tk.Toplevel):
    """Enkel dialog for å velge en regnskapslinje fra en lukket liste."""

    def __init__(self, parent: tk.Misc, rl_list) -> None:
        super().__init__(parent)
        self.title("Velg regnskapslinje")
        self.transient(parent)
        self.resizable(False, False)
        self._result: tuple[str, str] | None = None
        self._rl_list = list(rl_list)

        labels = [f"{rl.nr} — {rl.regnskapslinje}" for rl in self._rl_list]
        self._label_to_rl = {lbl: rl for lbl, rl in zip(labels, self._rl_list)}

        ttk.Label(self, text="Regnskapslinje:").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))
        self._var = tk.StringVar(value=labels[0] if labels else "")
        self._cb = ttk.Combobox(self, textvariable=self._var, values=labels, state="readonly", width=42)
        self._cb.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=2)

        btns = ttk.Frame(self)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", padx=8, pady=8)
        ttk.Button(btns, text="Avbryt", command=self._on_cancel).pack(side="right")
        ttk.Button(btns, text="Bekreft", command=self._on_ok).pack(side="right", padx=(0, 6))

        self.bind("<Return>", lambda _e: self._on_ok())
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self._cb.focus_set()
        self.grab_set()

    def _on_ok(self) -> None:
        label = self._var.get().strip()
        rl = self._label_to_rl.get(label)
        if rl is None:
            self._on_cancel()
            return
        self._result = (str(rl.nr).strip(), str(rl.regnskapslinje).strip())
        self.destroy()

    def _on_cancel(self) -> None:
        self._result = None
        self.destroy()

    @classmethod
    def ask(cls, parent: tk.Misc, rl_list) -> tuple[str, str] | None:
        if not rl_list:
            return None
        dlg = cls(parent, rl_list)
        parent.wait_window(dlg)
        return dlg._result
