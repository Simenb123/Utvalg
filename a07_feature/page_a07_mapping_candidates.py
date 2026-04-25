from __future__ import annotations

from .page_a07_mapping_shared import *  # noqa: F403
from src.pages.a07.backend.candidate_actions import (
    global_auto_plan_action_counts,
    rf1022_candidate_summary_counts,
)


class A07PageMappingCandidatesMixin:
    def _safe_auto_matching_enabled(self) -> bool:
        return True

    def _auto_matching_protected_codes(self) -> set[str]:
        protected: set[str] = set()
        for frame_name in ("control_df", "a07_overview_df"):
            df = getattr(self, frame_name, None)
            if not isinstance(df, pd.DataFrame) or df.empty:
                continue
            if "Kode" not in df.columns or "Diff" not in df.columns:
                continue
            try:
                work = df.loc[:, ["Kode", "Diff"]].copy()
                work["Kode"] = work["Kode"].fillna("").astype(str).str.strip()
                work["DiffNum"] = pd.to_numeric(work["Diff"], errors="coerce")
                matches = work.loc[
                    work["Kode"].ne("")
                    & work["DiffNum"].notna()
                    & work["DiffNum"].abs().le(0.01),
                    "Kode",
                ]
                protected.update(str(code).strip() for code in matches.tolist() if str(code).strip())
            except Exception:
                continue
        return protected

    def _strict_auto_amount_is_exact(self, row: pd.Series | dict[str, object]) -> bool:
        getter = getattr(row, "get", None)
        if not callable(getter):
            return False
        evidence = str(getter("AmountEvidence", "") or "").strip().casefold()
        if evidence == "exact":
            return True
        try:
            diff = pd.to_numeric(pd.Series([getter("Diff", None)]), errors="coerce").iloc[0]
        except Exception:
            diff = None
        try:
            return bool(pd.notna(diff) and abs(float(diff)) <= 0.01)
        except Exception:
            return False

    def _auto_apply_strict_a07_suggestions(self) -> dict[str, object]:
        ensure_display = getattr(self, "_ensure_suggestion_display_fields", None)
        if callable(ensure_display):
            suggestions_df = ensure_display()
        else:
            suggestions_df = getattr(getattr(self, "workspace", None), "suggestions", None)
            if not isinstance(suggestions_df, pd.DataFrame):
                suggestions_df = _empty_suggestions_df()
        if suggestions_df is None or suggestions_df.empty or "Kode" not in suggestions_df.columns:
            return {"codes": [], "accounts": [], "autosaved": False, "focus_code": ""}

        workspace = getattr(self, "workspace", None)
        if workspace is None:
            return {"codes": [], "accounts": [], "autosaved": False, "focus_code": ""}
        if not isinstance(getattr(workspace, "mapping", None), dict):
            workspace.mapping = {}

        locked = _locked_codes_for(self)
        try:
            effective_mapping = {
                str(account).strip(): str(code).strip()
                for account, code in dict(self._effective_mapping() or {}).items()
                if str(account).strip()
            }
        except Exception:
            effective_mapping = {
                str(account).strip(): str(code).strip()
                for account, code in dict(workspace.mapping or {}).items()
                if str(account).strip()
            }

        codes = [
            str(code or "").strip()
            for code in suggestions_df["Kode"].dropna().astype(str).tolist()
            if str(code or "").strip()
        ]
        applied_codes: list[str] = []
        applied_accounts: list[str] = []
        reserved_accounts: set[str] = set()

        for code in dict.fromkeys(codes):
            if not code or code in locked:
                continue
            best_row = best_suggestion_row_for_code(suggestions_df, code, locked_codes=locked)
            if best_row is None:
                continue
            if not a07_suggestion_is_strict_auto(best_row):
                continue
            amount_checker = getattr(self, "_strict_auto_amount_is_exact", None)
            if callable(amount_checker):
                amount_is_exact = bool(amount_checker(best_row))
            else:
                amount_is_exact = bool(A07PageMappingCandidatesMixin._strict_auto_amount_is_exact(self, best_row))
            if not amount_is_exact:
                continue

            accounts = [account for account in _split_mapping_accounts(best_row.get("ForslagKontoer")) if account]
            if not accounts:
                continue
            if any(account in reserved_accounts for account in accounts):
                continue
            conflict = False
            for account in accounts:
                current_code = str(effective_mapping.get(account) or "").strip()
                if current_code and current_code != code:
                    conflict = True
                    break
            if conflict:
                continue

            before = {str(k): str(v) for k, v in workspace.mapping.items()}
            apply_suggestion_to_mapping(workspace.mapping, best_row)
            changed = [
                account
                for account in accounts
                if str(workspace.mapping.get(account) or "").strip() == code
                and str(before.get(account) or "").strip() != code
            ]
            if not changed:
                continue

            applied_codes.append(code)
            applied_accounts.extend(changed)
            reserved_accounts.update(accounts)
            for account in changed:
                effective_mapping[account] = code

        if not applied_accounts:
            return {"codes": [], "accounts": [], "autosaved": False, "focus_code": ""}

        autosaved = False
        try:
            autosaved = bool(self._autosave_mapping(source="auto", confidence=1.0))
        except Exception:
            autosaved = False
        focus_code = applied_codes[0] if applied_codes else ""
        return {
            "codes": applied_codes,
            "accounts": applied_accounts,
            "autosaved": autosaved,
            "focus_code": focus_code,
        }

    def _current_rf1022_candidate_df(self) -> pd.DataFrame:
        has_runtime_data = hasattr(self, "control_gl_df")
        try:
            return build_rf1022_candidate_df(
                self.control_gl_df,
                self._ensure_suggestion_display_fields(),
                self._selected_rf1022_group(),
                basis_col=getattr(getattr(self, "workspace", None), "basis_col", "Endring"),
            )
        except Exception:
            if not has_runtime_data:
                candidates = getattr(self, "rf1022_candidate_df", None)
                if isinstance(candidates, pd.DataFrame):
                    return candidates.copy()
            return pd.DataFrame()

    def _all_rf1022_candidate_df(self) -> pd.DataFrame:
        has_runtime_data = hasattr(self, "control_gl_df")
        try:
            group_ids = [group_id for group_id, _label in self._rf1022_group_menu_choices()]
            return build_rf1022_candidate_df_for_groups(
                self.control_gl_df,
                self._ensure_suggestion_display_fields(),
                group_ids,
                basis_col=getattr(getattr(self, "workspace", None), "basis_col", "Endring"),
            )
        except Exception:
            if not has_runtime_data:
                candidates = getattr(self, "rf1022_all_candidate_df", None)
                if isinstance(candidates, pd.DataFrame):
                    return candidates.copy()
            return pd.DataFrame()

    def _rf1022_candidates_with_target_codes(self, candidates: pd.DataFrame | None) -> pd.DataFrame:
        if candidates is None:
            return pd.DataFrame()
        work = candidates.copy()
        if work.empty:
            return work
        if "Kode" not in work.columns:
            work["Kode"] = ""
        if "Konto" not in work.columns:
            work["Konto"] = ""
        if "Rf1022GroupId" not in work.columns:
            work["Rf1022GroupId"] = ""
        for idx, row in work.iterrows():
            code = str(row.get("Kode") or "").strip()
            if code:
                continue
            account = str(row.get("Konto") or "").strip()
            group_id = str(row.get("Rf1022GroupId") or "").strip()
            resolved = str(self._resolve_rf1022_target_code(group_id, [account]) or "").strip()
            if resolved:
                work.at[idx, "Kode"] = resolved
        return work

    def _build_global_auto_mapping_plan(self, candidates: pd.DataFrame | None = None) -> pd.DataFrame:
        started = time.perf_counter()
        if candidates is None:
            candidates = self._all_rf1022_candidate_df()
        code_resolver = getattr(self, "_rf1022_candidates_with_target_codes", None)
        if callable(code_resolver):
            candidates = code_resolver(candidates)
        else:
            candidates = A07PageMappingCandidatesMixin._rf1022_candidates_with_target_codes(self, candidates)
        if candidates is None or candidates.empty:
            return pd.DataFrame()
        try:
            suggestions_df = self._ensure_suggestion_display_fields()
        except Exception:
            suggestions_df = pd.DataFrame()
        try:
            solved_codes = self._auto_matching_protected_codes()
        except Exception:
            solved_codes = set()
        plan = build_global_auto_mapping_plan(
            candidates,
            getattr(self, "control_gl_df", pd.DataFrame()),
            suggestions_df,
            dict(self._effective_mapping() or {}),
            solved_codes=solved_codes,
            locked_codes=_locked_codes_for(self),
            basis_col=getattr(getattr(self, "workspace", None), "basis_col", "Endring"),
            rulebook=getattr(self, "effective_rulebook", None),
        )
        try:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._diag(f"global_auto_plan rows={len(plan.index)} elapsed_ms={elapsed_ms}")
        except Exception:
            pass
        return plan

    def _global_auto_plan_action_counts(plan: pd.DataFrame | None) -> dict[str, int]:
        return global_auto_plan_action_counts(plan)

    def _rf1022_candidate_action_counts(self, candidates: pd.DataFrame | None) -> dict[str, int]:
        return self.get_global_auto_plan_summary(candidates)

    def get_global_auto_plan_summary(self, candidates: pd.DataFrame | None = None) -> dict[str, int]:
        """Cheap UI precheck; click handlers still build the full guarded plan."""
        started = time.perf_counter()
        if candidates is None:
            candidates = self._all_rf1022_candidate_df()
        code_resolver = getattr(self, "_rf1022_candidates_with_target_codes", None)
        if callable(code_resolver):
            try:
                candidates = code_resolver(candidates)
            except Exception:
                candidates = pd.DataFrame()

        try:
            locked = _locked_codes_for(self)
        except Exception:
            locked = set()
        try:
            solved_codes = self._auto_matching_protected_codes()
        except Exception:
            solved_codes = set()
        try:
            current_mapping = dict(self._effective_mapping() or {})
        except Exception:
            current_mapping = dict(getattr(getattr(self, "workspace", None), "mapping", None) or {})
        gl_accounts: set[str] = set()
        gl_df = getattr(self, "control_gl_df", None)
        if isinstance(gl_df, pd.DataFrame) and not gl_df.empty and "Konto" in gl_df.columns:
            try:
                gl_accounts = {str(value).strip() for value in gl_df["Konto"].dropna().astype(str) if str(value).strip()}
            except Exception:
                gl_accounts = set()

        counts = rf1022_candidate_summary_counts(
            candidates,
            locked_codes=locked,
            solved_codes=solved_codes,
            current_mapping=current_mapping,
            gl_accounts=gl_accounts,
        )
        try:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            candidate_count = len(candidates.index) if isinstance(candidates, pd.DataFrame) else 0
            self._diag(f"global_auto_summary candidates={candidate_count} actionable={counts['actionable']} elapsed_ms={elapsed_ms}")
        except Exception:
            pass
        return counts

    def _selected_rf1022_candidate_row(self) -> pd.Series | None:
        tree = getattr(self, "tree_control_suggestions", None)
        if tree is None:
            return None
        try:
            selection = tree.selection()
        except Exception:
            selection = ()
        if not selection:
            return None
        account = str(selection[0] or "").strip()
        if not account:
            return None
        candidates = self._current_rf1022_candidate_df()
        if candidates.empty or "Konto" not in candidates.columns:
            return None
        matches = candidates.loc[candidates["Konto"].astype(str).str.strip() == account]
        if matches.empty:
            return None
        return matches.iloc[0]

