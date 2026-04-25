from __future__ import annotations

from .support_render_shared import *  # noqa: F403


class A07PageSupportPanelMixin:
    def _update_mapping_review_buttons(self) -> None:
        button = getattr(self, "btn_next_mapping_problem", None)
        if button is None:
            return
        summary = build_mapping_review_summary(getattr(self, "control_selected_accounts_df", None))
        try:
            button.state(["!disabled"] if summary.get("kritiske", 0) else ["disabled"])
        except Exception:
            pass

    def _focus_next_control_account_problem(self) -> None:
        tree = getattr(self, "tree_control_accounts", None)
        if tree is None:
            return
        try:
            current_selection = tree.selection()
            current_account = str(current_selection[0]).strip() if current_selection else ""
        except Exception:
            current_account = ""
        target = next_mapping_review_problem_account(
            getattr(self, "control_selected_accounts_df", None),
            current_account,
        )
        status_var = getattr(self, "status_var", None)
        if not target:
            try:
                status_var.set("Ingen kritiske koblinger i gjeldende visning.")
            except Exception:
                pass
            return
        try:
            children = tree.get_children()
        except Exception:
            children = ()
        if target not in children:
            return
        try:
            did_select = self._set_tree_selection(tree, target, reveal=True, focus=True)
        except TypeError:
            did_select = self._set_tree_selection(tree, target)
        if did_select:
            try:
                tree.focus_set()
            except Exception:
                pass
            try:
                status_var.set(f"Neste problem: konto {target}.")
            except Exception:
                pass

    def _set_control_smart_button(
        self,
        *,
        text: str = "",
        command=None,
        enabled: bool = False,
        visible: bool = True,
    ) -> None:
        smart_button = getattr(self, "btn_control_smart", None)
        if smart_button is None:
            return
        control_panel = getattr(self, "control_panel", None)
        if bool(getattr(self, "_control_smart_button_removed", False)):
            try:
                smart_button.state(["disabled"])
            except Exception:
                pass
            try:
                smart_button.pack_forget()
            except Exception:
                pass
            if control_panel is not None and bool(getattr(self, "_compact_control_status", False)):
                try:
                    control_panel.pack_forget()
                except Exception:
                    pass
            return
        if not visible:
            try:
                smart_button.state(["disabled"])
            except Exception:
                pass
            try:
                smart_button.pack_forget()
            except Exception:
                pass
            if control_panel is not None:
                try:
                    control_panel.pack_forget()
                except Exception:
                    pass
            return
        if control_panel is not None:
            try:
                if not bool(control_panel.winfo_manager()):
                    lower_body = getattr(self, "control_lower_body", None)
                    if lower_body is not None:
                        control_panel.pack(fill="x", pady=(0, 2), before=lower_body)
                    else:
                        control_panel.pack(fill="x", pady=(0, 2))
            except Exception:
                pass
        try:
            if not bool(smart_button.winfo_manager()):
                smart_button.pack(side="right")
        except Exception:
            pass
        try:
            if command is not None:
                smart_button.configure(text=text, command=command)
            else:
                smart_button.configure(text=text)
        except Exception:
            pass
        try:
            smart_button.state(["!disabled"] if enabled else ["disabled"])
        except Exception:
            pass

    def _update_summary(self) -> None:
        client, year = self._session_context(session)
        ctx_parts = [x for x in (client, year) if x]
        context_text = " / ".join(ctx_parts) if ctx_parts else "ingen klientkontekst"

        visible_control_df = filter_control_visible_codes_df(self.control_df)
        unsolved_count = a07_control_status.count_pending_control_items(visible_control_df)
        self.summary_var.set(
            " | ".join(
                [
                    context_text,
                    f"{unsolved_count} åpne",
                    f"Umappede {len(self.unmapped_df)}",
                ]
            )
        )

        if self.a07_path is None:
            if client and year:
                self.a07_path_var.set(
                    f"A07: ingen lagret A07-kilde i {default_a07_source_path(client, year)}"
                )
            else:
                self.a07_path_var.set("A07: ikke valgt")
        else:
            self.a07_path_var.set(f"A07: {self.a07_path}")

        if self.tb_path is None:
            if client and year:
                self.tb_path_var.set("Saldobalanse: ingen aktiv SB-versjon for klient/aar")
            else:
                self.tb_path_var.set("Saldobalanse: klient/aar ikke valgt")
        else:
            self.tb_path_var.set(f"Saldobalanse: aktiv versjon {self.tb_path}")

        if self.mapping_path is None:
            if client and year:
                self.mapping_path_var.set(
                    f"Mapping: ikke lagret enna ({suggest_default_mapping_path(self.a07_path, client=client, year=year)})"
                )
            else:
                self.mapping_path_var.set("Mapping: ikke valgt")
        else:
            self.mapping_path_var.set(f"Mapping: {self.mapping_path}")

        if self.rulebook_path is None:
            self.rulebook_path_var.set(f"Rulebook: standard heuristikk ({default_global_rulebook_path()})")
        else:
            self.rulebook_path_var.set(f"Rulebook: {self.rulebook_path}")

        if self.previous_mapping_year is None:
            self.history_path_var.set("Historikk: ingen tidligere A07-mapping funnet")
        elif self.previous_mapping_path is None:
            self.history_path_var.set(
                f"Historikk: bruker profilbasert mapping fra {self.previous_mapping_year}"
            )
        else:
            self.history_path_var.set(
                f"Historikk: bruker prior fra {self.previous_mapping_year} ({self.previous_mapping_path})"
            )

        self.control_bucket_var.set(a07_control_status.build_control_bucket_summary(visible_control_df))
        self.details_var.set("Bruk Kilder... for filoversikt.")

