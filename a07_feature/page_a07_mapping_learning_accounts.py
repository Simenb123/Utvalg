from __future__ import annotations

from .page_a07_mapping_shared import *  # noqa: F403


def _mapping_actions_module():
    from . import page_a07_mapping_actions as mapping_actions_module

    return mapping_actions_module


class A07PageMappingLearningAccountsMixin:
    def _control_account_name_lookup(self, accounts: Sequence[object]) -> dict[str, str]:
        wanted = {str(account or "").strip() for account in accounts if str(account or "").strip()}
        if not wanted:
            return {}
        out: dict[str, str] = {}
        frames = (
            getattr(self, "control_selected_accounts_df", None),
            getattr(self, "control_gl_df", None),
            getattr(self, "mapping_df", None),
        )
        for frame in frames:
            if frame is None or getattr(frame, "empty", True):
                continue
            if "Konto" not in frame.columns or "Navn" not in frame.columns:
                continue
            work = frame.copy()
            work["Konto"] = work["Konto"].fillna("").astype(str).str.strip()
            for _, row in work.iterrows():
                account = str(row.get("Konto") or "").strip()
                if account not in wanted or account in out:
                    continue
                name = str(row.get("Navn") or "").strip()
                if name:
                    out[account] = name
        return out

    def _mapped_a07_code_for_account(self, account: object) -> str:
        account_s = str(account or "").strip()
        if not account_s:
            return ""
        effective_mapping_getter = getattr(self, "_effective_mapping", None)
        if callable(effective_mapping_getter):
            try:
                code = str((effective_mapping_getter() or {}).get(account_s) or "").strip()
                if code:
                    return code
            except Exception:
                pass
        workspace = getattr(self, "workspace", None)
        mapping = getattr(workspace, "mapping", None) or {}
        return str(mapping.get(account_s) or "").strip()

    def _notify_a07_rule_learning_changed(self, focus_code: object | None = None) -> None:
        app = getattr(session, "APP", None)
        if app is None:
            return

        def _defer(callback) -> None:
            scheduler = getattr(self, "after_idle", None)
            if callable(scheduler):
                try:
                    scheduler(callback)
                    return
                except Exception:
                    pass
            try:
                callback()
            except Exception:
                pass

        # Alias learning already invalidates rule caches and triggers one A07 refresh.
        # Refreshing Analyse/Saldobalanse from this right-click path makes the UI feel
        # stuck, so only keep the admin rulebook editor in sync and do it after idle.
        def _reload_admin_rulebook() -> None:
            admin_page = getattr(app, "page_admin", None)
            rulebook_editor = getattr(admin_page, "_rulebook_editor", None)
            reload_editor = getattr(rulebook_editor, "reload", None)
            if not callable(reload_editor):
                return
            try:
                reload_editor(select_key=focus_code)
            except TypeError:
                try:
                    reload_editor()
                except Exception:
                    pass
            except Exception:
                pass

        _defer(_reload_admin_rulebook)

    def _refresh_after_a07_rule_learning(self, focus_code: object | None = None) -> None:
        try:
            self._refresh_core(focus_code=focus_code)
        except Exception:
            try:
                self._refresh_all()
            except Exception:
                pass

    def _learn_selected_control_account_names(
        self,
        *,
        exclude: bool,
        remove_mapping: bool = False,
    ) -> None:
        accounts_getter = getattr(self, "_selected_control_account_ids", None)
        accounts = accounts_getter() if callable(accounts_getter) else []
        accounts = [str(account or "").strip() for account in accounts if str(account or "").strip()]
        if not accounts:
            self._notify_inline(
                "Velg en eller flere mappede kontoer nederst først.",
                focus_widget=getattr(self, "tree_control_accounts", None),
            )
            return

        if remove_mapping:
            conflicts = _locked_mapping_conflicts_for(self, accounts)
            if _notify_locked_conflicts_for(self, conflicts, focus_widget=getattr(self, "tree_control_accounts", None)):
                return

        names = self._control_account_name_lookup(accounts)
        entries: list[tuple[str, str]] = []
        skipped = 0
        for account in accounts:
            code = self._mapped_a07_code_for_account(account)
            name = names.get(account, "")
            if not code or not name:
                skipped += 1
                continue
            entries.append((code, name))

        if not entries:
            self._notify_inline(
                "Fant ingen mappede kontoer med A07-kode og kontonavn aa laere av.",
                focus_widget=getattr(self, "tree_control_accounts", None),
            )
            return

        mapping_actions_module = _mapping_actions_module()
        try:
            batch_result = mapping_actions_module.append_a07_rule_keywords(entries, exclude=exclude)
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke oppdatere A07-regler:\n{exc}")
            return
        learned = [(result.code, result.term, bool(result.changed)) for result in batch_result.results]

        try:
            mapping_actions_module.payroll_classification.invalidate_runtime_caches()
        except Exception:
            pass

        removed_count = 0
        if remove_mapping:
            remover = getattr(self, "_remove_mapping_accounts_checked", None)
            removed = (
                remover(
                    accounts,
                    focus_widget=getattr(self, "tree_control_accounts", None),
                    refresh="none",
                    source_label="Fjernet mapping fra",
                )
                if callable(remover)
                else []
            )
            removed_count = len(removed)

        focus_code = learned[0][0] if learned else None
        notify_admin = getattr(self, "_notify_a07_rule_learning_changed", None)
        if callable(notify_admin):
            try:
                notify_admin(focus_code=focus_code)
            except TypeError:
                try:
                    notify_admin()
                except Exception:
                    pass
            except Exception:
                pass

        refresh_after_learning = getattr(self, "_refresh_after_a07_rule_learning", None)
        if callable(refresh_after_learning):
            refresh_after_learning(focus_code=focus_code)
        else:
            try:
                self._refresh_core(focus_code=focus_code)
            except Exception:
                try:
                    self._refresh_all()
                except Exception:
                    pass

        changed_count = sum(1 for _code, _name, changed in learned if changed)
        action = "ekskludert fra" if exclude else "lagt til som alias for"
        if remove_mapping:
            self.status_var.set(
                f"{changed_count} kontonavn {action} A07-regel, {removed_count} mapping(er) fjernet."
            )
        else:
            self.status_var.set(f"{changed_count} kontonavn {action} A07-regel.")
        if skipped:
            self.status_var.set(f"{self.status_var.get()} Hoppet over {skipped}.")

    def _append_selected_control_account_names_to_a07_alias(self) -> None:
        self._learn_selected_control_account_names(exclude=False, remove_mapping=False)

    def _exclude_selected_control_account_names_from_a07_code(self) -> None:
        self._learn_selected_control_account_names(exclude=True, remove_mapping=False)

    def _remove_selected_control_accounts_and_exclude_alias(self) -> None:
        self._learn_selected_control_account_names(exclude=True, remove_mapping=True)

    def _selected_control_account_learning_context(self) -> dict[str, object]:
        accounts_getter = getattr(self, "_selected_control_account_ids", None)
        try:
            accounts = accounts_getter() if callable(accounts_getter) else []
        except Exception:
            accounts = []
        accounts = [str(account or "").strip() for account in accounts if str(account or "").strip()]
        if not accounts:
            return {"enabled": False, "code_label": "A07-kode", "accounts": []}
        name_lookup = getattr(self, "_control_account_name_lookup", None)
        try:
            names = name_lookup(accounts) if callable(name_lookup) else {}
        except Exception:
            names = {}
        code_getter = getattr(self, "_mapped_a07_code_for_account", None)
        pairs: list[tuple[str, str, str]] = []
        codes: list[str] = []
        for account in accounts:
            try:
                code = str(code_getter(account) if callable(code_getter) else "").strip()
            except Exception:
                code = ""
            name = str((names or {}).get(account) or "").strip()
            if code and name:
                pairs.append((account, code, name))
                if code not in codes:
                    codes.append(code)
        if len(codes) == 1:
            code_label = codes[0]
        elif len(codes) > 1:
            code_label = "valgte A07-koder"
        else:
            code_label = "A07-kode"
        return {
            "enabled": bool(pairs),
            "code_label": code_label,
            "accounts": accounts,
            "pairs": pairs,
        }

