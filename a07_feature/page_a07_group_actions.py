from __future__ import annotations

from typing import Sequence

from a07_feature import A07Group, canonical_a07_code

from .page_a07_env import simpledialog


class A07PageGroupActionsMixin:
    def _group_display_label(self, code: object) -> str:
        code_s = str(code or "").strip()
        group = (getattr(getattr(self, "workspace", None), "groups", {}) or {}).get(code_s)
        group_name = str(getattr(group, "group_name", "") or "").strip()
        return group_name or code_s

    def _create_group_from_selection(self) -> None:
        codes = self._groupable_selected_control_codes()
        self._create_group_from_codes(codes)

    def _create_group_from_codes(
        self,
        codes: Sequence[str],
        *,
        prompt_for_name: bool = False,
    ) -> str | None:
        codes = list(dict.fromkeys(str(code).strip() for code in (codes or ()) if str(code).strip()))
        if not codes:
            self._notify_inline("Marker minst én A07-kode for å opprette en gruppe.", focus_widget=self.tree_a07)
            return None

        existing_group_getter = getattr(self, "_existing_group_id_for_codes", None)
        existing_group_id = (
            str(existing_group_getter(codes) or "").strip()
            if callable(existing_group_getter)
            else ""
        )
        if existing_group_id:
            self._refresh_core(focus_code=existing_group_id)
            self._focus_control_code(existing_group_id)
            group = getattr(self.workspace, "groups", {}).get(existing_group_id)
            group_name = str(getattr(group, "group_name", "") or existing_group_id).strip()
            self.status_var.set(f"A07-gruppen finnes allerede: {group_name}.")
            return existing_group_id

        default_name = self._default_group_name(codes)
        group_name = default_name
        if prompt_for_name:
            name = simpledialog.askstring("A07-gruppe", "Navn på gruppen:", parent=self, initialvalue=default_name)
            if name is None:
                return None
            group_name = str(name).strip() or default_name

        group_id = self._next_group_id(codes)
        self.workspace.groups[group_id] = A07Group(
            group_id=group_id,
            group_name=group_name,
            member_codes=codes,
        )
        self._autosave_workspace_state()
        self._refresh_core(focus_code=group_id)
        self._focus_control_code(group_id)
        self.status_var.set(f"Opprettet A07-gruppe {group_name}.")
        return group_id

    def _a07_group_menu_choices(self) -> list[tuple[str, str]]:
        choices: list[tuple[str, str]] = []
        groups = getattr(getattr(self, "workspace", None), "groups", {}) or {}
        for group_id, group in groups.items():
            group_id_s = str(group_id or "").strip()
            if not group_id_s:
                continue
            group_name = str(getattr(group, "group_name", "") or group_id_s).strip()
            members = [
                str(code or "").strip()
                for code in (getattr(group, "member_codes", []) or [])
                if str(code or "").strip()
            ]
            suffix = f" ({len(members)} koder)" if members else ""
            choices.append((group_id_s, f"{group_name}{suffix}"))
        choices.sort(key=lambda item: (item[1].casefold(), item[0].casefold()))
        return choices

    def _add_selected_codes_to_group(self, group_id: str) -> str | None:
        return self._add_codes_to_group(group_id, self._groupable_selected_control_codes())

    def _add_codes_to_group(self, group_id: str, codes: Sequence[str]) -> str | None:
        old_group_id = str(group_id or "").strip()
        if not old_group_id:
            self._notify_inline("Velg en A07-gruppe først.", focus_widget=self.tree_a07)
            return None
        groups = getattr(self.workspace, "groups", {}) or {}
        group = groups.get(old_group_id)
        if group is None:
            self._notify_inline("Fant ikke valgt A07-gruppe.", focus_widget=self.tree_a07)
            return None

        existing_members = [
            canonical_a07_code(code)
            for code in (getattr(group, "member_codes", []) or [])
            if canonical_a07_code(code)
        ]
        member_keys = {code.casefold() for code in existing_members}
        added_members: list[str] = []
        for code in codes or ():
            code_s = canonical_a07_code(code)
            if not code_s or code_s.casefold() in member_keys:
                continue
            added_members.append(code_s)
            member_keys.add(code_s.casefold())

        if not added_members:
            self._notify_inline("Valgte A07-koder finnes allerede i gruppen.", focus_widget=self.tree_a07)
            return old_group_id

        updated_members = existing_members + added_members
        old_default_name = self._default_group_name(existing_members)
        current_name = str(getattr(group, "group_name", "") or old_group_id).strip()
        new_default_name = self._default_group_name(updated_members)
        new_group_id = self._next_group_id(updated_members)

        target_group = groups.get(new_group_id)
        if target_group is not None and new_group_id != old_group_id:
            target_group.member_codes = updated_members
            if not str(getattr(target_group, "group_name", "") or "").strip():
                target_group.group_name = new_default_name
            groups.pop(old_group_id, None)
            group = target_group
        else:
            groups.pop(old_group_id, None)
            group.group_id = new_group_id
            group.member_codes = updated_members
            if not current_name or current_name in {old_group_id, old_default_name}:
                group.group_name = new_default_name
            groups[new_group_id] = group

        if new_group_id != old_group_id:
            for account, mapped_code in list((getattr(self.workspace, "mapping", {}) or {}).items()):
                if str(mapped_code or "").strip() == old_group_id:
                    self.workspace.mapping[account] = new_group_id
            if old_group_id in self.workspace.locks:
                self.workspace.locks.discard(old_group_id)
                self.workspace.locks.add(new_group_id)
            if str(getattr(self.workspace, "selected_code", "") or "").strip() == old_group_id:
                self.workspace.selected_code = new_group_id

        added_label = ", ".join(added_members)
        self._autosave_workspace_state()
        self._refresh_core(focus_code=new_group_id)
        self._focus_control_code(new_group_id)
        self.status_var.set(f"La til {added_label} i A07-gruppen {group.group_name or new_group_id}.")
        return new_group_id

    def _rename_selected_group(self) -> None:
        group_id = self._selected_group_id()
        if not group_id:
            self._notify_inline("Velg en A07-gruppe først.", focus_widget=self.tree_groups)
            return
        group = self.workspace.groups.get(group_id)
        if group is None:
            self._notify_inline("Fant ikke valgt A07-gruppe.", focus_widget=self.tree_groups)
            return
        current_name = str(group.group_name or group_id).strip() or group_id
        name = simpledialog.askstring("A07-gruppe", "Nytt navn på gruppen:", parent=self, initialvalue=current_name)
        if name is None:
            return
        updated_name = str(name).strip() or current_name
        if updated_name == current_name:
            return
        group.group_name = updated_name
        self._autosave_workspace_state()
        self._refresh_core(focus_code=group_id)
        self._focus_control_code(group_id)
        self.status_var.set(f"Oppdaterte gruppenavn til {updated_name}.")

    def _remove_selected_group(self) -> None:
        group_id = self._selected_group_id()
        if not group_id:
            self._notify_inline("Velg en A07-gruppe først.", focus_widget=self.tree_groups)
            return
        mapping_resolver = getattr(self, "_effective_mapping", None)
        if callable(mapping_resolver):
            effective_mapping = mapping_resolver()
        else:
            effective_mapping = dict(getattr(self.workspace, "mapping", {}) or {})
        in_use = [
            str(account).strip()
            for account, code in (effective_mapping or {}).items()
            if str(code or "").strip() == group_id and str(account).strip()
        ]
        if in_use:
            account_label = "konto" if len(in_use) == 1 else "kontoer"
            self._notify_inline(
                f"Kan ikke oppløse gruppe som fortsatt brukes i mapping ({len(in_use)} {account_label}). Fjern eller flytt mapping først.",
                focus_widget=self.tree_groups,
            )
            self._focus_control_code(group_id)
            return
        group_label = self._group_display_label(group_id)
        self.workspace.groups.pop(group_id, None)
        self.workspace.locks.discard(group_id)
        self._autosave_workspace_state()
        self._refresh_core()
        self.status_var.set(f"Oppløste A07-gruppe {group_label}.")

    def _on_group_selection_changed(self) -> None:
        if bool(getattr(self, "_suspend_selection_sync", False)):
            return
        sync_groups_panel_visibility = getattr(self, "_sync_groups_panel_visibility", None)
        if callable(sync_groups_panel_visibility):
            sync_groups_panel_visibility()
        self._focus_selected_group_code()

    def _focus_selected_group_code(self) -> None:
        group_id = self._selected_group_id()
        if not group_id:
            return
        try:
            current_code = str(self._selected_control_code() or "").strip()
        except Exception:
            current_code = ""
        if current_code == group_id:
            return
        self._focus_control_code(group_id)

    def _lock_selected_code(self) -> None:
        code = self._selected_control_code()
        if not code:
            self._notify_inline("Velg en kode eller gruppe å låse først.", focus_widget=self.tree_a07)
            return
        self.workspace.locks.add(code)
        self._autosave_workspace_state()
        self._refresh_core(focus_code=code)
        self._focus_control_code(code)
        self.status_var.set(f"Låste {self._group_display_label(code)}.")

    def _unlock_selected_code(self) -> None:
        code = self._selected_control_code()
        if not code:
            self._notify_inline("Velg en kode eller gruppe å låse opp først.", focus_widget=self.tree_a07)
            return
        self.workspace.locks.discard(code)
        self._autosave_workspace_state()
        self._refresh_core(focus_code=code)
        self._focus_control_code(code)
        self.status_var.set(f"Låste opp {self._group_display_label(code)}.")
