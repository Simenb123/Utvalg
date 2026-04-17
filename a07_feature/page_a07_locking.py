from __future__ import annotations

from .page_a07_shared import *  # noqa: F401,F403


class A07PageLockingMixin:
    def _effective_mapping(self) -> dict[str, str]:
        cached = getattr(self, "effective_a07_mapping", None)
        if cached is not None:
            return dict(cached)
        return apply_groups_to_mapping(self.workspace.mapping, self.workspace.membership)

    def _effective_previous_mapping(self) -> dict[str, str]:
        cached = getattr(self, "effective_previous_a07_mapping", None)
        if cached is not None:
            return dict(cached)
        return apply_groups_to_mapping(self.previous_mapping, self.workspace.membership)

    def _locked_codes(self) -> set[str]:
        workspace = getattr(self, "workspace", None)
        locked = getattr(workspace, "locks", None)
        if not locked:
            return set()
        return {str(code).strip() for code in locked if str(code).strip()}

    def _locked_mapping_conflicts(
        self,
        accounts: Sequence[object] | None = None,
        *,
        target_code: object | None = None,
    ) -> list[str]:
        locked_getter = getattr(self, "_locked_codes", None)
        if callable(locked_getter):
            try:
                locked = {
                    str(code).strip()
                    for code in locked_getter()
                    if str(code).strip()
                }
            except Exception:
                locked = set()
        else:
            workspace = getattr(self, "workspace", None)
            locked = {
                str(code).strip()
                for code in (getattr(workspace, "locks", None) or ())
                if str(code).strip()
            }
        if not locked:
            return []

        workspace = getattr(self, "workspace", None)
        mapping = getattr(workspace, "mapping", None) or {}
        membership = getattr(workspace, "membership", None) or {}
        effective_mapping_getter = getattr(self, "_effective_mapping", None)
        if callable(effective_mapping_getter):
            try:
                effective_mapping = effective_mapping_getter()
            except Exception:
                effective_mapping = {
                    str(account).strip(): str(code).strip()
                    for account, code in mapping.items()
                    if str(account).strip()
                }
        else:
            effective_mapping = {
                str(account).strip(): str(code).strip()
                for account, code in mapping.items()
                if str(account).strip()
            }
        conflicts: list[str] = []

        target_code_s = str(target_code or "").strip()
        if target_code_s and target_code_s in locked:
            conflicts.append(target_code_s)
        target_group_code = str(membership.get(target_code_s) or "").strip()
        if target_group_code and target_group_code in locked and target_group_code not in conflicts:
            conflicts.append(target_group_code)

        for account in accounts or ():
            account_s = str(account or "").strip()
            if not account_s:
                continue
            current_code = str(effective_mapping.get(account_s) or mapping.get(account_s) or "").strip()
            if current_code and current_code in locked and current_code not in conflicts:
                conflicts.append(current_code)

        return conflicts

    def _notify_locked_conflicts(
        self,
        conflicts: Sequence[object],
        *,
        focus_widget: object | None = None,
    ) -> bool:
        codes = [str(code).strip() for code in conflicts if str(code).strip()]
        if not codes:
            return False
        preview = ", ".join(codes[:3])
        if len(codes) > 3:
            preview += ", ..."
        self._notify_inline(
            f"Endringen berorer laaste koder: {preview}. Laas opp for du endrer mapping.",
            focus_widget=focus_widget,
        )
        return True
