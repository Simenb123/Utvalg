"""page_fagchat.py — Faglig AI-assistent (RAG-basert, kun fagdatabase)

Fanen er bygget som en chat-side med:
  - Spørsmålsfelt + Send-knapp (Enter sender)
  - Scrollbar chat-logg (bruker/assistent-meldinger)
  - Kildereferanser etter hvert svar
  - Ekspanderbar kontekst-panel (for transparens)
  - Bakgrunnsthread slik at GUI ikke fryser under retrieval/LLM-kall
  - Konfigurasjonspanel (top-k, bruk LLM av/på)

Klientdata er ALDRI tilgjengelig her — kun spørsmål sendes til modellen
sammen med utvalgte tekstchunks fra fagdatabasen.

Avhengigheter (i openai-repoet):
  pip install chromadb openai python-dotenv PyPDF2
"""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional


# ---------------------------------------------------------------------------
# Finn openai-repoet og legg det til sys.path

def _find_openai_repo() -> Optional[Path]:
    """Søker etter openai-repoet relativt til denne filen."""
    here = Path(__file__).parent.resolve()
    # Prøv kjente plasseringer: sibling-mappe, eller en nivå opp
    candidates = [
        here.parent / "openai",
        here.parent.parent / "openai",
        here / "rag_engine",  # fallback hvis kopiert inn
    ]
    for c in candidates:
        if (c / "src" / "rag_assistant").is_dir():
            return c
    return None


_RAG_REPO = _find_openai_repo()
_RAG_AVAILABLE = False

if _RAG_REPO is not None:
    src_path = str(_RAG_REPO / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    try:
        from rag_assistant.qa_service import QueryOutcome, run_query  # type: ignore
        from rag_assistant.env_loader import load_env  # type: ignore
        _RAG_AVAILABLE = True
        _LIBRARY_PATH = _RAG_REPO / "kildebibliotek.json"
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Farger og konstanter

_COLOR_USER_BG   = "#dbeafe"   # blå boble
_COLOR_USER_FG   = "#1e3a5f"
_COLOR_BOT_BG    = "#f0fdf4"   # grønn boble
_COLOR_BOT_FG    = "#14532d"
_COLOR_SRC_BG    = "#fefce8"   # gul kilde-rad
_COLOR_SRC_FG    = "#713f12"
_COLOR_ERR_BG    = "#fef2f2"
_COLOR_ERR_FG    = "#991b1b"
_COLOR_THINKING  = "#6b7280"   # grå – "tenker…"

_TAG_USER     = "user"
_TAG_BOT      = "bot"
_TAG_SOURCE   = "source"
_TAG_ERROR    = "error"
_TAG_THINKING = "thinking"
_TAG_HEADING  = "heading"


# ---------------------------------------------------------------------------

class FagchatPage(ttk.Frame):
    """Faglig AI-assistent-fane — ingen klientdata sendes til modellen."""

    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent)
        self._queue: queue.Queue = queue.Queue()
        self._busy = False
        self._ctx_visible = tk.BooleanVar(value=False)
        self._use_llm = tk.BooleanVar(value=True)
        self._top_k = tk.IntVar(value=5)
        self._last_context: str = ""

        self._build_ui()
        self._poll_queue()

        if not _RAG_AVAILABLE:
            self._show_setup_warning()

    # ------------------------------------------------------------------
    # UI-bygg

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_toolbar(row=0)
        self._build_chat_area(row=1)
        self._build_input_area(row=2)
        self._build_status_bar(row=3)

    def _build_toolbar(self, *, row: int) -> None:
        bar = ttk.Frame(self, padding=(8, 4))
        bar.grid(row=row, column=0, sticky="ew")

        ttk.Label(bar, text="Faglig AI-assistent", font=("", 11, "bold")).pack(side=tk.LEFT)

        # Høyre side: innstillinger
        right = ttk.Frame(bar)
        right.pack(side=tk.RIGHT)

        ttk.Label(right, text="Top-k:").pack(side=tk.LEFT, padx=(0, 2))
        ttk.Spinbox(right, from_=3, to=15, textvariable=self._top_k,
                    width=4).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Checkbutton(right, text="LLM-svar", variable=self._use_llm).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(right, text="Vis kontekst", variable=self._ctx_visible,
                        command=self._toggle_context).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(right, text="Tøm", command=self._clear_chat,
                   width=6).pack(side=tk.LEFT)

    def _build_chat_area(self, *, row: int) -> None:
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.grid(row=row, column=0, sticky="nsew", padx=4, pady=2)
        self._paned = paned

        # Venstre: chat-logg
        chat_frame = ttk.Frame(paned)
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)
        paned.add(chat_frame, weight=3)

        self._chat = tk.Text(
            chat_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            cursor="arrow",
            spacing1=4,
            spacing3=4,
            padx=10,
            pady=8,
            font=("", 10),
        )
        sb = ttk.Scrollbar(chat_frame, orient=tk.VERTICAL, command=self._chat.yview)
        self._chat.configure(yscrollcommand=sb.set)
        self._chat.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        # Tekst-tags
        self._chat.tag_configure(_TAG_USER,
            background=_COLOR_USER_BG, foreground=_COLOR_USER_FG,
            lmargin1=60, lmargin2=60, rmargin=10,
            spacing1=6, spacing3=6, relief=tk.FLAT)
        self._chat.tag_configure(_TAG_BOT,
            background=_COLOR_BOT_BG, foreground=_COLOR_BOT_FG,
            lmargin1=10, lmargin2=20, rmargin=60,
            spacing1=6, spacing3=6)
        self._chat.tag_configure(_TAG_SOURCE,
            background=_COLOR_SRC_BG, foreground=_COLOR_SRC_FG,
            lmargin1=20, lmargin2=30, font=("", 9))
        self._chat.tag_configure(_TAG_ERROR,
            background=_COLOR_ERR_BG, foreground=_COLOR_ERR_FG,
            lmargin1=10, lmargin2=20)
        self._chat.tag_configure(_TAG_THINKING,
            foreground=_COLOR_THINKING, font=("", 10, "italic"),
            lmargin1=10)
        self._chat.tag_configure(_TAG_HEADING,
            font=("", 9, "bold"), foreground=_COLOR_SRC_FG,
            lmargin1=20)

        # Høyre: kontekst-panel (skjult som standard)
        self._ctx_frame = ttk.LabelFrame(paned, text="Hentet kontekst (råtekst)")
        self._ctx_text = tk.Text(
            self._ctx_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("", 9), padx=6, pady=4,
        )
        ctx_sb = ttk.Scrollbar(self._ctx_frame, orient=tk.VERTICAL, command=self._ctx_text.yview)
        self._ctx_text.configure(yscrollcommand=ctx_sb.set)
        self._ctx_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ctx_sb.pack(side=tk.RIGHT, fill=tk.Y)
        # Ikke lagt til paned ennå — legges til av _toggle_context

    def _build_input_area(self, *, row: int) -> None:
        frame = ttk.Frame(self, padding=(8, 4))
        frame.grid(row=row, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)

        self._input = ttk.Entry(frame, font=("", 11))
        self._input.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._input.bind("<Return>", lambda _e: self._send())
        self._input.bind("<KP_Enter>", lambda _e: self._send())

        self._send_btn = ttk.Button(frame, text="Send", command=self._send, width=8)
        self._send_btn.grid(row=0, column=1)

        ttk.Label(frame,
                  text="Spørsmål sendes med relevante fagutdrag fra kildebiblioteket — ingen klientdata.",
                  foreground="#6b7280", font=("", 8)).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

    def _build_status_bar(self, *, row: int) -> None:
        self._status_var = tk.StringVar(value="Klar")
        bar = ttk.Frame(self, relief=tk.SUNKEN)
        bar.grid(row=row, column=0, sticky="ew", padx=0, pady=0)
        ttk.Label(bar, textvariable=self._status_var,
                  font=("", 9), padding=(6, 2)).pack(side=tk.LEFT)

    # ------------------------------------------------------------------
    # Chat-logg helpers

    def _append(self, text: str, tag: str) -> None:
        self._chat.configure(state=tk.NORMAL)
        self._chat.insert(tk.END, text + "\n", tag)
        self._chat.configure(state=tk.DISABLED)
        self._chat.see(tk.END)

    def _remove_thinking(self) -> None:
        """Fjern siste 'tenker…'-linje."""
        self._chat.configure(state=tk.NORMAL)
        ranges = self._chat.tag_ranges(_TAG_THINKING)
        if ranges:
            # Fjern siste forekomst
            last_start = ranges[-2]
            last_end = ranges[-1]
            self._chat.delete(last_start, last_end)
        self._chat.configure(state=tk.DISABLED)

    def _clear_chat(self) -> None:
        self._chat.configure(state=tk.NORMAL)
        self._chat.delete("1.0", tk.END)
        self._chat.configure(state=tk.DISABLED)
        self._last_context = ""
        self._update_context_panel("")
        self._status_var.set("Klar")

    def _toggle_context(self) -> None:
        if self._ctx_visible.get():
            self._paned.add(self._ctx_frame, weight=1)
            self._update_context_panel(self._last_context)
        else:
            try:
                self._paned.forget(self._ctx_frame)
            except Exception:
                pass

    def _update_context_panel(self, text: str) -> None:
        self._ctx_text.configure(state=tk.NORMAL)
        self._ctx_text.delete("1.0", tk.END)
        if text:
            self._ctx_text.insert(tk.END, text)
        self._ctx_text.configure(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # Send / query

    def _send(self) -> None:
        if self._busy:
            return
        q = self._input.get().strip()
        if not q:
            return
        if not _RAG_AVAILABLE:
            self._show_setup_warning()
            return

        self._input.delete(0, tk.END)
        self._append(f"Du:  {q}", _TAG_USER)
        self._append("Henter faglig kontekst…", _TAG_THINKING)
        self._set_busy(True)
        self._status_var.set("Søker i fagdatabasen…")

        use_llm = self._use_llm.get()
        top_k = max(1, int(self._top_k.get() or 5))

        def _worker() -> None:
            try:
                load_env(_RAG_REPO / ".env")
                if use_llm:
                    import os
                    if not os.environ.get("OPENAI_API_KEY"):
                        self._queue.put(("error",
                            "OPENAI_API_KEY mangler.\n"
                            "Opprett en .env-fil i openai-mappen med:\n"
                            "OPENAI_API_KEY=sk-..."))
                        return

                outcome: QueryOutcome = run_query(
                    q,
                    library_path=_LIBRARY_PATH,
                    n_results=top_k,
                    expand_relations=True,
                    use_llm=use_llm,
                )
                self._queue.put(("ok", outcome))
            except Exception as exc:
                self._queue.put(("error", str(exc)))

        threading.Thread(target=_worker, daemon=True).start()

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._queue.get_nowait()
                kind = msg[0]
                data = msg[1]
                self._remove_thinking()

                if kind == "ok":
                    outcome: QueryOutcome = data
                    answer = outcome.answer or None

                    if answer:
                        self._append(f"Assistent:\n{answer}", _TAG_BOT)
                    else:
                        # Context-only modus
                        self._append(
                            "Assistent: [Context-only — LLM deaktivert]\n"
                            "Se 'Vis kontekst' for hentet fagutdrag.",
                            _TAG_BOT,
                        )

                    if outcome.sources_text:
                        self._append("Kilder:", _TAG_HEADING)
                        for line in outcome.sources_text.splitlines():
                            if line.strip():
                                self._append(f"  {line.strip()}", _TAG_SOURCE)

                    self._last_context = outcome.context or ""
                    if self._ctx_visible.get():
                        self._update_context_panel(self._last_context)
                    self._status_var.set(
                        f"Ferdig — {len(outcome.chunks)} chunks hentet"
                        + (", LLM-svar generert" if answer else ", context-only")
                    )

                elif kind == "error":
                    self._append(f"Feil: {data}", _TAG_ERROR)
                    self._status_var.set("Feil — se feilmelding i chatten")

                self._set_busy(False)
        except queue.Empty:
            pass

        self.after(100, self._poll_queue)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self._send_btn.configure(state=state)
        self._input.configure(state=state)

    # ------------------------------------------------------------------
    # Setup-advarsel

    def _show_setup_warning(self) -> None:
        msg = (
            "RAG-motoren ikke funnet.\n\n"
            "Forventet mappe:\n"
            f"  {(_RAG_REPO or Path('../openai'))}\n\n"
            "Installer avhengigheter:\n"
            "  pip install chromadb openai python-dotenv PyPDF2\n\n"
            "Bygg indeks:\n"
            "  cd openai\n"
            "  python run_build_index.py --library kildebibliotek.json\n\n"
            "Legg til API-nøkkel i openai/.env:\n"
            "  OPENAI_API_KEY=sk-..."
        )
        self._append(msg, _TAG_ERROR)
        self._status_var.set("Mangler oppsett — se feilmelding")

    # ------------------------------------------------------------------
    # Offentlig API (brukes av ui_main ved session-last)

    def refresh_from_session(self, _session=None) -> None:
        """Ingen klientdata brukes her — ingenting å laste fra sesjon."""
        pass
