"""Dialog for å koble kontoer/regnskapslinjer til revisjonshandlinger.

Leser handlinger fra CRMSystem-databasen via ``crmsystem_actions`` og lagrer
valgte koblinger via ``regnskap_client_overrides``. Dialogen er modal og
viser eksisterende koblinger som forhåndskryssede rader.
"""

from __future__ import annotations

from typing import Any, Sequence


def _load_team_choices() -> list[dict]:
    """Les teammedlemmer fra config/team.json. Returner tom liste ved feil."""
    try:
        import team_config as _tc
        return list(_tc.list_team_members())
    except Exception:
        return []


def _current_user_initials() -> str:
    try:
        import team_config as _tc
        return (_tc.current_visena_initials() or "").strip().upper()
    except Exception:
        return ""


def open_action_link_dialog(
    *,
    parent: Any,
    client: str,
    year: str,
    kind: str,
    entity_key: str,
    entity_label: str,
    on_saved: Any = None,
) -> None:
    """Åpne dialog for å koble én konto eller regnskapslinje til handlinger.

    Parameters
    ----------
    kind : "account" | "rl"
        Styrer hvilken lagringsfunksjon som brukes.
    entity_key : str
        Konto-nr eller regnr (lagres som nøkkel).
    entity_label : str
        Leselig tittel vist øverst i dialogen (f.eks. "1920 Bank").
    on_saved : callable, optional
        Kalles uten argumenter etter vellykket lagring.
    """
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except Exception:
        return

    if kind not in ("account", "rl"):
        return
    if not client or not year or not entity_key:
        return

    try:
        from crmsystem_actions import load_audit_actions
    except Exception as exc:
        messagebox.showerror("Handlinger", f"Kan ikke laste handlinger: {exc}", parent=parent)
        return

    result = load_audit_actions(client, year)
    if result.error:
        messagebox.showerror("Handlinger", result.error, parent=parent)
        return
    if not result.actions:
        messagebox.showinfo(
            "Handlinger",
            "Fant ingen revisjonshandlinger for denne klienten/året i CRM.",
            parent=parent,
        )
        return

    try:
        import src.shared.regnskap.client_overrides as _rco
    except Exception as exc:
        messagebox.showerror("Handlinger", f"Kan ikke åpne lagring: {exc}", parent=parent)
        return

    if kind == "account":
        existing_map = _rco.load_account_action_links(client, year)
    else:
        existing_map = _rco.load_rl_action_links(client, year)
    existing_links = existing_map.get(str(entity_key), [])
    existing_ids: set[int] = {int(lnk.get("action_id", 0)) for lnk in existing_links}
    existing_assigned: dict[int, str] = {
        int(lnk.get("action_id", 0)): str(lnk.get("assigned_to", "") or "").strip().upper()
        for lnk in existing_links
        if lnk.get("assigned_to")
    }

    team_choices = _load_team_choices()
    label_by_initials: dict[str, str] = {
        str(c.get("initials") or "").upper(): str(c.get("label") or "")
        for c in team_choices
        if c.get("initials")
    }
    current_initials = _current_user_initials()

    win = tk.Toplevel(parent)
    win.title("Koble til revisjonshandling")
    win.transient(parent)
    try:
        win.grab_set()
    except Exception:
        pass
    win.geometry("980x600")

    header = ttk.Frame(win, padding=(12, 10, 12, 6))
    header.pack(fill="x")
    ttk.Label(
        header,
        text=f"Koble «{entity_label}» til handlinger",
        font=("Segoe UI", 11, "bold"),
    ).pack(anchor="w")
    ttk.Label(
        header,
        text=(
            f"Klient: {result.engagement.client_name if result.engagement else client}"
            f"   År: {year}"
        ),
        foreground="#555",
    ).pack(anchor="w")

    body = ttk.Frame(win, padding=(12, 4, 12, 4))
    body.pack(fill="both", expand=True)
    body.rowconfigure(0, weight=1)
    body.columnconfigure(0, weight=1)

    cols = ("sel", "area", "type", "procedure", "owner", "assigned", "status")
    tree = ttk.Treeview(body, columns=cols, show="headings", selectmode="browse")
    tree.grid(row=0, column=0, sticky="nsew")
    vsb = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
    vsb.grid(row=0, column=1, sticky="ns")
    tree.configure(yscrollcommand=vsb.set)

    tree.heading("sel", text="")
    tree.heading("area", text="Område")
    tree.heading("type", text="Type")
    tree.heading("procedure", text="Prosedyre")
    tree.heading("owner", text="Eier (CRM)")
    tree.heading("assigned", text="Tilordnet")
    tree.heading("status", text="Status")

    tree.column("sel", width=34, anchor="center", stretch=False)
    tree.column("area", width=130, anchor="w")
    tree.column("type", width=80, anchor="w")
    tree.column("procedure", width=320, anchor="w")
    tree.column("owner", width=110, anchor="w")
    tree.column("assigned", width=80, anchor="center")
    tree.column("status", width=100, anchor="w")

    tree.tag_configure("checked", background="#E3F5E1")

    # action_id → AuditAction
    actions_by_id: dict[int, Any] = {a.action_id: a for a in result.actions}
    # item_id → action_id
    row_to_action: dict[str, int] = {}
    checked: set[int] = set(existing_ids)
    assigned_map: dict[int, str] = dict(existing_assigned)

    type_label = {"control": "Kontroll", "substantive": "Substans"}

    def _refresh_row(item_id: str) -> None:
        aid = row_to_action.get(item_id)
        if aid is None:
            return
        action = actions_by_id[aid]
        mark = "✓" if aid in checked else ""
        assigned = assigned_map.get(aid, "") if aid in checked else ""
        tree.item(
            item_id,
            values=(
                mark,
                action.area_name,
                type_label.get(action.action_type, action.action_type),
                action.procedure_name,
                action.owner,
                assigned,
                action.status,
            ),
            tags=("checked",) if aid in checked else (),
        )

    for action in result.actions:
        item_id = tree.insert("", "end", values=("", "", "", "", "", "", ""))
        row_to_action[item_id] = action.action_id
        _refresh_row(item_id)

    status = ttk.Frame(win, padding=(12, 0, 12, 4))
    status.pack(fill="x")
    status_var = tk.StringVar()

    def _update_status() -> None:
        status_var.set(f"{len(checked)} av {len(result.actions)} handlinger valgt")

    _update_status()
    ttk.Label(status, textvariable=status_var, foreground="#555").pack(anchor="w")

    def _toggle(item_id: str) -> None:
        aid = row_to_action.get(item_id)
        if aid is None:
            return
        if aid in checked:
            checked.discard(aid)
        else:
            checked.add(aid)
            # Nye koblinger får default tilordning = nåværende bruker
            if aid not in assigned_map and current_initials:
                assigned_map[aid] = current_initials
        _refresh_row(item_id)
        _update_status()

    def _toggle_current() -> None:
        sel = tree.selection()
        if sel:
            _toggle(sel[0])

    def _on_click(event: Any) -> None:
        item = tree.identify_row(event.y)
        if not item:
            return
        col = tree.identify_column(event.x)
        tree.selection_set(item)
        if col == "#1":
            _toggle(item)

    tree.bind("<Button-1>", _on_click)
    tree.bind("<space>", lambda e: (_toggle_current(), "break")[1])
    tree.bind("<Return>", lambda e: (_toggle_current(), "break")[1])

    # ── Tilordne-bar ──
    assign_bar = ttk.Frame(win, padding=(12, 0, 12, 4))
    assign_bar.pack(fill="x")
    ttk.Label(assign_bar, text="Tilordnet valgte:").pack(side="left")

    assign_values: list[str] = ["(ingen)"]
    label_to_initials: dict[str, str] = {"(ingen)": ""}
    for c in team_choices:
        lbl = str(c.get("label") or "")
        initials = str(c.get("initials") or "").upper()
        if lbl and initials:
            assign_values.append(lbl)
            label_to_initials[lbl] = initials

    default_label = label_by_initials.get(current_initials, "")
    var_assign = tk.StringVar(value=default_label or "(ingen)")
    cmb_assign = ttk.Combobox(
        assign_bar, textvariable=var_assign, values=assign_values,
        state="readonly", width=32,
    )
    cmb_assign.pack(side="left", padx=(6, 6))

    def _apply_assignment_to_checked() -> None:
        target = label_to_initials.get(var_assign.get(), "")
        for aid in list(checked):
            if target:
                assigned_map[aid] = target
            else:
                assigned_map.pop(aid, None)
        for item_id in tree.get_children():
            _refresh_row(item_id)

    ttk.Button(
        assign_bar, text="Tilordne valgte", command=_apply_assignment_to_checked,
    ).pack(side="left")

    def _save_and_close() -> None:
        payload_meta: list[dict] = []
        for aid in sorted(checked):
            action = actions_by_id.get(aid)
            if action is None:
                continue
            entry = {
                "action_id": aid,
                "procedure_name": action.procedure_name,
                "area_name": action.area_name,
                "action_type": action.action_type,
            }
            assignee = assigned_map.get(aid, "")
            if assignee:
                entry["assigned_to"] = assignee
            payload_meta.append(entry)
        try:
            if kind == "account":
                _rco.set_account_action_links(client, year, str(entity_key), payload_meta)
            else:
                _rco.set_rl_action_links(client, year, str(entity_key), payload_meta)
        except Exception as exc:
            messagebox.showerror("Handlinger", f"Kunne ikke lagre: {exc}", parent=win)
            return
        if on_saved:
            try:
                on_saved()
            except Exception:
                pass
        win.destroy()

    def _select_all() -> None:
        for aid in actions_by_id:
            checked.add(aid)
            if aid not in assigned_map and current_initials:
                assigned_map[aid] = current_initials
        for item_id in tree.get_children():
            _refresh_row(item_id)
        _update_status()

    def _clear_all() -> None:
        checked.clear()
        for item_id in tree.get_children():
            _refresh_row(item_id)
        _update_status()

    buttons = ttk.Frame(win, padding=(12, 4, 12, 12))
    buttons.pack(fill="x")
    ttk.Button(buttons, text="Merk alle", command=_select_all).pack(side="left")
    ttk.Button(buttons, text="Fjern alle", command=_clear_all).pack(side="left", padx=(6, 0))
    ttk.Button(buttons, text="Avbryt", command=win.destroy).pack(side="right")
    ttk.Button(buttons, text="Lagre", command=_save_and_close).pack(side="right", padx=(0, 6))

    try:
        win.wait_window()
    except Exception:
        pass


def summarize_links(links: Sequence[dict]) -> str:
    """Kort sammendrag brukt i meny-labels: '3 handlinger'."""
    n = len(links)
    if n == 0:
        return ""
    if n == 1:
        return "1 handling"
    return f"{n} handlinger"
