from __future__ import annotations

from a07_feature.page_windows import (
    open_mapping_overview,
    open_matcher_admin,
    open_source_overview,
)

from .page_a07_constants import _MAPPING_COLUMNS, _MATCHER_SETTINGS_DEFAULTS
from .page_a07_dialogs import _format_aliases_editor, _parse_aliases_editor
from .page_a07_env import session


class A07PageProjectToolsMixin:
    def _open_source_overview(self) -> None:
        open_source_overview(self)

    def _open_mapping_overview(self) -> None:
        open_mapping_overview(self, _MAPPING_COLUMNS)

    def _open_a07_rulebook_admin(self) -> None:
        app = getattr(session, "APP", None)
        admin_page = getattr(app, "page_admin", None)
        notebook = getattr(app, "nb", None)
        if admin_page is not None and notebook is not None:
            try:
                notebook.select(admin_page)
            except Exception:
                pass
            show_rulebook = getattr(admin_page, "show_a07_rulebook", None)
            if callable(show_rulebook):
                try:
                    current_code_getter = getattr(self, "_selected_control_code", None)
                    rule_id = current_code_getter() if callable(current_code_getter) else None
                    show_rulebook(rule_id=rule_id)
                    self.status_var.set("Åpnet Admin > A07-regler.")
                    return
                except TypeError:
                    try:
                        show_rulebook()
                        self.status_var.set("Åpnet Admin > A07-regler.")
                        return
                    except Exception:
                        pass
                except Exception:
                    pass
        self._open_matcher_admin()

    def _open_matcher_admin(self) -> None:
        self._open_legacy_matcher_admin()

    def _open_legacy_matcher_admin(self) -> None:
        open_matcher_admin(
            self,
            matcher_settings_defaults=_MATCHER_SETTINGS_DEFAULTS,
            format_aliases_editor=_format_aliases_editor,
            parse_aliases_editor=_parse_aliases_editor,
        )
