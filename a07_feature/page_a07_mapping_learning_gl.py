from __future__ import annotations

from .page_a07_mapping_shared import *  # noqa: F403


def _mapping_actions_module():
    from . import page_a07_mapping_actions as mapping_actions_module

    return mapping_actions_module


class A07PageMappingLearningGlMixin:
    def _selected_control_gl_learning_context(self) -> dict[str, object]:
        accounts_getter = getattr(self, "_selected_control_gl_accounts", None)
        try:
            accounts = accounts_getter() if callable(accounts_getter) else []
        except Exception:
            accounts = []
        accounts = [str(account or "").strip() for account in accounts if str(account or "").strip()]
        if not accounts:
            return {
                "enabled": False,
                "code_label": "A07-kode",
                "accounts": [],
                "pairs": [],
                "remove_enabled": False,
            }

        selected_code_getter = getattr(self, "_selected_control_code", None)
        try:
            selected_code = str(selected_code_getter() if callable(selected_code_getter) else "").strip()
        except Exception:
            selected_code = ""
        if selected_code.startswith("A07_GROUP:"):
            selected_code = ""

        name_lookup = getattr(self, "_control_account_name_lookup", None)
        try:
            names = name_lookup(accounts) if callable(name_lookup) else {}
        except Exception:
            names = {}
        code_getter = getattr(self, "_mapped_a07_code_for_account", None)

        pairs: list[tuple[str, str, str]] = []
        codes: list[str] = []
        mapped_accounts: list[str] = []
        for account in accounts:
            try:
                mapped_code = str(code_getter(account) if callable(code_getter) else "").strip()
            except Exception:
                mapped_code = ""
            if mapped_code:
                mapped_accounts.append(account)
            code = selected_code or mapped_code
            name = str((names or {}).get(account) or "").strip()
            if code and name:
                pairs.append((account, code, name))
                if code not in codes:
                    codes.append(code)

        if selected_code:
            code_label = selected_code
        elif len(codes) == 1:
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
            "remove_enabled": bool(mapped_accounts),
        }

    def _learn_selected_control_gl_account_names(
        self,
        *,
        exclude: bool,
        remove_mapping: bool = False,
    ) -> None:
        context_getter = getattr(self, "_selected_control_gl_learning_context", None)
        try:
            context = context_getter() if callable(context_getter) else {}
        except Exception:
            context = {}
        if not isinstance(context, dict):
            context = {}

        accounts = [str(account or "").strip() for account in context.get("accounts", []) if str(account or "").strip()]
        pairs = [
            (str(code or "").strip(), str(name or "").strip())
            for _account, code, name in context.get("pairs", [])
            if str(code or "").strip() and str(name or "").strip()
        ]
        if not accounts:
            self._notify_inline(
                "Velg en eller flere kontoer til venstre forst.",
                focus_widget=getattr(self, "tree_control_gl", None),
            )
            return
        if not pairs:
            self._notify_inline(
                "Velg en A07-kode til hoyre, eller velg kontoer som allerede er koblet.",
                focus_widget=getattr(self, "tree_a07", None),
            )
            return

        if remove_mapping:
            conflicts = _locked_mapping_conflicts_for(self, accounts)
            if _notify_locked_conflicts_for(self, conflicts, focus_widget=getattr(self, "tree_control_gl", None)):
                return

        mapping_actions_module = _mapping_actions_module()
        try:
            batch_result = mapping_actions_module.append_a07_rule_keywords(pairs, exclude=exclude)
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
                    focus_widget=getattr(self, "tree_control_gl", None),
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

    def _append_selected_control_gl_names_to_a07_alias(self) -> None:
        self._learn_selected_control_gl_account_names(exclude=False, remove_mapping=False)

    def _exclude_selected_control_gl_names_from_a07_code(self) -> None:
        self._learn_selected_control_gl_account_names(exclude=True, remove_mapping=False)

    def _remove_selected_control_gl_accounts_and_exclude_alias(self) -> None:
        self._learn_selected_control_gl_account_names(exclude=True, remove_mapping=True)

