from __future__ import annotations

from .page_a07_mapping_shared import *  # noqa: F403
from src.pages.a07.backend.control_actions import (
    apply_accounts_to_code,
    clean_account_ids,
    resolve_rf1022_target_code as resolve_rf1022_target_code_backend,
)


class A07PageMappingAssignMixin:
    def _rf1022_group_menu_choices(self) -> list[tuple[str, str]]:
        choices: list[tuple[str, str]] = []
        seen: set[str] = set()
        overview_df = getattr(self, "rf1022_overview_df", None)
        if isinstance(overview_df, pd.DataFrame) and not overview_df.empty:
            for _, row in overview_df.iterrows():
                group_id = str(row.get("GroupId") or "").strip()
                if not group_id or group_id in seen:
                    continue
                label = str(row.get("Navn") or "").strip() or rf1022_group_label(group_id) or group_id
                choices.append((group_id, label))
                seen.add(group_id)
        for group_id in ("100_loenn_ol", "100_refusjon", "111_naturalytelser", "112_pensjon", "uavklart_rf1022"):
            if group_id in seen:
                continue
            label = rf1022_group_label(group_id) or group_id
            choices.append((group_id, label))
        return choices

    def _a07_code_menu_choices(self, *, limit: int = 120) -> list[tuple[str, str]]:
        choices: list[tuple[str, str]] = []
        seen: set[str] = set()

        def _add_choice(code: object, label: object | None = None) -> None:
            code_s = str(code or "").strip()
            if not code_s or code_s.startswith("A07_GROUP:") or code_s in seen:
                return
            label_s = str(label or "").strip()
            if not label_s:
                label_s = code_s
            if not label_s.lower().startswith(code_s.lower()):
                label_s = f"{code_s} - {label_s}"
            if len(label_s) > 110:
                label_s = f"{label_s[:107]}..."
            choices.append((code_s, label_s))
            seen.add(code_s)

        control_df = getattr(self, "control_df", None)
        if isinstance(control_df, pd.DataFrame) and not control_df.empty and "Kode" in control_df.columns:
            for _, row in control_df.iterrows():
                label = row.get("Navn") if "Navn" in control_df.columns else ""
                if not str(label or "").strip() and "A07Post" in control_df.columns:
                    label = row.get("A07Post")
                _add_choice(row.get("Kode"), label)
                if len(choices) >= limit:
                    return choices

        workspace = getattr(self, "workspace", None)
        a07_df = getattr(workspace, "a07_df", None)
        for option in build_a07_picker_options(a07_df if isinstance(a07_df, pd.DataFrame) else pd.DataFrame()):
            _add_choice(option.key, option.label)
            if len(choices) >= limit:
                break
        return choices

    def _activate_a07_code_for_explicit_account_action(self, code: str | None) -> None:
        code_s = str(code or "").strip()
        if not code_s:
            return
        try:
            self.workspace.selected_code = code_s
        except Exception:
            pass
        sync_level = getattr(self, "_sync_control_work_level_vars", None)
        if callable(sync_level):
            try:
                sync_level("a07")
            except Exception:
                pass
        sync_work_level_ui = getattr(self, "_sync_control_work_level_ui", None)
        if callable(sync_work_level_ui):
            try:
                sync_work_level_ui()
            except Exception:
                pass
        sync_tabs = getattr(self, "_sync_support_notebook_tabs", None)
        if callable(sync_tabs):
            try:
                sync_tabs()
            except Exception:
                pass
        refresh_tree = getattr(self, "_refresh_a07_tree", None)
        if callable(refresh_tree):
            try:
                refresh_tree()
            except Exception:
                pass
        focus_code = getattr(self, "_focus_control_code", None)
        if callable(focus_code):
            try:
                focus_code(code_s)
            except Exception:
                pass

    def _resolve_rf1022_target_code(
        self,
        group_id: str | None,
        accounts: Sequence[object] | None = None,
    ) -> str | None:
        selected_code = str(getattr(getattr(self, "workspace", None), "selected_code", None) or "").strip()
        effective_mapping_getter = getattr(self, "_effective_mapping", None)
        if callable(effective_mapping_getter):
            try:
                effective_mapping = dict(effective_mapping_getter() or {})
            except Exception:
                effective_mapping = dict(getattr(getattr(self, "workspace", None), "mapping", None) or {})
        else:
            effective_mapping = dict(getattr(getattr(self, "workspace", None), "mapping", None) or {})

        gl_df = getattr(self, "control_gl_df", None)
        if not isinstance(gl_df, pd.DataFrame) or gl_df.empty:
            gl_df = getattr(getattr(self, "workspace", None), "gl_df", None)
        suggestions_df = getattr(getattr(self, "workspace", None), "suggestions", None)
        return resolve_rf1022_target_code_backend(
            group_id=group_id,
            accounts=accounts,
            selected_code=selected_code,
            effective_mapping=effective_mapping,
            suggestions_df=suggestions_df if isinstance(suggestions_df, pd.DataFrame) else None,
            gl_df=gl_df if isinstance(gl_df, pd.DataFrame) else None,
        )

    def _assign_accounts_to_rf1022_group(
        self,
        accounts: Sequence[object] | None,
        group_id: str | None,
        *,
        source_label: str = "RF-1022-mapping",
    ) -> None:
        account_list = list(clean_account_ids(accounts))
        if not account_list:
            self._notify_inline(
                "Velg en eller flere GL-kontoer til venstre forst.",
                focus_widget=self.tree_control_gl,
            )
            return
        group_s = str(group_id or "").strip()
        if not group_s:
            self._notify_inline("Velg en RF-1022-post til hoyre forst.", focus_widget=self.tree_a07)
            return
        target_code = self._resolve_rf1022_target_code(group_s, account_list)
        if not target_code:
            self._notify_inline("Fant ingen A07-detalj for valgt RF-1022-post.", focus_widget=self.tree_a07)
            return
        conflicts = _locked_mapping_conflicts_for(self, account_list, target_code=target_code)
        if _notify_locked_conflicts_for(self, conflicts, focus_widget=self.tree_a07):
            return

        assigned = apply_accounts_to_code(self.workspace.mapping, account_list, target_code)
        autosaved = self._autosave_mapping()
        try:
            self._selected_rf1022_group_id = group_s
        except Exception:
            pass
        self._refresh_core(focus_code=target_code)
        self._focus_mapping_account(assigned[0])
        try:
            self._focus_control_code(target_code)
        except Exception:
            pass
        group_label = rf1022_group_label(group_s) or group_s
        count = len(assigned)
        if autosaved:
            self.status_var.set(
                f"{source_label}: tildelte {count} konto(er) til {group_label} via {target_code} og lagret i klientmappen."
            )
        else:
            self.status_var.set(f"{source_label}: tildelte {count} konto(er) til {group_label} via {target_code}.")
        self._select_primary_tab()

    def _assign_selected_accounts_to_rf1022_group(self, group_id: str | None) -> None:
        self._assign_accounts_to_rf1022_group(
            self._selected_control_gl_accounts(),
            group_id,
            source_label="RF-1022-mapping",
        )

    def _assign_accounts_to_a07_code(
        self,
        accounts: Sequence[object] | None,
        code: str | None,
        *,
        source_label: str = "Mapping",
    ) -> None:
        account_list = list(clean_account_ids(accounts))
        if not account_list:
            self._notify_inline(
                "Velg en eller flere GL-kontoer til venstre forst.",
                focus_widget=self.tree_control_gl,
            )
            return
        code_s = str(code or "").strip()
        if not code_s:
            self._notify_inline("Velg en A07-kode forst.", focus_widget=self.tree_a07)
            return
        conflicts = _locked_mapping_conflicts_for(self, account_list, target_code=code_s)
        if _notify_locked_conflicts_for(self, conflicts, focus_widget=self.tree_a07):
            return

        try:
            assigned = apply_accounts_to_code(self.workspace.mapping, account_list, code_s)
            autosaved = self._autosave_mapping()
            self._refresh_core(focus_code=code_s)
            self._focus_mapping_account(assigned[0])
            self._activate_a07_code_for_explicit_account_action(code_s)
            count = len(assigned)
            if autosaved:
                self.status_var.set(f"{source_label}: tildelte {count} konto(er) til {code_s} og lagret i klientmappen.")
            else:
                self.status_var.set(f"{source_label}: tildelte {count} konto(er) til {code_s}.")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke tildele konto til kode:\n{exc}")

    def _assign_selected_accounts_to_a07_code(self, code: str | None) -> None:
        self._assign_accounts_to_a07_code(
            self._selected_control_gl_accounts(),
            code,
            source_label="Mapping",
        )

    def _focus_linked_code_for_selected_gl_account(self) -> None:
        accounts = self._selected_control_gl_accounts()
        account = str(accounts[0] if accounts else "").strip()
        if not account:
            self._notify_inline(
                "Velg en GL-konto til venstre forst.",
                focus_widget=self.tree_control_gl,
            )
            return
        try:
            mapping = self._effective_mapping()
        except Exception:
            mapping = getattr(getattr(self, "workspace", None), "mapping", {}) or {}
        code = str(mapping.get(account) or "").strip()
        if not code:
            self._notify_inline(
                f"Konto {account} har ingen A07-kobling.",
                focus_widget=self.tree_control_gl,
            )
            return
        self._activate_a07_code_for_explicit_account_action(code)
        try:
            self.status_var.set(f"Konto {account} er koblet til A07-kode {code}.")
        except Exception:
            pass

    def _apply_account_code_mapping(
        self,
        konto: str | None,
        kode: str | None,
        *,
        source_label: str = "Mapping satt",
    ) -> None:
        conflicts = _locked_mapping_conflicts_for(self, [konto], target_code=kode)
        if _notify_locked_conflicts_for(self, conflicts, focus_widget=self.tree_a07):
            return
        konto_s, kode_s = apply_manual_mapping_choice(self.workspace.mapping, konto, kode)
        autosaved = self._autosave_mapping()
        self._refresh_core(focus_code=kode_s)
        self._focus_control_code(kode_s)
        self._focus_mapping_account(konto_s)

        if autosaved:
            self.status_var.set(f"{source_label}: {konto_s} -> {kode_s} og lagret i klientmappen.")
        else:
            self.status_var.set(f"{source_label}: {konto_s} -> {kode_s}.")
        self._select_primary_tab()

    def _remove_mapping_accounts_checked(
        self,
        accounts: Sequence[object],
        *,
        focus_widget: object | None = None,
        refresh: str = "core",
        source_label: str = "Fjernet mapping fra",
    ) -> list[str]:
        clean_accounts = [
            str(account or "").strip()
            for account in (accounts or ())
            if str(account or "").strip()
        ]
        if not clean_accounts:
            return []
        conflicts = _locked_mapping_conflicts_for(self, clean_accounts)
        if _notify_locked_conflicts_for(self, conflicts, focus_widget=focus_widget):
            return []

        removed = remove_mapping_accounts(self.workspace.mapping, clean_accounts)
        if not removed:
            self._notify_inline(
                "Valgte kontoer har ingen mapping aa fjerne.",
                focus_widget=focus_widget,
            )
            return []

        try:
            autosaved = self._autosave_mapping()
            if refresh == "none":
                pass
            elif refresh == "all":
                self._refresh_all()
            else:
                selected_code_getter = getattr(self, "_selected_control_code", None)
                try:
                    focus_code = selected_code_getter() if callable(selected_code_getter) else None
                except Exception:
                    focus_code = None
                self._refresh_core(focus_code=focus_code)
            if refresh != "none":
                self._focus_mapping_account(removed[0])
            count = len(removed)
            if autosaved:
                self.status_var.set(f"{source_label} {count} konto(er) og lagret endringen.")
            else:
                self.status_var.set(f"{source_label} {count} konto(er).")
            if refresh != "none":
                self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke fjerne mapping fra konto:\n{exc}")
        return removed

