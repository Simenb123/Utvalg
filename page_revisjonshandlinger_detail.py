"""Detalj-popup for en enkelt revisjonshandling.

Viser handling-info, koblet arbeidspapir, produserte filer (med PDF-preview),
og en kommentar-boks som lagres per handling/klient/år.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore

import action_artifact_store
from action_artifact_store import Artifact


class _PdfPreview(ttk.Frame):  # type: ignore[misc]
    """Enkel PDF-visning med side-navigasjon. Bruker PyMuPDF (fitz)."""

    def __init__(self, master: Any) -> None:
        super().__init__(master)
        self._doc = None
        self._page_idx = 0
        self._photo = None  # hold referanse — ellers samles bildet
        self._path: Path | None = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew")
        bar.columnconfigure(3, weight=1)
        self._btn_prev = ttk.Button(bar, text="◀", width=3, command=self._on_prev, state="disabled")
        self._btn_prev.grid(row=0, column=0)
        self._btn_next = ttk.Button(bar, text="▶", width=3, command=self._on_next, state="disabled")
        self._btn_next.grid(row=0, column=1, padx=(2, 6))
        self._info_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self._info_var, style="Muted.TLabel").grid(row=0, column=2, sticky="w")

        canvas_wrap = ttk.Frame(self, relief="sunken", borderwidth=1)
        canvas_wrap.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        canvas_wrap.columnconfigure(0, weight=1)
        canvas_wrap.rowconfigure(0, weight=1)
        self._canvas = tk.Canvas(canvas_wrap, background="#f4f4f4", highlightthickness=0)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(canvas_wrap, orient="vertical", command=self._canvas.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        self._canvas.configure(yscrollcommand=yscroll.set)
        self._canvas.bind("<Configure>", lambda _e: self._render())

    # ------------------------------------------------------------------

    def load(self, path: Path) -> bool:
        self.close()
        try:
            import fitz  # PyMuPDF
        except Exception:
            self._info_var.set("PDF-visning krever PyMuPDF (fitz). Bruk «Åpne fil» i stedet.")
            return False
        try:
            self._doc = fitz.open(str(path))
        except Exception as exc:
            self._info_var.set(f"Kunne ikke åpne PDF: {exc}")
            return False
        self._path = path
        self._page_idx = 0
        self._update_buttons()
        self.after(0, self._render)
        return True

    def close(self) -> None:
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:
                pass
        self._doc = None
        self._photo = None
        self._canvas.delete("all")
        self._info_var.set("")
        self._btn_prev.configure(state="disabled")
        self._btn_next.configure(state="disabled")

    def _update_buttons(self) -> None:
        if self._doc is None:
            self._btn_prev.configure(state="disabled")
            self._btn_next.configure(state="disabled")
            return
        n = self._doc.page_count
        self._btn_prev.configure(state=("normal" if self._page_idx > 0 else "disabled"))
        self._btn_next.configure(state=("normal" if self._page_idx < n - 1 else "disabled"))
        self._info_var.set(f"Side {self._page_idx + 1} av {n}")

    def _on_prev(self) -> None:
        if self._doc is None or self._page_idx <= 0:
            return
        self._page_idx -= 1
        self._update_buttons()
        self._render()

    def _on_next(self) -> None:
        if self._doc is None or self._page_idx >= self._doc.page_count - 1:
            return
        self._page_idx += 1
        self._update_buttons()
        self._render()

    def _render(self) -> None:
        if self._doc is None:
            return
        try:
            import fitz  # noqa: F401
            from PIL import Image, ImageTk
        except Exception:
            return
        page = self._doc.load_page(self._page_idx)
        rect = page.rect
        canvas_w = max(self._canvas.winfo_width(), 200)
        zoom = max(0.5, min(3.0, canvas_w / max(rect.width, 1)))
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        mode = "RGB" if pix.alpha == 0 else "RGBA"
        img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
        self._photo = ImageTk.PhotoImage(img)
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, image=self._photo, anchor="nw")
        self._canvas.configure(scrollregion=(0, 0, pix.width, pix.height))


class ActionDetailDialog(tk.Toplevel):  # type: ignore[misc]
    """Popup med handling-info, filer, PDF-preview og kommentar-boks."""

    def __init__(
        self,
        master: Any,
        *,
        client: str,
        year: str,
        action_key: str,
        header_lines: list[str],
        description: str,
        workpaper_ids: list[str],
        workpaper_index: dict[str, Any],
        on_run: Callable[[], None] | None = None,
        user_name: str = "",
    ) -> None:
        super().__init__(master)
        title_name = header_lines[0] if header_lines else "detaljer"
        self.title(f"Handling — {title_name}")
        # Bevisst ingen transient() — beholder min/max-knappene i tittellinjen.
        self.resizable(True, True)
        self.geometry("1000x720")
        self.minsize(720, 520)

        self._client = client
        self._year = year
        self._action_key = action_key
        self._on_run = on_run
        self._user_name = user_name
        self._current_artifact: Artifact | None = None
        self._artifacts: list[Artifact] = []
        self._comment_save_after: str | None = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_header(header_lines, description, workpaper_ids, workpaper_index)
        self._build_body()
        self._build_footer()
        self._reload()

        self.bind("<Escape>", lambda _e: self._on_close())
        self.bind("<Control-s>", lambda _e: (self._persist_comment(), "break"))
        self.bind("<Control-S>", lambda _e: (self._persist_comment(), "break"))
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(0, self._center_on_parent)
        self.after(10, lambda: self._comment_txt.focus_set())

    def _center_on_parent(self) -> None:
        try:
            self.update_idletasks()
            parent = self.master.winfo_toplevel() if self.master else None
            if parent is None or not parent.winfo_viewable():
                return
            pw, ph = parent.winfo_width(), parent.winfo_height()
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            w, h = self.winfo_width(), self.winfo_height()
            x = max(0, px + (pw - w) // 2)
            y = max(0, py + (ph - h) // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    # ------------------------------------------------------------------

    def _build_header(
        self,
        header_lines: list[str],
        description: str,
        workpaper_ids: list[str],
        workpaper_index: dict[str, Any],
    ) -> None:
        hdr = ttk.Frame(self, padding=(12, 10, 12, 6))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(0, weight=1)

        for i, line in enumerate(header_lines):
            style = "TLabel" if i == 0 else "Muted.TLabel"
            font = ("TkDefaultFont", 11, "bold") if i == 0 else None
            lbl = ttk.Label(hdr, text=line, style=style)
            if font:
                lbl.configure(font=font)
            lbl.grid(row=i, column=0, sticky="w")

        wp_names: list[str] = []
        for wid in workpaper_ids:
            wp = workpaper_index.get(wid)
            wp_names.append(wp.navn if wp else f"[mangler {wid[:8]}…]")
        if wp_names:
            ttk.Label(
                hdr,
                text="Koblet arbeidspapir: " + ", ".join(wp_names),
                style="Muted.TLabel",
            ).grid(row=len(header_lines), column=0, sticky="w", pady=(4, 0))

        if description:
            box = ttk.Frame(hdr)
            box.grid(row=len(header_lines) + 1, column=0, sticky="ew", pady=(6, 0))
            box.columnconfigure(0, weight=1)
            txt = tk.Text(box, height=min(6, max(2, description.count("\n") + 2)),
                          wrap="word", background="#fafafa", relief="flat")
            txt.insert("1.0", description)
            txt.configure(state="disabled")
            txt.grid(row=0, column=0, sticky="ew")

    def _build_body(self) -> None:
        body = ttk.Frame(self, padding=(12, 4, 12, 4))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=3)
        body.rowconfigure(1, weight=2)

        # --- Venstre: fil-liste ---
        files_frame = ttk.LabelFrame(body, text="Filer", padding=6)
        files_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        files_frame.columnconfigure(0, weight=1)
        files_frame.rowconfigure(0, weight=1)

        cols = ("navn", "dato", "str")
        self._tree = ttk.Treeview(files_frame, columns=cols, show="headings", selectmode="browse")
        self._tree.heading("navn", text="Arbeidspapir / fil")
        self._tree.heading("dato", text="Kjørt")
        self._tree.heading("str", text="Str")
        self._tree.column("navn", width=260, minwidth=160)
        self._tree.column("dato", width=130, minwidth=90, anchor="center")
        self._tree.column("str", width=70, minwidth=50, anchor="e")
        yscroll = ttk.Scrollbar(files_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=yscroll.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        self._tree.bind("<<TreeviewSelect>>", self._on_file_select)
        self._tree.bind("<Double-1>", lambda _e: self._on_open_file())

        file_btns = ttk.Frame(files_frame)
        file_btns.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._btn_open = ttk.Button(file_btns, text="Åpne fil", command=self._on_open_file, state="disabled")
        self._btn_open.pack(side="left")
        self._btn_reveal = ttk.Button(file_btns, text="Vis i mappe", command=self._on_reveal_file, state="disabled")
        self._btn_reveal.pack(side="left", padx=(6, 0))
        self._btn_remove = ttk.Button(file_btns, text="Fjern fra oversikt", command=self._on_remove_from_index, state="disabled")
        self._btn_remove.pack(side="left", padx=(6, 0))

        # --- Høyre: preview ---
        preview_frame = ttk.LabelFrame(body, text="Forhåndsvisning", padding=6)
        preview_frame.grid(row=0, column=1, sticky="nsew")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        self._preview = _PdfPreview(preview_frame)
        self._preview.grid(row=0, column=0, sticky="nsew")
        self._preview_placeholder_var = tk.StringVar(
            value="Velg en PDF-fil i listen for å forhåndsvise."
        )
        self._preview_placeholder = ttk.Label(
            preview_frame, textvariable=self._preview_placeholder_var,
            style="Muted.TLabel", anchor="center",
        )
        self._preview_placeholder.grid(row=0, column=0, sticky="nsew")
        self._preview.grid_remove()

        # --- Nede: kommentar ---
        comment_frame = ttk.LabelFrame(body, text="Kommentar (lagres automatisk)", padding=6)
        comment_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        comment_frame.columnconfigure(0, weight=1)
        comment_frame.rowconfigure(0, weight=1)
        self._comment_txt = tk.Text(comment_frame, height=6, wrap="word")
        self._comment_txt.grid(row=0, column=0, sticky="nsew")
        cscroll = ttk.Scrollbar(comment_frame, orient="vertical", command=self._comment_txt.yview)
        self._comment_txt.configure(yscrollcommand=cscroll.set)
        cscroll.grid(row=0, column=1, sticky="ns")
        self._comment_status_var = tk.StringVar(value="")
        ttk.Label(comment_frame, textvariable=self._comment_status_var, style="Muted.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        self._comment_txt.bind("<<Modified>>", self._on_comment_modified)

    def _build_footer(self) -> None:
        ftr = ttk.Frame(self, padding=(12, 6, 12, 10))
        ftr.grid(row=2, column=0, sticky="ew")
        ftr.columnconfigure(0, weight=1)
        if self._on_run is not None:
            ttk.Button(ftr, text="Kjør arbeidspapir…", command=self._run_and_reload).grid(
                row=0, column=0, sticky="w"
            )
        ttk.Button(ftr, text="Lukk", command=self._on_close).grid(row=0, column=1, sticky="e")

    # ------------------------------------------------------------------
    # Data

    def _reload(self) -> None:
        if self._client and self._year:
            try:
                self._artifacts = [
                    a for a in action_artifact_store.prune_missing(self._client, self._year)
                    if a.action_key == self._action_key
                ]
            except Exception:
                self._artifacts = []
            comment = action_artifact_store.get_comment(self._client, self._year, self._action_key)
            self._comment_txt.delete("1.0", "end")
            if comment.text:
                self._comment_txt.insert("1.0", comment.text)
            self._comment_txt.edit_modified(False)
            if comment.updated_at:
                self._comment_status_var.set(f"Sist lagret: {comment.updated_at}")
            else:
                self._comment_status_var.set(" ")  # tom — unødvendig støy ved ingen kommentar
        else:
            self._artifacts = []
            self._comment_txt.configure(state="disabled")
            self._comment_status_var.set("Ingen klient/år valgt — kommentar kan ikke lagres.")
        self._refresh_file_tree()

    def _refresh_file_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())
        ordered = sorted(self._artifacts, key=lambda x: x.kjort_at, reverse=True)
        if not ordered:
            self._tree.insert(
                "", "end", iid="__empty__",
                values=("Ingen filer produsert ennå — bruk «Kjør arbeidspapir…»", "", ""),
                tags=("empty",),
            )
            try:
                self._tree.tag_configure("empty", foreground="#888888")
            except Exception:
                pass
        else:
            for i, a in enumerate(ordered):
                label = f"{a.workpaper_navn}  —  {a.filename}" if a.workpaper_navn else a.filename
                self._tree.insert(
                    "", "end", iid=str(i),
                    values=(label, a.kjort_at[:19].replace("T", " "), _format_size(a.size)),
                )
        self._current_artifact = None
        self._update_file_buttons()
        self._show_placeholder(
            "Velg en fil for å forhåndsvise." if ordered else "Ingen filer ennå."
        )

    def _show_placeholder(self, text: str) -> None:
        self._preview.close()
        self._preview.grid_remove()
        self._preview_placeholder_var.set(text)
        self._preview_placeholder.grid()

    def _on_file_select(self, _evt: Any = None) -> None:
        sel = self._tree.selection()
        if not sel or sel[0] == "__empty__":
            self._current_artifact = None
            self._update_file_buttons()
            self._show_placeholder("Velg en fil for å forhåndsvise.")
            return
        try:
            idx = int(sel[0])
        except ValueError:
            return
        ordered = sorted(self._artifacts, key=lambda x: x.kjort_at, reverse=True)
        if idx < 0 or idx >= len(ordered):
            return
        self._current_artifact = ordered[idx]
        self._update_file_buttons()
        path = Path(self._current_artifact.file_path)
        if not path.exists():
            self._show_placeholder("Filen er ikke lenger tilgjengelig på disk.")
            return
        if path.suffix.lower() == ".pdf":
            self._preview_placeholder.grid_remove()
            self._preview.grid()
            ok = self._preview.load(path)
            if not ok:
                self._show_placeholder("Kunne ikke forhåndsvise PDF. Bruk «Åpne fil».")
        else:
            self._show_placeholder(f"{path.suffix.lstrip('.').upper() or 'Fil'} — bruk «Åpne fil» for å vise.")

    def _update_file_buttons(self) -> None:
        state = "normal" if self._current_artifact is not None else "disabled"
        for btn in (self._btn_open, self._btn_reveal, self._btn_remove):
            btn.configure(state=state)

    def _on_open_file(self) -> None:
        if self._current_artifact is None:
            return
        path = Path(self._current_artifact.file_path)
        if not path.exists():
            messagebox.showwarning("Fil mangler", "Filen finnes ikke lenger.", parent=self)
            return
        _open_with_default_app(path)

    def _on_reveal_file(self) -> None:
        if self._current_artifact is None:
            return
        path = Path(self._current_artifact.file_path)
        if not path.exists():
            messagebox.showwarning("Fil mangler", "Filen finnes ikke lenger.", parent=self)
            return
        _reveal_in_folder(path)

    def _on_remove_from_index(self) -> None:
        if self._current_artifact is None:
            return
        if not messagebox.askyesno(
            "Fjern fra oversikt",
            "Fjerne denne filen fra handlingens oversikt? Selve filen slettes ikke.",
            parent=self,
        ):
            return
        remaining = [
            a for a in action_artifact_store.load_artifacts(self._client, self._year)
            if not (
                a.action_key == self._current_artifact.action_key
                and a.file_path == self._current_artifact.file_path
            )
        ]
        action_artifact_store.save_artifacts(self._client, self._year, remaining)
        self._reload()

    def _run_and_reload(self) -> None:
        if self._on_run is None:
            return
        try:
            self._on_run()
        finally:
            self._reload()

    # ------------------------------------------------------------------
    # Kommentar auto-save

    def _on_comment_modified(self, _evt: Any = None) -> None:
        if not self._comment_txt.edit_modified():
            return
        self._comment_txt.edit_modified(False)
        if self._comment_save_after is not None:
            try:
                self.after_cancel(self._comment_save_after)
            except Exception:
                pass
        self._comment_save_after = self.after(600, self._persist_comment)

    def _persist_comment(self) -> None:
        self._comment_save_after = None
        if not (self._client and self._year):
            return
        text = self._comment_txt.get("1.0", "end").rstrip()
        saved = action_artifact_store.save_comment(
            self._client, self._year, self._action_key, text,
            updated_by=self._user_name,
        )
        if saved.updated_at:
            self._comment_status_var.set(f"Lagret {saved.updated_at}")
        else:
            self._comment_status_var.set("Tom — ingen kommentar lagret.")

    def _on_close(self) -> None:
        if self._comment_save_after is not None:
            try:
                self.after_cancel(self._comment_save_after)
            except Exception:
                pass
            self._persist_comment()
        self._preview.close()
        self.destroy()


# ---------------------------------------------------------------------------
# Hjelpere


def _format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _open_with_default_app(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as exc:  # pragma: no cover
        messagebox.showerror("Kunne ikke åpne fil", str(exc))


def _reveal_in_folder(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
    except Exception as exc:  # pragma: no cover
        messagebox.showerror("Kunne ikke åpne mappe", str(exc))
