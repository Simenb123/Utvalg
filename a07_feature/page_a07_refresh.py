from __future__ import annotations

import faulthandler
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk
from typing import Callable

from .page_a07_constants import _A07_DIAGNOSTICS_ENABLED, _A07_DIAGNOSTICS_LOG
from .page_a07_env import messagebox, session
from .page_a07_refresh_state import A07PageRefreshStateMixin


class A07PageRefreshMixin(A07PageRefreshStateMixin):
    def _diag(self, message: str) -> None:
        if not _A07_DIAGNOSTICS_ENABLED:
            return
        try:
            stamp = time.strftime("%H:%M:%S")
            millis = int((time.time() % 1) * 1000)
            with _A07_DIAGNOSTICS_LOG.open("a", encoding="utf-8") as handle:
                handle.write(f"[{stamp}.{millis:03d}] {message}\n")
        except Exception:
            pass

    def _tree_debug_name(self, tree: ttk.Treeview | None) -> str:
        if tree is None:
            return "<none>"
        try:
            return str(tree.winfo_name() or tree)
        except Exception:
            return f"tree-{id(tree)}"

    def _cancel_refresh_watchdog(self) -> None:
        job = getattr(self, "_refresh_watchdog_job", None)
        if not job:
            return
        if isinstance(job, str):
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._refresh_watchdog_job = None

    def _schedule_refresh_watchdog(self, label: str, token: int) -> None:
        if not _A07_DIAGNOSTICS_ENABLED:
            return
        self._cancel_refresh_watchdog()

        def _thread_watchdog() -> None:
            time.sleep(2.0)
            if not bool(getattr(self, "_refresh_in_progress", False)):
                return
            active_token = int(getattr(self, "_refresh_generation", 0))
            if active_token != int(token):
                return
            try:
                with _A07_DIAGNOSTICS_LOG.open("a", encoding="utf-8") as handle:
                    stamp = time.strftime("%H:%M:%S")
                    millis = int((time.time() % 1) * 1000)
                    handle.write(
                        f"[{stamp}.{millis:03d}] watchdog {label} token={token} "
                        f"active_token={active_token} "
                        f"pending_session={self._pending_session_refresh} "
                        f"pending_support={self._pending_support_refresh} "
                        f"support_ready={self._support_views_ready} "
                        f"support_dirty={self._support_views_dirty} "
                        f"support_requested={getattr(self, '_support_requested', None)} "
                        f"restore_alive={bool(self._restore_thread and self._restore_thread.is_alive())} "
                        f"core_alive={bool(self._core_refresh_thread and self._core_refresh_thread.is_alive())} "
                        f"support_alive={bool(self._support_refresh_thread and self._support_refresh_thread.is_alive())}\n"
                    )
                    handle.write(f"[{stamp}.{millis:03d}] watchdog-stack {label} token={token}\n")
                    faulthandler.dump_traceback(file=handle, all_threads=True)
                    handle.write("\n")
            except Exception:
                try:
                    stack_dump = ""
                    current_frames = sys._current_frames()
                    thread_frames: list[str] = []
                    for thread in threading.enumerate():
                        ident = getattr(thread, "ident", None)
                        if ident is None:
                            continue
                        frame = current_frames.get(ident)
                        if frame is None:
                            continue
                        rendered = "".join(traceback.format_stack(frame, limit=20))
                        thread_frames.append(
                            f"--- thread={thread.name} ident={ident} alive={thread.is_alive()} ---\n{rendered}"
                        )
                    stack_dump = "\n".join(thread_frames).strip()
                    if stack_dump:
                        self._diag(f"watchdog-stack-fallback {label} token={token}\n{stack_dump}")
                except Exception:
                    pass

        thread = threading.Thread(
            target=_thread_watchdog,
            name=f"A07Watchdog-{label}-{token}",
            daemon=True,
        )
        self._refresh_watchdog_job = thread
        thread.start()

    def refresh_from_session(self, session_module=session) -> None:
        if self._refresh_in_progress:
            self._pending_session_refresh = True
            return
        context = self._session_context(session_module)
        if context != self._context_key:
            self._context_key = context
            self._restore_context_state(*context)
            return
        snapshot = self._current_context_snapshot(*context)
        if snapshot != self._context_snapshot:
            self._context_snapshot = snapshot
            self._restore_context_state(*context)
            return
        self._update_summary()

    def _schedule_session_refresh(self, delay_ms: int = 1) -> None:
        if self._session_refresh_job is not None:
            try:
                self.after_cancel(self._session_refresh_job)
            except Exception:
                pass
            self._session_refresh_job = None

        def _run() -> None:
            self._session_refresh_job = None
            self.refresh_from_session()

        try:
            self._session_refresh_job = self.after(delay_ms, _run)
        except Exception:
            self.refresh_from_session()

    def _cancel_scheduled_job(self, attr_name: str) -> None:
        job = getattr(self, attr_name, None)
        if not job:
            return
        try:
            self.after_cancel(job)
        except Exception:
            pass
        setattr(self, attr_name, None)

    def _schedule_control_gl_refresh(
        self,
        delay_ms: int = 75,
        *,
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        self._cancel_scheduled_job("_control_gl_refresh_job")

        def _run() -> None:
            self._control_gl_refresh_job = None
            self._refresh_control_gl_tree_chunked(on_complete=on_complete)

        try:
            self._control_gl_refresh_job = self.after(delay_ms, _run)
        except Exception:
            _run()

    def _schedule_a07_refresh(
        self,
        delay_ms: int = 75,
        *,
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        self._cancel_scheduled_job("_a07_refresh_job")

        def _run() -> None:
            self._a07_refresh_job = None
            self._refresh_a07_tree_chunked(on_complete=on_complete)

        try:
            self._a07_refresh_job = self.after(delay_ms, _run)
        except Exception:
            _run()

    def _schedule_control_selection_followup(self) -> None:
        self._cancel_scheduled_job("_control_selection_followup_job")

        def _run() -> None:
            self._control_selection_followup_job = None
            if bool(getattr(self, "_skip_initial_control_followup", False)):
                self._skip_initial_control_followup = False
                self._diag("skip initial control selection followup")
                self._update_control_transfer_buttons()
                return
            support_requested = bool(getattr(self, "_support_requested", True))
            active_tab = self._active_support_tab_key()
            if (
                bool(getattr(self, "_control_details_visible", False))
                and support_requested
                and self._support_views_ready
                and active_tab == "suggestions"
            ):
                self._refresh_suggestions_tree()
            if bool(getattr(self, "_control_details_visible", False)) and support_requested:
                if active_tab == "history" and not bool(getattr(self, "_history_compare_ready", False)):
                    self._schedule_support_refresh()
                elif self._support_views_ready:
                    self._refresh_control_support_trees()
                else:
                    self._schedule_support_refresh()
            self._update_control_transfer_buttons()

        try:
            self._control_selection_followup_job = self.after(40, _run)
        except Exception:
            _run()

    def _cancel_support_refresh(self) -> None:
        if self._support_refresh_job is None:
            return
        try:
            self.after_cancel(self._support_refresh_job)
        except Exception:
            pass
        self._support_refresh_job = None

    def _schedule_support_refresh(self) -> None:
        if (
            not bool(getattr(self, "_control_details_visible", False))
            or not bool(getattr(self, "_support_requested", True))
        ):
            self._pending_support_refresh = False
            return
        if self._refresh_in_progress:
            self._pending_support_refresh = True
            return
        if (
            self._active_support_tab_key() != "history"
            or bool(getattr(self, "_history_compare_ready", False))
        ):
            if self._support_views_ready and not self._support_views_dirty:
                self._render_active_support_tab(force=True)
            return
        self._cancel_support_refresh()

        def _run() -> None:
            self._support_refresh_job = None
            self._refresh_support_views()

        try:
            self._support_refresh_job = self.after(60, _run)
        except Exception:
            self._refresh_support_views()

    def _cancel_core_refresh_jobs(self) -> None:
        for attr_name in (
            "_session_refresh_job",
            "_control_gl_refresh_job",
            "_a07_refresh_job",
            "_control_selection_followup_job",
        ):
            self._cancel_scheduled_job(attr_name)

        for tree_name in ("tree_control_gl", "tree_a07"):
            tree = getattr(self, tree_name, None)
            if tree is None:
                continue
            try:
                self._cancel_tree_fill(tree)
            except Exception:
                pass
            key = self._tree_fill_key(tree)
            try:
                self._tree_fill_tokens[key] = int(self._tree_fill_tokens.get(key, 0)) + 1
            except Exception:
                pass

    def _next_refresh_generation(self) -> int:
        self._refresh_generation += 1
        return self._refresh_generation

    def _on_visible(self, _event: tk.Event | None = None) -> None:
        try:
            if _event is not None and getattr(_event, "widget", None) is not self:
                return
        except Exception:
            pass
        try:
            if not self.winfo_viewable():
                return
        except Exception:
            pass
        if self._refresh_in_progress:
            return
        try:
            if not self._context_has_changed():
                return
        except Exception:
            pass
        self._schedule_session_refresh(delay_ms=50)

    def _on_notebook_tab_changed(self, event: tk.Event | None = None) -> None:
        if event is None:
            return
        try:
            notebook = event.widget
            selected = notebook.nametowidget(notebook.select())
        except Exception:
            return
        if selected is self:
            if self._refresh_in_progress:
                return
            try:
                if not self._context_has_changed():
                    return
            except Exception:
                pass
            self._schedule_session_refresh(delay_ms=50)

    def _refresh_context(self, *, refresh_tb: bool = False) -> None:
        if self._refresh_in_progress:
            self._pending_session_refresh = True
            return
        client, year = self._session_context(session)
        if refresh_tb:
            self._invalidate_active_tb_path_cache(client, year)
        self._context_key = (client, year)
        self._restore_context_state(client, year)

    def _refresh_core(self, *, focus_code: str | None = None, reason: str | None = None) -> None:
        if self._refresh_in_progress:
            self._pending_session_refresh = True
            if focus_code:
                self._pending_focus_code = str(focus_code).strip() or None
            if reason:
                self._diag(f"refresh_core deferred reason={reason}")
            return
        if focus_code:
            self._pending_focus_code = str(focus_code).strip() or None
        if reason:
            self._diag(f"refresh_core reason={reason}")
        self._refresh_in_progress = True
        self._pending_session_refresh = False
        self._pending_support_refresh = False
        self._support_requested = False
        cancel_job = getattr(self, "_cancel_scheduled_job", None)
        if callable(cancel_job):
            cancel_job("_session_refresh_job")
        self._cancel_core_refresh_jobs()
        self._cancel_support_refresh()
        self._support_views_ready = False
        self._start_core_refresh()

    def _refresh_support(self) -> None:
        self._schedule_support_refresh()

    def _refresh_clicked(self) -> None:
        if self.workspace.gl_df.empty:
            self._sync_active_trial_balance(refresh=False)

        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            self._notify_inline(
                "Last A07 og bruk aktiv saldobalanse for valgt klient/aar for du oppdaterer.",
                focus_widget=self,
            )
            return
        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            messagebox.showinfo(
                "A07",
                "Last A07 JSON og sÃƒÂ¸rg for at valgt klient/aar har en aktiv saldobalanse i Utvalg.",
            )
            return

        try:
            selected_code = self._selected_control_code()
            self._pending_focus_code = str(selected_code or "").strip() or None
            refresh_context = getattr(self, "_refresh_context", None)
            if callable(refresh_context):
                refresh_context(refresh_tb=True)
            else:
                self._refresh_all()
            self.status_var.set("A07-kontroll og forslag er oppdatert.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke oppdatere A07-visningen:\n{exc}")

    def _refresh_all(self) -> None:
        refresh_core = getattr(self, "_refresh_core", None)
        if callable(refresh_core):
            refresh_core()
            return

        cancel_core_refresh_jobs = getattr(self, "_cancel_core_refresh_jobs", None)
        if callable(cancel_core_refresh_jobs):
            cancel_core_refresh_jobs()
        cancel_support_refresh = getattr(self, "_cancel_support_refresh", None)
        if callable(cancel_support_refresh):
            cancel_support_refresh()
        self._pending_session_refresh = False
        self._pending_support_refresh = False
        self._support_views_ready = False
        self._refresh_in_progress = True
        start_core_refresh = getattr(self, "_start_core_refresh", None)
        if callable(start_core_refresh):
            start_core_refresh()

    def _refresh_support_views(self) -> None:
        if (
            not bool(getattr(self, "_control_details_visible", False))
            or not bool(getattr(self, "_support_requested", True))
        ):
            self._pending_support_refresh = False
            return
        active_tab_getter = getattr(self, "_active_support_tab_key", None)
        loaded_tabs = getattr(self, "_loaded_support_tabs", set())
        active_tab = active_tab_getter() if callable(active_tab_getter) else None
        history_ready = bool(getattr(self, "_history_compare_ready", False))
        if self._support_views_ready and not self._support_views_dirty:
            if active_tab == "history" and not history_ready:
                if self._support_refresh_thread is not None:
                    return
                self._pending_support_refresh = False
                self._start_support_refresh()
                return
            if not callable(active_tab_getter) or active_tab in loaded_tabs:
                self._render_active_support_tab()
            return
        if self._refresh_in_progress:
            self._pending_support_refresh = True
            return
        if self._support_refresh_thread is not None:
            return
        self._pending_support_refresh = False
        self._start_support_refresh()
