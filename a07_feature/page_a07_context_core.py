from __future__ import annotations

from .page_a07_context_shared import *  # noqa: F403


class A07PageContextCoreMixin:
    def _control_code_name_map(self) -> dict[str, str]:
        code_names: dict[str, str] = {}
        for df in (
            getattr(self, "control_df", None),
            getattr(self, "a07_overview_df", None),
            getattr(getattr(self, "workspace", None), "a07_df", None),
        ):
            if df is None or getattr(df, "empty", True):
                continue
            if "Kode" not in df.columns or "Navn" not in df.columns:
                continue
            try:
                for _, row in df[["Kode", "Navn"]].dropna(subset=["Kode"]).iterrows():
                    code = str(row.get("Kode") or "").strip()
                    navn = str(row.get("Navn") or "").strip()
                    if code and navn and code not in code_names:
                        code_names[code] = navn
            except Exception:
                continue
        return code_names

    def _default_group_name(self, codes: Sequence[str]) -> str:
        return build_default_group_name(codes, code_names=self._control_code_name_map())

    def _next_group_id(self, codes: Sequence[str]) -> str:
        code_tokens = [str(code).strip() for code in codes if str(code).strip()]
        existing = self._existing_group_id_for_codes(code_tokens)
        if existing:
            return existing
        slug = "+".join(code_tokens) or "group"
        base = f"A07_GROUP:{slug}"
        if base not in self.workspace.groups:
            return base
        idx = 2
        while f"{base}:{idx}" in self.workspace.groups:
            idx += 1
        return f"{base}:{idx}"

    def _existing_group_id_for_codes(self, codes: Sequence[str]) -> str | None:
        wanted = a07_group_member_signature(codes)
        if not wanted:
            return None
        for group_id, group in (getattr(self.workspace, "groups", {}) or {}).items():
            current = a07_group_member_signature(getattr(group, "member_codes", ()) or ())
            if current == wanted:
                return str(group_id)
        return None

    def _notify_inline(self, message: str, *, focus_widget: object | None = None) -> None:
        self.status_var.set(str(message or "").strip())
        if focus_widget is None:
            return
        try:
            focus_widget.focus_set()
        except Exception:
            return

