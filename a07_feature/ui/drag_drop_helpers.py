from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

try:
    from ..page_a07_constants import _CONTROL_DRAG_IDLE_HINT
except ImportError:  # pragma: no cover - IDE/direct-run fallback
    project_root = Path(__file__).resolve().parents[2]
    project_root_s = str(project_root)
    if project_root_s not in sys.path:
        sys.path.insert(0, project_root_s)
    from a07_feature.page_a07_constants import _CONTROL_DRAG_IDLE_HINT

_DRAG_GHOST_ACTIVE_BG = "#1F6FEB"
_DRAG_GHOST_READY_BG = "#2F6F3E"
_DRAG_GHOST_TEXT = "#FFFFFF"


class A07PageDragDropHelpersMixin:
    def _drag_target_kind_label(self) -> str:
        try:
            work_level_getter = getattr(self, "_selected_control_work_level", None)
            work_level = work_level_getter() if callable(work_level_getter) else "a07"
        except Exception:
            work_level = "a07"
        return "RF-1022-post" if str(work_level or "").strip() == "rf1022" else "A07-kode"

    def _drag_source_summary(self) -> str:
        accounts = self._current_drag_accounts()
        if not accounts:
            return ""
        if len(accounts) == 1:
            return f"konto {accounts[0]}"
        preview = ", ".join(accounts[:2])
        remaining = len(accounts) - 2
        if remaining > 0:
            preview = f"{preview} + {remaining} til"
        return f"{len(accounts)} kontoer ({preview})"

    def _drag_target_summary(self, code: object) -> str:
        code_s = str(code or "").strip()
        if not code_s:
            return ""
        try:
            work_level_getter = getattr(self, "_selected_control_work_level", None)
            work_level = work_level_getter() if callable(work_level_getter) else "a07"
        except Exception:
            work_level = "a07"

        label = ""
        if str(work_level or "").strip() == "rf1022":
            overview_df = getattr(self, "rf1022_overview_df", None)
            try:
                matches = overview_df.loc[overview_df["GroupId"].astype(str).str.strip() == code_s]
            except Exception:
                matches = None
            if matches is not None and not matches.empty:
                row = matches.iloc[0]
                label = str(row.get("Kontrollgruppe") or row.get("Post") or "").strip()
        else:
            control_df = getattr(self, "control_df", None)
            try:
                matches = control_df.loc[control_df["Kode"].astype(str).str.strip() == code_s]
            except Exception:
                matches = None
            if matches is not None and not matches.empty:
                row = matches.iloc[0]
                label = str(row.get("A07Post") or row.get("Navn") or "").strip()

        if label and label.casefold() != code_s.casefold():
            return f"{code_s} ({label})"
        return code_s

    def _drag_feedback_message(self, *, target_code: object | None = None) -> tuple[str, str]:
        source = self._drag_source_summary()
        if not source:
            return _CONTROL_DRAG_IDLE_HINT, "Muted.TLabel"
        if target_code:
            target = self._drag_target_summary(target_code) or str(target_code or "").strip()
            return f"Slipp naa: {source} -> {target}.", "Ready.TLabel"
        target_kind = self._drag_target_kind_label().lower()
        return (
            f"Dra {source} til ønsket {target_kind} til høyre. Slipp naar raden blir markert.",
            "Warning.TLabel",
        )

    def _set_control_drag_feedback(self, message: object, *, style: str) -> None:
        text = str(message or "").strip() or _CONTROL_DRAG_IDLE_HINT
        self.control_drag_var.set(text)
        try:
            self.lbl_control_drag.configure(style=style)
        except Exception:
            pass

    def _restore_control_drag_hint(self) -> None:
        message, style = self._drag_feedback_message()
        self._set_control_drag_feedback(message, style=style)

    def _ensure_control_drag_ghost(self) -> None:
        if getattr(self, "_control_drag_ghost", None) is not None:
            return
        anchor = getattr(self, "tree_a07", None) or getattr(self, "tree_control_gl", None) or self
        try:
            ghost = tk.Toplevel(anchor)
            ghost.wm_overrideredirect(True)
            ghost.wm_attributes("-topmost", True)
            outer = tk.Frame(ghost, background=_DRAG_GHOST_ACTIVE_BG, bd=0)
            outer.pack()
            card = tk.Frame(outer, background=_DRAG_GHOST_TEXT, bd=0)
            card.pack(padx=1, pady=1)
            summary = tk.Label(
                card,
                text="",
                background=_DRAG_GHOST_TEXT,
                foreground="#0F172A",
                font=("Segoe UI", 9, "bold"),
                padx=10,
                pady=(6, 1),
                justify="left",
                anchor="w",
            )
            detail = tk.Label(
                card,
                text="",
                background=_DRAG_GHOST_TEXT,
                foreground="#475569",
                font=("Segoe UI", 9),
                padx=10,
                pady=(0, 6),
                justify="left",
                anchor="w",
            )
            summary.pack(fill="x")
            detail.pack(fill="x")
            ghost.wm_geometry("+-2000+-2000")
            self._control_drag_ghost = ghost
            self._control_drag_ghost_frame = outer
            self._control_drag_ghost_summary = summary
            self._control_drag_ghost_detail = detail
        except Exception:
            self._control_drag_ghost = None
            self._control_drag_ghost_frame = None
            self._control_drag_ghost_summary = None
            self._control_drag_ghost_detail = None

    def _teardown_control_drag_visuals(self) -> None:
        ghost = getattr(self, "_control_drag_ghost", None)
        if ghost is not None:
            try:
                ghost.destroy()
            except Exception:
                pass
        self._control_drag_ghost = None
        self._control_drag_ghost_frame = None
        self._control_drag_ghost_summary = None
        self._control_drag_ghost_detail = None
        for tree_name in ("tree_a07", "tree_control_gl", "tree_unmapped"):
            tree = getattr(self, tree_name, None)
            if tree is None:
                continue
            try:
                tree.configure(cursor="")
            except Exception:
                pass

    def _update_control_drag_visuals(
        self,
        event: tk.Event | None = None,
        *,
        target_code: object | None = None,
        valid: bool = False,
    ) -> None:
        if not self._current_drag_accounts():
            self._teardown_control_drag_visuals()
            return
        self._ensure_control_drag_ghost()
        ghost = getattr(self, "_control_drag_ghost", None)
        frame = getattr(self, "_control_drag_ghost_frame", None)
        summary = getattr(self, "_control_drag_ghost_summary", None)
        detail = getattr(self, "_control_drag_ghost_detail", None)
        source = self._drag_source_summary()
        target_kind = self._drag_target_kind_label()
        if target_code and valid:
            target = self._drag_target_summary(target_code) or str(target_code or "").strip()
            summary_text = f"Slipp paa {target}"
            detail_text = f"Mapper {source} nar du slipper museknappen."
            border = _DRAG_GHOST_READY_BG
            cursor = "hand2"
        else:
            summary_text = f"Dra {source}"
            detail_text = f"Flytt over ønsket {target_kind.lower()} til høyre."
            border = _DRAG_GHOST_ACTIVE_BG
            cursor = "fleur"

        if summary is not None:
            try:
                summary.configure(text=summary_text)
            except Exception:
                pass
        if detail is not None:
            try:
                detail.configure(text=detail_text)
            except Exception:
                pass
        if frame is not None:
            try:
                frame.configure(background=border)
            except Exception:
                pass
        for tree_name in ("tree_a07", "tree_control_gl", "tree_unmapped"):
            tree = getattr(self, tree_name, None)
            if tree is None:
                continue
            try:
                tree.configure(cursor=cursor)
            except Exception:
                pass
        if ghost is not None and event is not None:
            try:
                x_root = int(getattr(event, "x_root", 0) or 0)
                y_root = int(getattr(event, "y_root", 0) or 0)
                ghost.wm_geometry(f"+{x_root + 16}+{y_root + 8}")
            except Exception:
                pass

    def _start_unmapped_drag(self, event: tk.Event | None = None) -> None:
        account = self._tree_iid_from_event(self.tree_unmapped, event)
        self._drag_unmapped_account = account
        self._drag_control_accounts = []
        self._restore_control_drag_hint()
        self._update_control_drag_visuals(event, valid=False)

    def _start_control_gl_drag(self, event: tk.Event | None = None) -> None:
        accounts = self._selected_control_gl_accounts()
        if not accounts:
            account = self._tree_iid_from_event(self.tree_control_gl, event)
            if account:
                self._set_tree_selection(self.tree_control_gl, account)
                accounts = [account]
        self._drag_control_accounts = [str(account).strip() for account in accounts if str(account).strip()]
        self._drag_unmapped_account = None
        self._restore_control_drag_hint()
        self._update_control_drag_visuals(event, valid=False)

    def _current_drag_accounts(self) -> list[str]:
        if self._drag_control_accounts:
            return [str(account).strip() for account in self._drag_control_accounts if str(account).strip()]
        account = str(self._drag_unmapped_account or "").strip()
        return [account] if account else []

    def _clear_control_drag_state(self) -> None:
        self._drag_unmapped_account = None
        self._drag_control_accounts = []
        clear_drop_target = getattr(self, "_clear_control_drop_target", None)
        if callable(clear_drop_target):
            clear_drop_target()
        self._teardown_control_drag_visuals()
        self._restore_control_drag_hint()

    def _set_control_drop_target(self, iid: str | None) -> None:
        tree = getattr(self, "tree_a07", None)
        if tree is None:
            self._control_drop_target_iid = None
            return
        try:
            children = set(str(value).strip() for value in tree.get_children())
        except Exception:
            children = set()

        previous_iid = str(getattr(self, "_control_drop_target_iid", "") or "").strip()
        if previous_iid and previous_iid in children:
            try:
                current_tags = tuple(str(tag).strip() for tag in (tree.item(previous_iid, "tags") or ()))
                tree.item(previous_iid, tags=tuple(tag for tag in current_tags if tag and tag != "drop_target"))
            except Exception:
                pass

        target_iid = str(iid or "").strip()
        if not target_iid or target_iid not in children:
            self._control_drop_target_iid = None
            return

        try:
            current_tags = tuple(str(tag).strip() for tag in (tree.item(target_iid, "tags") or ()))
        except Exception:
            current_tags = ()
        normalized_tags = tuple(tag for tag in current_tags if tag and tag != "drop_target")
        try:
            tree.item(target_iid, tags=normalized_tags + ("drop_target",))
        except Exception:
            pass
        self._control_drop_target_iid = target_iid

    def _clear_control_drop_target(self) -> None:
        self._set_control_drop_target(None)

    def _on_control_drop_zone_leave(self) -> None:
        if not self._current_drag_accounts():
            return
        self._clear_control_drop_target()
        self._restore_control_drag_hint()
        self._update_control_drag_visuals(valid=False)

    def _track_unmapped_drop_target(self, event: tk.Event | None = None) -> None:
        try:
            accounts = self._current_drag_accounts()
        except Exception:
            account = str(getattr(self, "_drag_unmapped_account", "") or "").strip()
            accounts = [account] if account else []
        if not accounts:
            clear_drop_target = getattr(self, "_clear_control_drop_target", None)
            if callable(clear_drop_target):
                clear_drop_target()
            self._teardown_control_drag_visuals()
            return
        code = self._tree_iid_from_event(self.tree_a07, event)
        if not code:
            clear_drop_target = getattr(self, "_clear_control_drop_target", None)
            if callable(clear_drop_target):
                clear_drop_target()
            self._restore_control_drag_hint()
            self._update_control_drag_visuals(event, valid=False)
            return
        selector = getattr(self, "_set_tree_selection", None)
        if callable(selector):
            try:
                selector(self.tree_a07, code, reveal=False, focus=False)
            except TypeError:
                selector(self.tree_a07, code)
        else:
            try:
                self.tree_a07.selection_set(code)
                self.tree_a07.focus(code)
                self.tree_a07.see(code)
            except Exception:
                pass
        set_drop_target = getattr(self, "_set_control_drop_target", None)
        if callable(set_drop_target):
            set_drop_target(code)
        message, style = self._drag_feedback_message(target_code=code)
        self._set_control_drag_feedback(message, style=style)
        self._update_control_drag_visuals(event, target_code=code, valid=True)


__all__ = ["A07PageDragDropHelpersMixin"]
