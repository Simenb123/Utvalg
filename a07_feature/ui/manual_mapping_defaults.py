from __future__ import annotations

from ..page_a07_constants import _CONTROL_GL_COLUMNS


class A07PageManualMappingDefaultsMixin:
    def _manual_mapping_defaults(
        self,
        *,
        preferred_account: str | None = None,
        preferred_code: str | None = None,
    ) -> tuple[str | None, str | None]:
        konto = str(preferred_account or "").strip() or None
        kode = str(preferred_code or "").strip() or None

        control_gl_values = self._selected_tree_values(self.tree_control_gl)
        if control_gl_values and konto is None:
            konto = str(control_gl_values[0]).strip() or None
            control_gl_column_ids = [column_id for column_id, *_rest in _CONTROL_GL_COLUMNS]
            try:
                code_index = control_gl_column_ids.index("Kode")
            except ValueError:
                code_index = -1
            if kode is None and code_index >= 0 and len(control_gl_values) > code_index:
                raw_code = str(control_gl_values[code_index]).strip()
                numeric_probe = raw_code.replace(" ", "").replace("\xa0", "").replace(",", ".")
                if raw_code and not numeric_probe.replace(".", "", 1).replace("-", "", 1).isdigit():
                    kode = raw_code

        unmapped_values = self._selected_tree_values(self.tree_unmapped)
        if unmapped_values and konto is None:
            konto = str(unmapped_values[0]).strip() or None

        control_account_values = self._selected_tree_values(self.tree_control_accounts)
        if control_account_values and konto is None:
            konto = str(control_account_values[0]).strip() or None

        if kode is None:
            select_code = getattr(self, "_selected_code_from_tree", None)
            if callable(select_code):
                try:
                    kode = select_code(self.tree_a07)
                except Exception:
                    kode = None
        if kode is None:
            for tree in (getattr(self, "tree_control_suggestions", None),):
                if tree is None:
                    continue
                values = self._selected_tree_values(tree)
                if values:
                    kode = str(values[0]).strip() or None
                    if kode:
                        break

        return konto, kode


__all__ = ["A07PageManualMappingDefaultsMixin"]
