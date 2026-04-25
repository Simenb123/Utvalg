from __future__ import annotations

from ..page_a07_constants import (
    _CONTROL_GL_MAPPING_LABELS,
    _CONTROL_GL_SERIES_LABELS,
    _CONTROL_VIEW_LABELS,
)
from ..page_a07_dialogs import remove_mapping_accounts
from ..page_a07_env import messagebox


class A07PageFocusHelpersMixin:
    def _focus_mapping_account(self, konto: str) -> None:
        konto_s = str(konto or "").strip()
        if not konto_s:
            return
        try:
            children = self.tree_control_gl.get_children()
        except Exception:
            children = ()
        if konto_s not in children:
            try:
                changed = False
                if bool(self.control_gl_unmapped_only_var.get()):
                    self.control_gl_unmapped_only_var.set(False)
                    changed = True
                mapping_var = getattr(self, "control_gl_mapping_filter_var", None)
                mapping_label_var = getattr(self, "control_gl_mapping_filter_label_var", None)
                if mapping_var is not None and str(mapping_var.get() or "").strip() != "alle":
                    mapping_var.set("alle")
                    changed = True
                if mapping_label_var is not None and str(mapping_label_var.get() or "").strip() != _CONTROL_GL_MAPPING_LABELS["alle"]:
                    mapping_label_var.set(_CONTROL_GL_MAPPING_LABELS["alle"])
                    changed = True
                series_var = getattr(self, "control_gl_series_filter_var", None)
                series_label_var = getattr(self, "control_gl_series_filter_label_var", None)
                series_vars = getattr(self, "control_gl_series_vars", None)
                if isinstance(series_vars, list):
                    for var in series_vars:
                        try:
                            if bool(var.get()):
                                var.set(0)
                                changed = True
                        except Exception:
                            pass
                if series_var is not None and str(series_var.get() or "").strip() != "alle":
                    series_var.set("alle")
                    changed = True
                if series_label_var is not None and str(series_label_var.get() or "").strip() != _CONTROL_GL_SERIES_LABELS["alle"]:
                    series_label_var.set(_CONTROL_GL_SERIES_LABELS["alle"])
                    changed = True
                if str(self.control_gl_filter_var.get() or "").strip():
                    self.control_gl_filter_var.set("")
                    changed = True
                if changed:
                    self._refresh_control_gl_tree()
            except Exception:
                pass
        try:
            self.tree_control_gl.selection_set(konto_s)
            self.tree_control_gl.focus(konto_s)
            self.tree_control_gl.see(konto_s)
        except Exception:
            return
        self._sync_control_account_selection(konto_s)

    def _focus_control_code(self, code: str | None) -> None:
        code_s = str(code or "").strip()
        if not code_s:
            return
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        if callable(selected_work_level):
            try:
                if selected_work_level() == "rf1022":
                    control_df = getattr(self, "control_df", None)
                    if control_df is not None and not getattr(control_df, "empty", True):
                        try:
                            matches = control_df.loc[
                                control_df["Kode"].astype(str).str.strip() == code_s
                            ]
                        except Exception:
                            matches = None
                        if matches is not None and not getattr(matches, "empty", True):
                            try:
                                group_id = str(matches.iloc[0].get("Rf1022GroupId") or "").strip()
                            except Exception:
                                group_id = ""
                            if group_id:
                                try:
                                    self.workspace.selected_code = code_s
                                except Exception:
                                    pass
                                self._selected_rf1022_group_id = group_id
                                code_s = group_id
            except Exception:
                pass
        if bool(getattr(self, "_refresh_in_progress", False)):
            self._pending_focus_code = code_s
            return
        try:
            children = self.tree_a07.get_children()
        except Exception:
            children = ()
        if code_s not in children:
            known = False
            for df_name, columns in (
                ("control_df", ("Kode",)),
                ("rf1022_overview_df", ("GroupId", "Gruppe")),
                ("groups_df", ("GroupId", "Gruppe")),
            ):
                df = getattr(self, df_name, None)
                if df is None or getattr(df, "empty", True):
                    continue
                for column in columns:
                    if column not in getattr(df, "columns", ()):
                        continue
                    try:
                        values = df[column].fillna("").astype(str).str.strip()
                        if bool(values.eq(code_s).any()):
                            known = True
                            break
                    except Exception:
                        continue
                if known:
                    break
            if not known:
                try:
                    self._diag(f"focus_control_code skipped unknown code={code_s!r}")
                except Exception:
                    pass
                return
            attempts = getattr(self, "_focus_control_code_attempts", None)
            if not isinstance(attempts, dict):
                attempts = {}
                self._focus_control_code_attempts = attempts
            attempt_key = f"{code_s}"
            attempt_count = int(attempts.get(attempt_key, 0) or 0)
            if attempt_count >= 2:
                try:
                    self._diag(f"focus_control_code stopped after attempts code={code_s!r}")
                except Exception:
                    pass
                return
            attempts[attempt_key] = attempt_count + 1
            try:
                self.a07_filter_var.set("alle")
                self.a07_filter_label_var.set(_CONTROL_VIEW_LABELS["alle"])
                try:
                    self.a07_match_filter_var.set("alle")
                except Exception:
                    pass
                self.a07_filter_widget.set(_CONTROL_VIEW_LABELS["alle"])
            except Exception:
                pass
            self._schedule_a07_refresh(
                delay_ms=1,
                on_complete=lambda code=code_s: self._focus_control_code(code),
            )
            return
        attempts = getattr(self, "_focus_control_code_attempts", None)
        if isinstance(attempts, dict):
            attempts.pop(code_s, None)
        if not self._set_tree_selection(self.tree_a07, code_s, reveal=True, focus=True):
            return
        try:
            if code_s in self.tree_groups.get_children():
                self._set_tree_selection(self.tree_groups, code_s, reveal=True, focus=True)
        except Exception:
            pass
        try:
            self.after_idle(self._on_control_selection_changed)
        except Exception:
            self._on_control_selection_changed()

    def _selected_control_account_ids(self) -> list[str]:
        try:
            selection = self.tree_control_accounts.selection()
        except Exception:
            selection = ()

        accounts: list[str] = []
        seen: set[str] = set()
        for iid in selection:
            konto = str(iid).strip()
            if not konto or konto in seen:
                continue
            accounts.append(konto)
            seen.add(konto)
        return accounts

    def _sync_control_account_selection(self, konto: str | None) -> None:
        konto_s = str(konto or "").strip()
        if not konto_s:
            return
        try:
            children = self.tree_control_accounts.get_children()
        except Exception:
            children = ()
        if konto_s not in children:
            return
        selector = getattr(self, "_set_tree_selection", None)
        if callable(selector):
            try:
                selector(self.tree_control_accounts, konto_s, reveal=False)
            except TypeError:
                selector(self.tree_control_accounts, konto_s)
            return
        try:
            self.tree_control_accounts.selection_set(konto_s)
            self.tree_control_accounts.focus(konto_s)
            self.tree_control_accounts.see(konto_s)
        except Exception:
            pass

    def _clear_control_gl_selection(self) -> None:
        tree = getattr(self, "tree_control_gl", None)
        if tree is None:
            return
        try:
            selection = tuple(tree.selection())
        except Exception:
            selection = ()
        if selection:
            try:
                tree.selection_remove(selection)
            except Exception:
                try:
                    tree.selection_set(())
                except Exception:
                    pass
        try:
            tree.focus("")
        except Exception:
            pass

    def _focus_selected_control_account_in_gl(self, *, allow_multi: bool = True) -> None:
        suppressed_check = getattr(self, "_is_tree_selection_suppressed", None)
        if callable(suppressed_check) and suppressed_check(getattr(self, "tree_control_accounts", None)):
            return
        accounts = self._selected_control_account_ids()
        if not accounts:
            return
        if len(accounts) > 1 and not allow_multi:
            return
        self._focus_mapping_account(accounts[0])

    def _remove_selected_control_accounts(self) -> None:
        accounts = self._selected_control_account_ids()
        if not accounts:
            self._notify_inline(
                "Velg en eller flere mappede kontoer nederst fÃ¸rst.",
                focus_widget=self.tree_control_accounts,
            )
            return

        remover = getattr(self, "_remove_mapping_accounts_checked", None)
        if callable(remover):
            remover(
                accounts,
                focus_widget=self.tree_control_accounts,
                refresh="all",
                source_label="Fjernet mapping fra",
            )
            return

        removed = remove_mapping_accounts(self.workspace.mapping, accounts)
        if not removed:
            self._notify_inline(
                "Valgte kontoer har ingen kode Ã¥ fjerne.",
                focus_widget=self.tree_control_accounts,
            )
            return

        try:
            autosaved = self._autosave_mapping()
            self._refresh_all()
            self._focus_mapping_account(removed[0])
            count = len(removed)
            if autosaved:
                self.status_var.set(f"Fjernet mapping fra {count} konto(er) og lagret endringen.")
            else:
                self.status_var.set(f"Fjernet mapping fra {count} konto(er).")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke fjerne mapping fra konto:\n{exc}")

    def _focus_unmapped_account(self, konto: str) -> None:
        konto_s = str(konto or "").strip()
        if not konto_s:
            return
        self._set_tree_selection(self.tree_unmapped, konto_s, reveal=True, focus=True)


__all__ = ["A07PageFocusHelpersMixin"]
