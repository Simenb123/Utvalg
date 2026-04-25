from __future__ import annotations

from .page_a07_mapping_shared import *  # noqa: F403
from .page_a07_mapping_residual import A07PageMappingResidualMixin
from .suggest.residual_display import RESIDUAL_SUGGESTION_SOURCE
from src.pages.a07.backend.mapping_apply import (
    apply_magic_wand_suggestions_to_mapping,
    apply_safe_history_mappings_to_mapping,
    apply_safe_suggestions_to_mapping,
)


class A07PageMappingBatchMixin(A07PageMappingResidualMixin):
    def _apply_safe_history_mappings(self) -> tuple[int, int]:
        result = apply_safe_history_mappings_to_mapping(
            self.workspace.mapping,
            history_compare_df=self.history_compare_df,
            effective_mapping=self._effective_mapping(),
            effective_previous_mapping=self._effective_previous_mapping(),
            gl_df=self.workspace.gl_df,
            locked_codes=_locked_codes_for(self),
        )
        return result.applied_codes, result.applied_accounts

    def _apply_safe_suggestions(self) -> tuple[int, int]:
        result = apply_safe_suggestions_to_mapping(
            self.workspace.mapping,
            suggestions_df=self.workspace.suggestions,
            effective_mapping=self._effective_mapping(),
            locked_codes=_locked_codes_for(self),
            min_score=0.85,
        )
        return result.applied_codes, result.applied_accounts

    def _apply_magic_wand_suggestions(
        self,
        unresolved_code_values: Sequence[object] | None = None,
    ) -> tuple[int, int, int]:
        amount_checker = getattr(self, "_strict_auto_amount_is_exact", None)
        result = apply_magic_wand_suggestions_to_mapping(
            self.workspace.mapping,
            suggestions_df=self.workspace.suggestions,
            effective_mapping=self._effective_mapping(),
            unresolved_codes=unresolved_code_values,
            locked_codes=_locked_codes_for(self),
            amount_is_exact=(amount_checker if callable(amount_checker) else None),
        )
        return result.applied_codes, result.applied_accounts, result.skipped_codes

    def _magic_match_clicked(self) -> None:
        try:
            auto_enabled = bool(getattr(self, "_safe_auto_matching_enabled", lambda: False)())
        except Exception:
            auto_enabled = False
        if not auto_enabled:
            self._notify_inline(
                "Tryllestav er midlertidig deaktivert mens A07-kontrollene strammes inn. Bruk forslag manuelt.",
                focus_widget=self,
            )
            return
        if self.workspace.gl_df.empty:
            self._sync_active_trial_balance(refresh=False)

        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            self._notify_inline(
                "Last A07 og bruk aktiv saldobalanse for valgt klient/år før du kjører trygg auto-matching.",
                focus_widget=self,
            )
            return

        try:
            work_level = self._selected_control_work_level()
        except Exception:
            work_level = "a07"
        if work_level != "rf1022":
            self._run_magic_wand_residual_flow()
            return

        try:
            self._apply_rf1022_candidate_suggestions()
        except Exception as exc:
            messagebox.showerror("A07", f"Trygg auto-matching kunne ikke fullføre:\n{exc}")

    def _open_manual_mapping_clicked(
        self,
        initial_account: str | None = None,
        initial_code: str | None = None,
    ) -> None:
        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            self._notify_inline(
                "Last A07 og bruk aktiv saldobalanse for valgt klient/Ã¥r for Ã¥ lage mapping.",
                focus_widget=self,
            )
            return

        account_options = build_gl_picker_options(self.workspace.gl_df, basis_col=self.workspace.basis_col)
        code_options = build_a07_picker_options(self.workspace.a07_df)
        if not account_options or not code_options:
            self._notify_inline("Fant ikke nok data til Ã¥ bygge avansert mapping.", focus_widget=self)
            return

        initial_account, initial_code = self._manual_mapping_defaults(
            preferred_account=initial_account,
            preferred_code=initial_code,
        )
        choice = open_manual_mapping_dialog(
            self,
            account_options=account_options,
            code_options=code_options,
            initial_account=initial_account,
            initial_code=initial_code,
            title="Ny eller rediger A07-mapping",
        )
        if choice is None:
            return

        try:
            self._apply_account_code_mapping(choice[0], choice[1], source_label="Mapping satt")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke lagre mappingen:\n{exc}")

    def _map_selected_unmapped(self) -> None:
        selection = self.tree_unmapped.selection()
        if not selection:
            self._notify_inline("Velg en umappet konto fÃ¸rst.", focus_widget=self.tree_unmapped)
            return

        self._open_manual_mapping_clicked()

    def _apply_selected_suggestion(self) -> None:
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        if work_level == "rf1022":
            self._apply_selected_rf1022_candidate()
            return
        row = self._selected_suggestion_row()
        if row is None:
            if self.workspace.suggestions is None or self.workspace.suggestions.empty:
                self._notify_inline("Det finnes ingen forslag Ã¥ bruke.", focus_widget=self.tree_a07)
            else:
                self._notify_inline("Velg et forslag fÃ¸rst.", focus_widget=self.tree_control_suggestions)
            return
        if self.workspace.suggestions is None or self.workspace.suggestions.empty:
            self._notify_inline("Det finnes ingen forslag Ã¥ bruke.", focus_widget=self.tree_a07)
            return

        try:
            code = str(row.get("Kode") or "").strip() or self._selected_control_code()
            if code in _locked_codes_for(self):
                self._notify_inline("Valgt kode er låst. Lås opp før du bruker forslag.", focus_widget=self.tree_a07)
                return
            if not a07_suggestion_is_strict_auto(row):
                source = str(row.get("SuggestionSource") or "").strip()
                if source == RESIDUAL_SUGGESTION_SOURCE:
                    action = str(row.get("ResidualAction") or "").strip()
                    if action == "group_review":
                        self._create_residual_group_from_suggestion(row)
                        return
                    accounts = sorted(_split_mapping_accounts(row.get("ForslagKontoer")))
                    self._open_manual_mapping_clicked(
                        initial_account=(accounts[0] if accounts else None),
                        initial_code=(code or None),
                    )
                    return
                reason = str(row.get("SuggestionGuardrailReason") or "").strip()
                suffix = f" ({reason})" if reason else ""
                self._notify_inline(
                    f"Valgt forslag er ikke trygt nok for automatisk bruk{suffix}. Bruk manuell/avansert mapping.",
                    focus_widget=self.tree_control_suggestions,
                )
                return
            apply_suggestion_to_mapping(self.workspace.mapping, row)
            autosaved = self._autosave_mapping()
            self._refresh_core(focus_code=code)
            self._focus_control_code(code)
            if autosaved:
                self.status_var.set("Valgt forslag er brukt i mappingen og lagret i klientmappen.")
            else:
                self.status_var.set("Valgt forslag er brukt i mappingen.")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke bruke valgt forslag:\n{exc}")

    def _apply_selected_history_mapping(self) -> None:
        selection = self.tree_history.selection()
        if not selection:
            self._notify_inline("Velg en historikkrad fÃ¸rst.", focus_widget=self.tree_history)
            return

        code = self._selected_code_from_tree(self.tree_history)
        if code in _locked_codes_for(self):
            self._notify_inline("Valgt kode er låst. Lås opp før du bruker historikk.", focus_widget=self.tree_history)
            return
        accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=self._effective_mapping(),
            mapping_previous=self._effective_previous_mapping(),
            gl_df=self.workspace.gl_df,
        )
        if not code or not accounts:
            self._notify_inline(
                "Valgt historikk kan ikke brukes direkte. Kontoene mÃ¥ finnes i Ã¥r og ikke kollidere med annen mapping.",
                focus_widget=self.tree_history,
            )
            return

        try:
            apply_suggestion_to_mapping(
                self.workspace.mapping,
                {"Kode": code, "ForslagKontoer": ",".join(accounts)},
            )
            autosaved = self._autosave_mapping(source="history", confidence=0.9)
            self._refresh_core(focus_code=code)
            self._focus_mapping_account(accounts[0])
            if autosaved:
                self.status_var.set(
                    f"Historisk mapping brukt for {code} ({', '.join(accounts)}) og lagret i klientmappen."
                )
            else:
                self.status_var.set(f"Historisk mapping brukt for {code} ({', '.join(accounts)}).")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke bruke valgt historikk:\n{exc}")

    def _apply_batch_history_mappings(self) -> None:
        if self.history_compare_df is None or self.history_compare_df.empty:
            self._notify_inline("Det finnes ingen historikk Ã¥ bruke.", focus_widget=self.tree_a07)
            return

        codes = select_safe_history_codes(self.history_compare_df)
        if not codes:
            self._notify_inline(
                "Fant ingen sikre historikkmappinger. Kontoene mÃ¥ finnes i Ã¥r og ikke kollidere med annen mapping.",
                focus_widget=self.tree_a07,
            )
            return

        try:
            applied_codes, applied_accounts = self._apply_safe_history_mappings()

            if applied_codes == 0:
                self._notify_inline(
                    "Ingen historikkmappinger kunne brukes etter konfliktkontroll mot dagens mapping.",
                    focus_widget=self.tree_a07,
                )
                return

            autosaved = self._autosave_mapping(source="history", confidence=0.9)
            self._refresh_core()
            if autosaved:
                self.status_var.set(
                    f"Brukte {applied_codes} sikre historikkmappinger ({applied_accounts} kontoer) og lagret endringen."
                )
            else:
                self.status_var.set(
                    f"Brukte {applied_codes} sikre historikkmappinger ({applied_accounts} kontoer)."
                )
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke bruke sikre historikkmappinger:\n{exc}")

    def _apply_batch_suggestions_clicked(self) -> None:
        try:
            auto_enabled = bool(getattr(self, "_safe_auto_matching_enabled", lambda: False)())
        except Exception:
            auto_enabled = False
        if not auto_enabled:
            self._notify_inline(
                "Trygg auto-matching er midlertidig deaktivert. Bruk trygg kandidat manuelt per A07-kode.",
                focus_widget=getattr(self, "tree_control_suggestions", None),
            )
            return
        self._apply_rf1022_candidate_suggestions()

