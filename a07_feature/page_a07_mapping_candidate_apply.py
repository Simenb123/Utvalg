from __future__ import annotations

from .page_a07_mapping_shared import *  # noqa: F403
from .page_a07_mapping_candidates import A07PageMappingCandidatesMixin
from src.pages.a07.backend.candidate_actions import apply_rf1022_auto_plan_to_mapping


class A07PageMappingCandidateApplyMixin:
    def _apply_selected_rf1022_candidate(self) -> None:
        row = self._selected_rf1022_candidate_row()
        if row is None:
            self._notify_inline("Velg en RF-1022-kandidat forst.", focus_widget=self.tree_control_suggestions)
            return
        account = str(row.get("Konto") or "").strip()
        code = str(row.get("Kode") or "").strip()
        if not code:
            code = str(self._resolve_rf1022_target_code(row.get("Rf1022GroupId"), [account]) or "").strip()
        if not account or not code:
            self._notify_inline("Kandidaten mangler konto eller A07-kode.", focus_widget=self.tree_control_suggestions)
            return
        plan_builder = getattr(self, "_build_global_auto_mapping_plan", None)
        try:
            plan = plan_builder(pd.DataFrame([dict(row)])) if callable(plan_builder) else pd.DataFrame()
        except Exception:
            plan = pd.DataFrame()
        if plan is None or plan.empty or "Action" not in plan.columns:
            self._notify_inline("Kandidaten kunne ikke sikkerhetskontrolleres.", focus_widget=self.tree_control_suggestions)
            return
        plan_row = plan.iloc[0]
        action = str(plan_row.get("Action") or "").strip()
        if action != "apply":
            status = str(plan_row.get("Status") or "Maa vurderes").strip()
            reason = str(plan_row.get("Reason") or "").strip()
            suffix = f": {reason}" if reason else "."
            self._notify_inline(
                f"Kandidaten kan ikke brukes automatisk ({status}){suffix}",
                focus_widget=self.tree_control_suggestions,
            )
            return
        checked_code = str(plan_row.get("Kode") or code).strip()
        checked_account = str(plan_row.get("Konto") or account).strip()
        self._assign_accounts_to_a07_code([checked_account], checked_code, source_label="RF-1022-forslag")

    def _apply_rf1022_candidate_suggestions(self) -> None:
        all_candidates = self._all_rf1022_candidate_df()
        if all_candidates.empty:
            self._notify_inline("Fant ingen trygge RF-1022-kandidater.", focus_widget=self.tree_control_suggestions)
            return
        plan_builder = getattr(self, "_build_global_auto_mapping_plan", None)
        if callable(plan_builder):
            plan = plan_builder(all_candidates)
        else:
            plan = A07PageMappingCandidatesMixin._build_global_auto_mapping_plan(self, all_candidates)
        self.rf1022_auto_plan_df = plan
        counts = A07PageMappingCandidatesMixin._global_auto_plan_action_counts(plan)
        if plan is None or plan.empty:
            self._notify_inline("Fant ingen trygge RF-1022-kandidater.", focus_widget=self.tree_control_suggestions)
            return

        candidates = plan.loc[plan["Action"].astype(str).str.strip() == "apply"].copy()
        if candidates.empty:
            skipped = counts["invalid"] + counts["conflict"] + counts["locked"] + counts["blocked"]
            self._notify_inline(
                "Fant ingen nye RF-1022-kandidater som kunne brukes "
                f"(hoppet over {skipped}, allerede ferdig {counts['already']}, "
                f"laast/konflikt {counts['locked'] + counts['conflict']}, maa vurderes {counts['review']}).",
                focus_widget=self.tree_control_suggestions,
            )
            return

        try:
            effective_mapping = dict(self._effective_mapping() or {})
        except Exception:
            effective_mapping = dict(getattr(getattr(self, "workspace", None), "mapping", None) or {})
        result = apply_rf1022_auto_plan_to_mapping(
            self.workspace.mapping,
            plan,
            effective_mapping=effective_mapping,
            locked_conflicts_fn=lambda account, code: _locked_mapping_conflicts_for(
                self,
                [account],
                target_code=code,
            ),
        )
        applied = list(result.applied)

        if not applied:
            skipped = result.skipped + counts["blocked"]
            self._notify_inline(
                "Fant ingen nye RF-1022-kandidater som kunne brukes "
                f"(hoppet over {skipped}, allerede ferdig {counts['already']}, "
                f"laast/konflikt {result.conflict + result.locked}, maa vurderes {counts['review']}).",
                focus_widget=self.tree_control_suggestions,
            )
            return

        autosaved = self._autosave_mapping()
        first_account, first_code = applied[0]
        self._refresh_core(focus_code=first_code)
        self._focus_mapping_account(first_account)
        try:
            self._focus_control_code(first_code)
        except Exception:
            pass
        applied_groups = 0
        try:
            applied_accounts = {account for account, _code in applied}
            applied_groups = int(
                candidates.loc[candidates["Konto"].astype(str).str.strip().isin(applied_accounts), "Rf1022GroupId"]
                .fillna("")
                .astype(str)
                .str.strip()
                .replace("", pd.NA)
                .dropna()
                .nunique()
            )
        except Exception:
            applied_groups = 0
        suffix_parts: list[str] = []
        if applied_groups:
            suffix_parts.append(f"{applied_groups} post(er)")
        skipped = result.skipped + counts["blocked"]
        if skipped:
            suffix_parts.append(f"hoppet over {skipped}")
        if counts["already"]:
            suffix_parts.append(f"{counts['already']} allerede ferdig")
        if result.locked:
            suffix_parts.append(f"{result.locked} laast")
        if result.conflict:
            suffix_parts.append(f"{result.conflict} konflikt")
        if counts["review"]:
            suffix_parts.append(f"{counts['review']} maa vurderes")
        suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
        if autosaved:
            self.status_var.set(
                f"Trygg auto-matching: brukte {len(applied)} sikre forslag{suffix} og lagret i klientmappen."
            )
        else:
            self.status_var.set(f"Trygg auto-matching: brukte {len(applied)} sikre forslag{suffix}.")
        self._select_primary_tab()

