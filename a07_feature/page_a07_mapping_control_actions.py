from __future__ import annotations

from .page_a07_mapping_shared import *  # noqa: F403
from .page_a07_mapping_assign import A07PageMappingAssignMixin
from src.pages.a07.backend.control_actions import (
    ASSIGN_A07,
    ASSIGN_RF1022,
    PROMPT_A07_CODE,
    PROMPT_RF1022_GROUP,
    apply_accounts_to_code,
    plan_selected_control_gl_action,
)


class A07PageMappingControlActionsMixin:
    def _selected_control_gl_action_plan(self):
        accounts = self._selected_control_gl_accounts()
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        selected_group_getter = getattr(self, "_selected_rf1022_group", None)
        try:
            group_id = selected_group_getter() if callable(selected_group_getter) else ""
        except Exception:
            group_id = ""
        selected_code_getter = getattr(self, "_selected_control_code", None)
        try:
            selected_code = selected_code_getter() if callable(selected_code_getter) else ""
        except Exception:
            selected_code = ""
        return plan_selected_control_gl_action(
            accounts=accounts,
            work_level=work_level,
            selected_code=selected_code,
            selected_rf1022_group=group_id,
        )

    def _assign_selected_control_mapping(self) -> None:
        plan = A07PageMappingControlActionsMixin._selected_control_gl_action_plan(self)
        if not plan.accounts:
            self._notify_inline(
                "Velg en eller flere saldobalansekontoer til venstre først.",
                focus_widget=self.tree_control_gl,
            )
            return
        if plan.action == ASSIGN_RF1022:
            self._assign_accounts_to_rf1022_group(plan.accounts, plan.target_group, source_label=plan.source_label)
            return
        if plan.action == PROMPT_A07_CODE:
            self._notify_inline("Velg en A07-kode til høyre først.", focus_widget=self.tree_a07)
            return
        code = plan.target_code
        conflicts = _locked_mapping_conflicts_for(self, plan.accounts, target_code=code)
        if _notify_locked_conflicts_for(self, conflicts, focus_widget=self.tree_a07):
            return

        try:
            assigned = apply_accounts_to_code(self.workspace.mapping, plan.accounts, code)
            autosaved = self._autosave_mapping()
            self._refresh_core(focus_code=code)
            self._focus_mapping_account(assigned[0])
            count = len(assigned)
            if autosaved:
                self.status_var.set(f"Tildelte {count} konto(er) til {code} og lagret i klientmappen.")
            else:
                self.status_var.set(f"Tildelte {count} konto(er) til {code}.")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke tildele konto til kode:\n{exc}")

    def _run_selected_control_gl_action(self) -> None:
        plan = A07PageMappingControlActionsMixin._selected_control_gl_action_plan(self)
        if not plan.accounts:
            return
        if plan.action == ASSIGN_RF1022:
            self._assign_accounts_to_rf1022_group(plan.accounts, plan.target_group, source_label=plan.source_label)
            return
        if plan.action == PROMPT_RF1022_GROUP:
            try:
                self.tree_a07.focus_set()
            except Exception:
                pass
            self.status_var.set(plan.message)
            return
        if plan.action == ASSIGN_A07:
            self._assign_selected_control_mapping()
            return
        try:
            self.tree_a07.focus_set()
        except Exception:
            pass
        self.status_var.set(plan.message)

    def _link_selected_control_rows(self) -> None:
        try:
            accounts = self._selected_control_gl_accounts()
        except Exception:
            accounts = []
        if accounts:
            self._run_selected_control_gl_action()
            return
        self._run_selected_control_action()

    def _clear_selected_control_mapping(self) -> None:
        accounts = self._selected_control_gl_accounts()
        if not accounts:
            self._notify_inline(
                "Velg en eller flere saldobalansekontoer til venstre først.",
                focus_widget=self.tree_control_gl,
            )
            return
        remover = getattr(self, "_remove_mapping_accounts_checked", None)
        if callable(remover):
            remover(
                accounts,
                focus_widget=self.tree_control_gl,
                refresh="core",
                source_label="Fjernet kode fra",
            )
        else:
            A07PageMappingAssignMixin._remove_mapping_accounts_checked(
                self,
                accounts,
                focus_widget=self.tree_control_gl,
                refresh="core",
                source_label="Fjernet kode fra",
            )

    def _drop_unmapped_on_control(self, event: tk.Event | None = None) -> None:
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        try:
            accounts = self._current_drag_accounts()
        except Exception:
            account = str(getattr(self, "_drag_unmapped_account", "") or "").strip()
            accounts = [account] if account else []
        if not accounts:
            return

        try:
            code = self._tree_iid_from_event(self.tree_a07, event)
            if not code:
                return
            self.tree_a07.selection_set(code)
            self.tree_a07.focus(code)
            self.tree_a07.see(code)
            if work_level == "rf1022":
                self._assign_accounts_to_rf1022_group(accounts, code, source_label="Drag-and-drop mot RF-1022")
                return
            conflicts = _locked_mapping_conflicts_for(self, accounts, target_code=code)
            if _notify_locked_conflicts_for(self, conflicts, focus_widget=self.tree_a07):
                return
            if len(accounts) == 1:
                self._apply_account_code_mapping(accounts[0], code, source_label="Drag-and-drop")
            else:
                assigned = apply_accounts_to_code(self.workspace.mapping, accounts, code)
                autosaved = self._autosave_mapping()
                self._refresh_core(focus_code=code)
                self._focus_control_code(code)
                self._focus_mapping_account(assigned[0])
                if autosaved:
                    self.status_var.set(
                        f"Drag-and-drop: tildelte {len(assigned)} kontoer til {code} og lagret i klientmappen."
                    )
                else:
                    self.status_var.set(f"Drag-and-drop: tildelte {len(assigned)} kontoer til {code}.")
                self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke fullfore drag-and-drop-mapping:\n{exc}")
        finally:
            self._clear_control_drag_state()

    def _apply_best_suggestion_for_selected_code(self) -> None:
        code = self._selected_control_code()
        if code in _locked_codes_for(self):
            self._notify_inline("Valgt kode er låst. Lås opp før du bruker forslag.", focus_widget=self.tree_a07)
            return
        ensure_display = getattr(self, "_ensure_suggestion_display_fields", None)
        if callable(ensure_display):
            suggestions_df = ensure_display()
        else:
            suggestions_df = getattr(getattr(self, "workspace", None), "suggestions", None)
            if not isinstance(suggestions_df, pd.DataFrame):
                suggestions_df = _empty_suggestions_df()
        best_row = best_suggestion_row_for_code(
            suggestions_df,
            code,
            locked_codes=_locked_codes_for(self),
        )
        if code is None or best_row is None:
            self._notify_inline("Fant ikke et forslag for valgt kode.", focus_widget=self.tree_a07)
            return
        if not bool(best_row.get("WithinTolerance", False)):
            self._notify_inline(
                "Beste forslag er utenfor toleranse. Kontroller detaljene eller map manuelt.",
                focus_widget=self.tree_control_suggestions,
            )
            return
        if not a07_suggestion_is_strict_auto(best_row):
            reason = str(best_row.get("SuggestionGuardrailReason") or "").strip()
            suffix = f" ({reason})" if reason else ""
            self._notify_inline(
                f"Beste forslag er ikke trygt nok for automatisk bruk{suffix}. Kontroller eller map manuelt.",
                focus_widget=self.tree_control_suggestions,
            )
            return

        try:
            apply_suggestion_to_mapping(self.workspace.mapping, best_row)
            autosaved = self._autosave_mapping()
            self._refresh_core(focus_code=code)
            self._focus_control_code(code)
            if autosaved:
                self.status_var.set(f"Beste forslag brukt for {code} og lagret i klientmappen.")
            else:
                self.status_var.set(f"Beste forslag brukt for {code}.")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke bruke beste forslag:\n{exc}")

    def _apply_history_for_selected_code(self) -> None:
        code = self._selected_control_code()
        if not code:
            self._notify_inline("Velg en A07-kode til høyre først.", focus_widget=self.tree_a07)
            return
        if code in _locked_codes_for(self):
            self._notify_inline("Valgt kode er låst. Lås opp før du bruker historikk.", focus_widget=self.tree_a07)
            return
        accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=self._effective_mapping(),
            mapping_previous=self._effective_previous_mapping(),
            gl_df=self.workspace.gl_df,
        )
        if not accounts:
            self._notify_inline("Fant ingen trygg historikk Ã¥ bruke for valgt kode.", focus_widget=self.tree_a07)
            return
        if not code or not accounts:
            messagebox.showinfo("A07", "Fant ingen trygg historikk Ã¥ bruke for valgt kode.")
            return

        try:
            apply_suggestion_to_mapping(
                self.workspace.mapping,
                {"Kode": code, "ForslagKontoer": ",".join(accounts)},
            )
            autosaved = self._autosave_mapping(source="history", confidence=0.9)
            self._refresh_core(focus_code=code)
            self._focus_control_code(code)
            if autosaved:
                self.status_var.set(f"Historikk brukt for {code} og lagret i klientmappen.")
            else:
                self.status_var.set(f"Historikk brukt for {code}.")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke bruke historikk for valgt kode:\n{exc}")

    def _run_selected_control_action(self) -> None:
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        if work_level == "rf1022":
            group_id = str(getattr(self, "_selected_rf1022_group", lambda: None)() or "").strip()
            if not group_id:
                return
            self._select_support_tab_key("suggestions")
            try:
                self._refresh_suggestions_tree()
            except Exception:
                pass
            return
        code = self._selected_control_code()
        if not code:
            return
        if code in _locked_codes_for(self):
            self._notify_inline("Valgt kode er låst. Lås opp før du bruker automatikk.", focus_widget=self.tree_a07)
            return

        overview_row = None
        if self.a07_overview_df is not None and not self.a07_overview_df.empty:
            matches = self.a07_overview_df.loc[self.a07_overview_df["Kode"].astype(str).str.strip() == code]
            if not matches.empty:
                overview_row = matches.iloc[0]

        status = str((overview_row.get("Status") if overview_row is not None else "") or "").strip()
        if status in {"OK", "Ekskludert"}:
            return

        current_accounts = accounts_for_code(self._effective_mapping(), code)
        history_accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=self._effective_mapping(),
            mapping_previous=self._effective_previous_mapping(),
            gl_df=self.workspace.gl_df,
        )
        if history_accounts:
            self._apply_history_for_selected_code()
            return

        suggestions_df = self._ensure_suggestion_display_fields()
        best_row = best_suggestion_row_for_code(
            suggestions_df,
            code,
            locked_codes=_locked_codes_for(self),
        )
        if best_row is not None and a07_suggestion_is_strict_auto(best_row):
            self._apply_best_suggestion_for_selected_code()
            return

        fallback = build_smartmapping_fallback(
            code=code,
            current_accounts=current_accounts,
            history_accounts=history_accounts,
            best_row=best_row,
        )
        self._select_support_tab_key(fallback.preferred_tab)
        if fallback.preferred_tab == "suggestions":
            self._select_best_suggestion_row_for_code(code)
        elif fallback.preferred_tab == "history":
            try:
                self._set_tree_selection(self.tree_history, code)
            except Exception:
                pass
        elif fallback.preferred_tab == "mapping" and current_accounts:
            try:
                self._set_tree_selection(self.tree_control_gl, current_accounts[0])
            except Exception:
                pass
        try:
            self.entry_control_gl_filter.focus_set()
        except Exception:
            pass
        self.status_var.set(fallback.message)

