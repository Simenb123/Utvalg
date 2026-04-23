"""page_fagchat.py — Faglig AI-assistent (RAG-basert, kun fagdatabase)

Fanen er bygget som en todelt chat-side:
  - Venstre: spørsmål/svar-chat med klikkbare kildereferanser
  - Høyre:   kildevisningspanel som viser chunk-tekst når en kilde klikkes

Klientdata er ALDRI tilgjengelig her — kun spørsmål sendes til modellen
sammen med utvalgte tekstchunks fra fagdatabasen.

Avhengigheter (i openai-repoet):
  pip install chromadb openai python-dotenv PyPDF2
"""

from __future__ import annotations

import queue
import re
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional


# ---------------------------------------------------------------------------
# Finn openai-repoet og legg det til sys.path

def _find_openai_repo() -> Optional[Path]:
    """Søker etter openai-repoet relativt til denne filen.

    Prioriterer lokal kopi (ved siden av Utvalg-1) for enklere utvikling.
    Nettverkskopier (sources_dir, data_dir) brukes kun som fallback.
    """
    import app_paths
    here = Path(__file__).parent.resolve()
    data = app_paths.data_dir()
    sources = app_paths.sources_dir()
    candidates = [
        here.parent / "openai",
        here.parent.parent / "openai",
        here / "rag_engine",
    ]
    # Nettverksstier som fallback
    if sources is not None:
        candidates.append(sources / "openai")
        candidates.append(sources.parent / "openai")
    candidates.append(data.parent / "openai")
    candidates.append(data / "openai")
    candidates.append(data / "rag_engine")
    for c in candidates:
        if (c / "src" / "rag_assistant").is_dir():
            return c
    return None


_RAG_REPO = _find_openai_repo()
_LIBRARY_PATH: Optional[Path] = _RAG_REPO / "kildebibliotek.json" if _RAG_REPO else None

_RAG_AVAILABLE: Optional[bool] = None


def _ensure_rag() -> bool:
    global _RAG_AVAILABLE
    if _RAG_AVAILABLE is not None:
        return _RAG_AVAILABLE
    if _RAG_REPO is None:
        _RAG_AVAILABLE = False
        return False
    src_path = str(_RAG_REPO / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    try:
        import rag_assistant.qa_service  # noqa: F401
        _RAG_AVAILABLE = True
    except Exception:
        _RAG_AVAILABLE = False
    return bool(_RAG_AVAILABLE)


# ---------------------------------------------------------------------------
# Farger og konstanter

_COLOR_USER_BG   = "#E5F1EE"
_COLOR_USER_FG   = "#1A4D44"
_COLOR_BOT_BG    = "#FFFDF8"
_COLOR_BOT_FG    = "#1F2430"
_COLOR_SRC_BG    = "#F0EDE6"
_COLOR_SRC_FG    = "#4A4135"
_COLOR_ERR_BG    = "#FEF2F2"
_COLOR_ERR_FG    = "#991B1B"
_COLOR_THINKING  = "#9CA3AF"

_INLINE_RE = re.compile(
    r'\*\*\*(.+?)\*\*\*'    # ***bold italic***
    r'|\*\*(.+?)\*\*'       # **bold**
    r'|\*(.+?)\*',          # *italic*
    re.DOTALL,
)
# Kildehenvisninger i AI-tekst: (ISA-200 P5), (KRAV-ISA-500 P8), (KONT-XXX P4) etc.
_SOURCE_REF_RE = re.compile(
    r'\(([A-ZÆØÅ][A-ZÆØÅ0-9]*-[A-ZÆØÅ0-9-]+(?:\s+[PA]\d+(?:[.\-]\d+)*)?)\)'
)
_HEADING_RE = re.compile(r'^(#{2,4})\s+(.+)$')
_CHECKBOX_UNCHECKED_RE = re.compile(r'^[-*]\s*\[ \]\s+(.+)$')
_CHECKBOX_CHECKED_RE = re.compile(r'^[-*]\s*\[[xX]\]\s+(.+)$')
_BULLET_RE = re.compile(r'^[-*]\s+(.+)$')
_NUMBERED_RE = re.compile(r'^(\d+\.)\s+(.+)$')

_TAG_USER     = "user"
_TAG_BOT      = "bot"
_TAG_SOURCE   = "source"
_TAG_ERROR    = "error"
_TAG_THINKING = "thinking"
_TAG_HEADING  = "heading"

_PLACEHOLDER = "Klikk en kilde i chatten for å se innholdet her."

_DOC_TYPE_LABELS = {
    "ISA": "Revisjonsstandard",
    "KRAV": "MÅ-krav",
    "SJEKKLISTE": "Sjekkliste",
    "NRS": "Regnskapsstandard",
    "LOV": "Lov",
    "FORSKRIFT": "Forskrift",
    "KONTEKST": "Bakgrunnsmateriale",
}

_FULL_SOURCE_CHUNK_LIMIT = 60  # maks chunks ved "Vis hele kilden"


# ---------------------------------------------------------------------------

class FagchatPage(ttk.Frame):
    """Faglig AI-assistent-fane — todelt visning: chat + kildevisning."""

    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent)
        self._queue: queue.Queue = queue.Queue()
        self._busy = False
        self._src_visible = tk.BooleanVar(value=True)
        self._use_llm = tk.BooleanVar(value=True)
        self._top_k = tk.IntVar(value=5)
        self._last_context: str = ""
        self._source_chunks: dict = {}  # tag_name → (label, [ContextChunk])
        self._ref_lookup: dict[str, str] = {}  # "ISA-200 P5" → click_tag
        self._current_src_path: str = ""
        self._chat_history: list[dict[str, str]] = []  # samtalehistorikk for LLM
        self._MAX_HISTORY = 6  # maks antall meldinger (3 bruker + 3 svar)
        self._thinking_active = False
        self._thinking_step = 0

        # Avatarbilder for chat
        self._user_avatar: tk.PhotoImage | None = None
        self._bot_avatar: tk.PhotoImage | None = None
        self._load_avatars()

        self._build_ui()
        self._poll_queue()

    _AVATAR_SIZE = 80  # piksel (kvadratisk)

    def _load_avatars(self) -> None:
        """Last avatarbilder fra doc/pictures og skaler til 30×30px."""
        try:
            import app_paths
            from PIL import Image, ImageTk  # type: ignore[import-untyped]

            pic_dir = None
            for base in [app_paths.sources_dir(), app_paths.data_dir()]:
                if base and (base / "doc" / "pictures").is_dir():
                    pic_dir = base / "doc" / "pictures"
                    break
            if pic_dir is None:
                return

            sz = self._AVATAR_SIZE

            def _load_square(path: Path) -> tk.PhotoImage | None:
                if not path.exists():
                    return None
                img = Image.open(str(path))
                # Sentrert crop til kvadrat
                w, h = img.size
                side = min(w, h)
                left = (w - side) // 2
                top = (h - side) // 2
                img = img.crop((left, top, left + side, top + side))
                img = img.resize((sz, sz), Image.LANCZOS)
                return ImageTk.PhotoImage(img)

            user_path = pic_dir / "Faceless avatar with speech bubble.png"
            bot_path = pic_dir / "Vennerlig AI-robot med lysboble.png"
            self._user_avatar = _load_square(user_path)
            self._bot_avatar = _load_square(bot_path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI-bygg

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_toolbar(row=0)
        self._build_main_area(row=1)
        self._build_input_area(row=2)
        self._build_status_bar(row=3)

    def _build_toolbar(self, *, row: int) -> None:
        bar = tk.Frame(self, background="#FFFDF8", padx=12, pady=6)
        bar.grid(row=row, column=0, sticky="ew")
        # Bunn-border
        tk.Frame(self, background="#D7D1C7", height=1).grid(
            row=row, column=0, sticky="sew")

        tk.Label(bar, text="Faglig AI-assistent",
                 font=("Segoe UI Semibold", 12), foreground="#1F2430",
                 background="#FFFDF8").pack(side=tk.LEFT)

        right = ttk.Frame(bar)
        right.pack(side=tk.RIGHT)

        ttk.Label(right, text="Top-k:").pack(side=tk.LEFT, padx=(0, 2))
        ttk.Spinbox(right, from_=3, to=15, textvariable=self._top_k,
                    width=4).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Checkbutton(right, text="LLM-svar", variable=self._use_llm).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(right, text="Vis kilder", variable=self._src_visible,
                        command=self._toggle_source_panel).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(right, text="Tøm", command=self._clear_chat,
                   width=6).pack(side=tk.LEFT)

    def _build_main_area(self, *, row: int) -> None:
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.grid(row=row, column=0, sticky="nsew", padx=4, pady=2)
        self._paned = paned

        # --- Venstre: chat-logg ---
        chat_frame = ttk.Frame(paned)
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)
        paned.add(chat_frame, weight=3)

        self._chat = tk.Text(
            chat_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            cursor="arrow",
            spacing1=2,
            spacing3=2,
            padx=14,
            pady=10,
            font=("Segoe UI", 10),
            background="#F5F4EF",
            relief=tk.FLAT,
            borderwidth=0,
        )
        sb = ttk.Scrollbar(chat_frame, orient=tk.VERTICAL, command=self._chat.yview)
        self._chat.configure(yscrollcommand=sb.set)
        self._chat.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        self._chat.tag_configure(_TAG_USER,
            background="#DAF0EA", foreground=_COLOR_USER_FG,
            lmargin1=100, lmargin2=100, rmargin=20,
            spacing1=5, spacing3=5, relief=tk.FLAT,
            font=("Segoe UI", 10))
        self._chat.tag_configure("user_accent",
            font=("Segoe UI", 10), foreground="#2F6D62",
            background="#DAF0EA")
        self._chat.tag_configure(_TAG_BOT,
            background=_COLOR_BOT_BG, foreground=_COLOR_BOT_FG,
            lmargin1=16, lmargin2=28, rmargin=60,
            spacing1=2, spacing3=2, relief=tk.FLAT,
            font=("Segoe UI", 10))
        self._chat.tag_configure(_TAG_SOURCE,
            foreground="#2F6D62", underline=True,
            lmargin1=20, lmargin2=20, font=("Segoe UI", 9))
        self._chat.tag_configure(_TAG_ERROR,
            background=_COLOR_ERR_BG, foreground=_COLOR_ERR_FG,
            lmargin1=16, lmargin2=28, font=("Segoe UI", 9))
        self._chat.tag_configure(_TAG_THINKING,
            foreground="#2F6D62", font=("Segoe UI", 9, "italic"),
            lmargin1=16, background="#F0FAF7")
        self._chat.tag_configure(_TAG_HEADING,
            font=("Segoe UI Semibold", 9), foreground="#667085",
            lmargin1=16, spacing1=12, spacing3=4)

        # Meldingslabels
        self._chat.tag_configure("msg_label_user",
            font=("Segoe UI Semibold", 10), foreground="#2F6D62",
            lmargin1=100, spacing1=18, spacing3=6)
        self._chat.tag_configure("msg_label_bot",
            font=("Segoe UI Semibold", 10), foreground="#667085",
            lmargin1=16, spacing1=18, spacing3=6)
        self._chat.tag_configure("label_icon_user",
            font=("Segoe UI", 10), foreground="#2F6D62",
            background="#E5F1EE")
        self._chat.tag_configure("label_icon_bot",
            font=("Segoe UI", 10), foreground="#667085",
            background="#F0EDE6")

        # Separator mellom meldingsgrupper
        self._chat.tag_configure("msg_separator",
            foreground="#D7D1C7", font=("Segoe UI", 4),
            spacing1=8, spacing3=8, justify=tk.CENTER)

        # Kildeliste — divider og gruppering
        self._chat.tag_configure("src_divider_label",
            font=("Segoe UI Semibold", 9), foreground="#667085",
            lmargin1=16, spacing1=12, spacing3=2)
        self._chat.tag_configure("src_divider_line",
            font=("Segoe UI", 9), foreground="#D7D1C7",
            spacing1=0, spacing3=2)
        self._chat.tag_configure("src_group_header",
            font=("Segoe UI Semibold", 8), foreground="#667085",
            lmargin1=20, spacing1=6, spacing3=1)
        self._chat.tag_configure("src_separator",
            font=("Segoe UI", 8), foreground="#B0A99A")

        # Feedback- og handlingsknapper
        self._chat.tag_configure("feedback_area",
            lmargin1=16, spacing1=8, spacing3=4)
        self._chat.tag_configure("copy_btn",
            font=("Segoe UI", 9), foreground="#9CA3AF",
            lmargin1=16)
        self._chat.tag_configure("copy_btn_done",
            font=("Segoe UI", 9), foreground="#2F6D62",
            lmargin1=16)
        self._chat.tag_configure("feedback_btn",
            font=("Segoe UI", 11), foreground="#9CA3AF",
            lmargin1=16)
        self._chat.tag_configure("feedback_btn_active",
            font=("Segoe UI", 11), foreground="#2F6D62",
            lmargin1=16)
        self._chat.tag_configure("feedback_label",
            font=("Segoe UI", 8), foreground="#9CA3AF")
        self._feedback_log: list[dict] = []

        # Inline kildehenvisninger i AI-tekst (pill-stil)
        self._chat.tag_configure("inline_ref",
            font=("Segoe UI", 9), foreground="#2F6D62",
            background="#E5F1EE")

        # Markdown inline
        self._chat.tag_configure("md_bold",
            font=("Segoe UI Semibold", 10))
        self._chat.tag_configure("md_italic",
            font=("Segoe UI", 10, "italic"))
        self._chat.tag_configure("md_bold_italic",
            font=("Segoe UI Semibold", 10, "italic"))

        # Markdown block — headers
        self._chat.tag_configure("md_h2",
            font=("Segoe UI Semibold", 12), foreground="#1F2430",
            spacing1=14, spacing3=4,
            lmargin1=16, lmargin2=16)
        self._chat.tag_configure("md_h3",
            font=("Segoe UI Semibold", 10), foreground="#2F6D62",
            spacing1=12, spacing3=3,
            lmargin1=16, lmargin2=16)
        self._chat.tag_configure("md_h4",
            font=("Segoe UI", 10, "bold"), foreground="#667085",
            spacing1=10, spacing3=2,
            lmargin1=16, lmargin2=16)

        # Markdown block — lists
        self._chat.tag_configure("md_bullet",
            lmargin1=36, lmargin2=48,
            font=("Segoe UI", 10), spacing1=2, spacing3=2)
        self._chat.tag_configure("md_numbered",
            lmargin1=36, lmargin2=48,
            font=("Segoe UI", 10), spacing1=2, spacing3=2)
        self._chat.tag_configure("md_checkbox",
            lmargin1=36, lmargin2=48,
            font=("Segoe UI", 10), spacing1=2, spacing3=2)
        self._chat.tag_configure("md_checkbox_symbol",
            font=("Segoe UI", 10), foreground="#9CA3AF")
        self._chat.tag_configure("md_checkbox_checked",
            font=("Segoe UI", 10), foreground="#2F6D62")
        self._chat.tag_configure("md_paragraph_spacer",
            font=("Segoe UI", 5), spacing1=0, spacing3=0)

        # --- Høyre: kildevisningspanel ---
        self._src_frame = ttk.Frame(paned)
        self._src_frame.columnconfigure(0, weight=1)
        self._src_frame.rowconfigure(1, weight=1)  # tekst-widget ekspanderer
        paned.add(self._src_frame, weight=2)

        # Header — tydelig kildeinfo øverst
        hdr = tk.Frame(self._src_frame, background="#F5F4EF", padx=14, pady=10)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        hdr.columnconfigure(0, weight=1)

        self._src_type_var = tk.StringVar(value="")
        self._src_type_label = tk.Label(
            hdr, textvariable=self._src_type_var,
            font=("Segoe UI Semibold", 8), foreground="#ffffff",
            padx=10, pady=3,
        )
        self._src_type_label.grid(row=0, column=0, sticky="w", pady=(0, 4))

        self._src_title_var = tk.StringVar(value="Kildevisning")
        tk.Label(hdr, textvariable=self._src_title_var,
                 font=("Segoe UI Semibold", 11), foreground="#1F2430",
                 background="#F5F4EF", anchor="w", wraplength=450,
                 justify=tk.LEFT).grid(row=1, column=0, sticky="w")

        self._src_anchor_var = tk.StringVar(value="")
        self._src_anchor_label = tk.Label(
            hdr, textvariable=self._src_anchor_var,
            font=("Segoe UI", 9), foreground="#667085", background="#F5F4EF",
            anchor="w",
        )
        self._src_anchor_label.grid(row=2, column=0, sticky="w")

        # Tekst-widget
        self._src_text = tk.Text(
            self._src_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Segoe UI", 9),
            padx=10,
            pady=8,
            background="#FFFDF8",
            relief=tk.FLAT,
            borderwidth=0,
        )
        src_sb = ttk.Scrollbar(self._src_frame, orient=tk.VERTICAL, command=self._src_text.yview)
        self._src_text.configure(yscrollcommand=src_sb.set)
        self._src_text.grid(row=1, column=0, sticky="nsew")
        src_sb.grid(row=1, column=1, sticky="ns")

        self._src_text.tag_configure("anker",
            font=("Segoe UI Semibold", 9), foreground="#1A4D44",
            background="#E5F1EE", spacing1=12, spacing3=5,
            lmargin1=0, lmargin2=0,
            borderwidth=0, relief=tk.FLAT)
        self._src_text.tag_configure("sep",
            foreground="#D7D1C7", font=("Segoe UI", 4),
            spacing1=8, spacing3=8)
        self._src_text.tag_configure("src_body",
            font=("Segoe UI", 9), foreground="#1F2430",
            lmargin1=10, lmargin2=10, spacing1=2, spacing3=2,
            wrap=tk.WORD)
        self._src_text.tag_configure("src_body_bold",
            font=("Segoe UI Semibold", 9), foreground="#1F2430",
            lmargin1=10, lmargin2=10)
        self._src_text.tag_configure("src_bold",
            font=("Segoe UI Semibold", 9), foreground="#1F2430")
        self._src_text.tag_configure("src_italic",
            font=("Segoe UI", 9, "italic"), foreground="#1F2430")
        self._src_text.tag_configure("src_bold_italic",
            font=("Segoe UI Semibold", 9, "italic"), foreground="#1F2430")
        # Overskrifter i kildevisning
        self._src_text.tag_configure("src_h1",
            font=("Segoe UI Semibold", 11), foreground="#1A4D44",
            lmargin1=10, lmargin2=10, spacing1=14, spacing3=6)
        self._src_text.tag_configure("src_h2",
            font=("Segoe UI Semibold", 10), foreground="#2F6D62",
            lmargin1=10, lmargin2=10, spacing1=12, spacing3=4)
        # Paragrafnumre (§-referanser)
        self._src_text.tag_configure("src_para_nr",
            font=("Segoe UI Semibold", 9), foreground="#2F6D62",
            lmargin1=10, lmargin2=24, spacing1=8, spacing3=2)
        # Underpunkter (a), (b), (i), (ii)
        self._src_text.tag_configure("src_subpoint",
            font=("Segoe UI", 9), foreground="#1F2430",
            lmargin1=28, lmargin2=40, spacing1=1, spacing3=1)
        # Kulepunkter
        self._src_text.tag_configure("src_bullet",
            font=("Segoe UI", 9), foreground="#1F2430",
            lmargin1=24, lmargin2=36, spacing1=1, spacing3=1)
        # Krav-linjer (KRAV:, FORKLARING:)
        self._src_text.tag_configure("src_krav_label",
            font=("Segoe UI Semibold", 9), foreground="#991B1B")
        self._src_text.tag_configure("src_forklaring_label",
            font=("Segoe UI Semibold", 9), foreground="#667085")
        # Kategori / metadata-linje
        self._src_text.tag_configure("src_meta",
            font=("Segoe UI", 8), foreground="#9CA3AF",
            lmargin1=10, lmargin2=10, spacing1=1, spacing3=1)
        # TOC-lignende linjer (skjules/dimmes)
        self._src_text.tag_configure("src_toc",
            font=("Segoe UI", 8), foreground="#B0A99A",
            lmargin1=10, lmargin2=10, spacing1=0, spacing3=0)
        self._src_text.tag_configure("placeholder", foreground="#9ca3af",
                                     font=("Segoe UI", 10, "italic"))

        # Knappelinje under tekst
        self._src_btn_frame = ttk.Frame(self._src_frame, padding=(4, 3))
        self._src_btn_frame.grid(row=2, column=0, columnspan=2, sticky="ew")
        self._open_pdf_btn = ttk.Button(
            self._src_btn_frame, text="Åpne PDF",
            command=self._open_current_pdf, state=tk.DISABLED,
        )
        self._open_pdf_btn.pack(side=tk.LEFT, padx=(0, 6))

        self._show_full_btn = ttk.Button(
            self._src_btn_frame, text="Vis hele kilden",
            command=self._show_full_source, state=tk.DISABLED,
        )
        self._show_full_btn.pack(side=tk.LEFT)

        self._edit_src_btn = ttk.Button(
            self._src_btn_frame, text="Rediger kilde",
            command=self._toggle_edit_source, state=tk.DISABLED,
        )
        self._edit_src_btn.pack(side=tk.LEFT, padx=(6, 0))

        self._save_src_btn = ttk.Button(
            self._src_btn_frame, text="Lagre",
            command=self._save_edited_source, style="Primary.TButton",
        )
        # Skjult som standard — vises kun i redigeringsmodus
        self._cancel_edit_btn = ttk.Button(
            self._src_btn_frame, text="Avbryt",
            command=self._cancel_edit_source,
        )

        self._editing_source = False
        self._current_source_id: str = ""
        self._current_source_txt_path: str = ""
        self._show_placeholder()

    def _build_input_area(self, *, row: int) -> None:
        # Ytre wrapper med 1px topp-border
        outer = tk.Frame(self, background="#FFFDF8")
        outer.grid(row=row, column=0, sticky="ew")
        tk.Frame(outer, background="#D7D1C7", height=1).pack(fill=tk.X)

        frame = tk.Frame(outer, background="#FFFDF8", padx=8, pady=4)
        frame.pack(fill=tk.X)
        frame.columnconfigure(0, weight=1)

        self._input = ttk.Entry(frame, font=("Segoe UI", 11))
        self._input.grid(row=0, column=0, sticky="ew", padx=(0, 8), ipady=4)
        self._input.bind("<Return>", lambda _e: self._send())
        self._input.bind("<KP_Enter>", lambda _e: self._send())

        self._send_btn = ttk.Button(frame, text="Send", command=self._send,
                                    width=8, style="Primary.TButton")
        self._send_btn.grid(row=0, column=1)

        tk.Label(frame,
                 text="Spørsmål sendes med relevante fagutdrag fra kildebiblioteket — ingen klientdata.",
                 foreground="#9CA3AF", background="#FFFDF8",
                 font=("Segoe UI", 8)).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

    def _build_status_bar(self, *, row: int) -> None:
        self._status_var = tk.StringVar(value="Klar")
        outer = tk.Frame(self, background="#F5F4EF")
        outer.grid(row=row, column=0, sticky="ew", padx=0, pady=0)
        tk.Frame(outer, background="#D7D1C7", height=1).pack(fill=tk.X)
        tk.Label(outer, textvariable=self._status_var,
                 font=("Segoe UI", 9), foreground="#667085",
                 background="#F5F4EF", padx=6, pady=2).pack(side=tk.LEFT)

    # ------------------------------------------------------------------
    # Kildevisningspanel

    def _show_placeholder(self) -> None:
        self._src_text.configure(state=tk.NORMAL)
        self._src_text.delete("1.0", tk.END)
        self._src_text.insert(tk.END, _PLACEHOLDER, "placeholder")
        self._src_text.configure(state=tk.DISABLED)
        self._src_type_var.set("")
        self._src_type_label.grid_remove()
        self._src_title_var.set("Kildevisning")
        self._src_anchor_var.set("")
        self._current_src_path = ""
        self._current_source_id = ""
        self._current_source_txt_path = ""
        self._open_pdf_btn.configure(state=tk.DISABLED)
        self._show_full_btn.configure(state=tk.DISABLED)
        self._edit_src_btn.configure(state=tk.DISABLED)

    def _update_source_header(self, chunks: list) -> None:
        """Oppdater kilde-headeren med metadata fra chunks."""
        if not chunks:
            return
        m = chunks[0].metadata or {}
        source_id = m.get("source_id") or ""
        source_title = m.get("source_title") or source_id
        doc_type = m.get("doc_type") or ""
        anchor = m.get("anchor") or ""

        # Type-badge
        type_label = _DOC_TYPE_LABELS.get(doc_type, doc_type)
        if type_label:
            self._src_type_var.set(type_label.upper())
            type_colors = {
                "ISA": "#2F6D62", "KRAV": "#B44D2E", "SJEKKLISTE": "#2F6D62",
                "NRS": "#8B6914", "LOV": "#6B4C8A", "FORSKRIFT": "#6B4C8A",
                "KONTEKST": "#667085",
            }
            self._src_type_label.configure(background=type_colors.get(doc_type, "#8b7355"))
            self._src_type_label.grid()
        else:
            self._src_type_label.grid_remove()

        # Tittel
        self._src_title_var.set(source_title)

        # Anker-info
        if anchor:
            # Samle alle unike ankere fra chunks
            anchors = []
            seen = set()
            for c in chunks:
                a = (c.metadata or {}).get("anchor") or ""
                if a and a not in seen:
                    seen.add(a)
                    anchors.append(a)
            self._src_anchor_var.set(f"Avsnitt: {', '.join(anchors)}")
        else:
            self._src_anchor_var.set("")

        # Source-id for "Vis hele kilden"
        self._current_source_id = source_id
        self._show_full_btn.configure(state=tk.NORMAL if source_id else tk.DISABLED)

        # Filsti for "Åpne PDF" — foretrekk display_file (original PDF)
        display_path = m.get("display_file") or m.get("source_path") or ""
        self._current_src_path = display_path
        if display_path and Path(display_path).exists():
            self._open_pdf_btn.configure(state=tk.NORMAL)
        else:
            self._open_pdf_btn.configure(state=tk.DISABLED)

        # Filsti for "Rediger kilde" — bruk source_path (txt-filen)
        txt_path = m.get("source_path") or ""
        self._current_source_txt_path = txt_path
        if txt_path and Path(txt_path).exists() and txt_path.endswith(".txt"):
            self._edit_src_btn.configure(state=tk.NORMAL)
        else:
            self._edit_src_btn.configure(state=tk.DISABLED)

    # Regex for inline markdown i kildevisning
    _SRC_INLINE_RE = re.compile(
        r'\*\*\*(.+?)\*\*\*'    # ***bold italic***
        r'|\*\*(.+?)\*\*'       # **bold**
        r'|\*(.+?)\*',          # *italic*
        re.DOTALL,
    )

    def _insert_src_inline(self, text: str, base_tag: str) -> None:
        """Insert text med inline bold/italic rendering i kildevisning."""
        last_end = 0
        for m in self._SRC_INLINE_RE.finditer(text):
            if m.start() > last_end:
                self._src_text.insert(tk.END, text[last_end:m.start()], base_tag)
            if m.group(1):        # ***bold italic***
                self._src_text.insert(tk.END, m.group(1), (base_tag, "src_bold_italic"))
            elif m.group(2):      # **bold**
                self._src_text.insert(tk.END, m.group(2), (base_tag, "src_bold"))
            elif m.group(3):      # *italic*
                self._src_text.insert(tk.END, m.group(3), (base_tag, "src_italic"))
            last_end = m.end()
        if last_end < len(text):
            self._src_text.insert(tk.END, text[last_end:], base_tag)

    def _insert_src_body(self, text: str) -> None:
        """Insert source body text with smart formatting."""
        import re as _re
        text = _re.sub(r"\n{3,}", "\n\n", text.strip())

        # Regex-mønstre for linjeklassifisering
        _RE_TOC = _re.compile(r'^.{5,}\.{5,}')  # "Innhold ........... 5"
        _RE_PARA_NR = _re.compile(r'^(\d{1,3}[a-z]?)\.\s+(.+)')  # "11. Revisors mål..."
        _RE_SUBPOINT = _re.compile(r'^\(([a-z]|[ivx]+)\)\s*(.*)')  # "(a) Påstander..."
        _RE_BULLET = _re.compile(r'^[-•–]\s+(.+)')  # "- punkt" eller "• punkt"
        _RE_KRAV = _re.compile(r'^KRAV:\s*(.*)', _re.IGNORECASE)
        _RE_FORKLARING = _re.compile(r'^FORKLARING:\s*(.*)', _re.IGNORECASE)
        _RE_KATEGORI = _re.compile(r'^\[Kategori:\s*(.*)\]')
        _RE_HEADER_CAPS = _re.compile(r'^[A-ZÆØÅ][A-ZÆØÅ\s,\-/]{8,}$')  # "INNHOLD" etc.
        _RE_SECTION = _re.compile(
            r'^(Veiledning og utfyllende forklaringer|Definisjoner|Krav|'
            r'Innledning|Mål|Vedlegg|Ikrafttredelsesdato|'
            r'Denne ISA-ens virkeområde)$', _re.IGNORECASE)

        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                self._src_text.insert(tk.END, "\n", "sep")
                continue

            # TOC-linjer (dimmes)
            if _RE_TOC.match(stripped):
                self._src_text.insert(tk.END, stripped + "\n", "src_toc")
                continue

            # Seksjonsoverskrifter
            if _RE_SECTION.match(stripped):
                self._src_text.insert(tk.END, stripped + "\n", "src_h1")
                continue

            # CAPS-overskrifter (INNHOLD, KRAV osv.)
            if _RE_HEADER_CAPS.match(stripped) and len(stripped) < 60:
                self._src_text.insert(tk.END, stripped + "\n", "src_h2")
                continue

            # Paragrafnumre (11. Revisors mål er...)
            m = _RE_PARA_NR.match(stripped)
            if m:
                self._src_text.insert(tk.END, f"{m.group(1)}. ", "src_para_nr")
                self._insert_src_inline(m.group(2), "src_body")
                self._src_text.insert(tk.END, "\n", "src_body")
                continue

            # Underpunkter (a), (b), (i)
            m = _RE_SUBPOINT.match(stripped)
            if m:
                self._src_text.insert(tk.END, f"({m.group(1)}) ", "src_para_nr")
                self._insert_src_inline(m.group(2) or "", "src_subpoint")
                self._src_text.insert(tk.END, "\n", "src_subpoint")
                continue

            # Kulepunkter
            m = _RE_BULLET.match(stripped)
            if m:
                self._src_text.insert(tk.END, "  •  ", "src_para_nr")
                self._insert_src_inline(m.group(1), "src_bullet")
                self._src_text.insert(tk.END, "\n", "src_bullet")
                continue

            # KRAV: linjer
            m = _RE_KRAV.match(stripped)
            if m:
                self._src_text.insert(tk.END, "KRAV: ", "src_krav_label")
                self._insert_src_inline(m.group(1), "src_body")
                self._src_text.insert(tk.END, "\n", "src_body")
                continue

            # FORKLARING: linjer
            m = _RE_FORKLARING.match(stripped)
            if m:
                self._src_text.insert(tk.END, "FORKLARING: ", "src_forklaring_label")
                self._insert_src_inline(m.group(1), "src_body")
                self._src_text.insert(tk.END, "\n", "src_body")
                continue

            # [Kategori: ...] metadata
            m = _RE_KATEGORI.match(stripped)
            if m:
                self._src_text.insert(tk.END, stripped + "\n", "src_meta")
                continue

            # Vanlig tekst — rendre inline markdown
            self._insert_src_inline(stripped, "src_body")
            self._src_text.insert(tk.END, "\n", "src_body")

    def _show_source_in_panel(self, tag_name: str) -> None:
        entry = self._source_chunks.get(tag_name)
        if not entry:
            return
        label, chunks = entry

        self._update_source_header(chunks)

        self._src_text.configure(state=tk.NORMAL)
        self._src_text.delete("1.0", tk.END)

        for i, chunk in enumerate(chunks):
            if i > 0:
                self._src_text.insert(tk.END, "\n" + "─" * 30 + "\n\n", "sep")
            m = chunk.metadata or {}
            anker = m.get("anchor") or ""
            if anker:
                self._src_text.insert(tk.END, f" {anker} \n", "anker")
            self._insert_src_body(chunk.text or "")

        self._src_text.configure(state=tk.DISABLED)
        self._src_text.see("1.0")

    def _show_full_source(self) -> None:
        """Hent og vis alle chunks fra denne kilden, sortert etter chunk_index."""
        source_id = self._current_source_id
        if not source_id or not _ensure_rag():
            return

        self._status_var.set(f"Henter hele {source_id}…")
        self.update_idletasks()

        def _load() -> None:
            try:
                from rag_assistant.rag_index import get_or_create_collection  # type: ignore
                col = get_or_create_collection(db_path=str(_RAG_REPO / "ragdb"))
                res = col.get(
                    where={"source_id": source_id},
                    include=["documents", "metadatas"],
                    limit=_FULL_SOURCE_CHUNK_LIMIT,
                )
                docs = res.get("documents", [])
                metas = res.get("metadatas", [])
                # Sorter etter chunk_index
                pairs = sorted(
                    zip(docs, metas),
                    key=lambda p: int(p[1].get("chunk_index", 0)) if p[1] else 0,
                )
                self._queue.put(("full_source", (source_id, pairs)))
            except Exception as exc:
                self._queue.put(("error", f"Kunne ikke hente kilde: {exc}"))

        threading.Thread(target=_load, daemon=True).start()

    def _render_full_source(self, source_id: str, pairs: list) -> None:
        """Vis alle chunks for en kilde i kildevisningspanelet."""
        self._src_text.configure(state=tk.NORMAL)
        self._src_text.delete("1.0", tk.END)

        prev_anchor = ""
        for doc, meta in pairs:
            anchor = (meta or {}).get("anchor") or ""
            if anchor and anchor != prev_anchor:
                if prev_anchor:
                    self._src_text.insert(tk.END, "\n" + "─" * 30 + "\n\n", "sep")
                self._src_text.insert(tk.END, f" {anchor} \n", "anker")
                prev_anchor = anchor
            elif not anchor and prev_anchor:
                self._src_text.insert(tk.END, "\n" + "─" * 30 + "\n\n", "sep")
                prev_anchor = ""
            self._insert_src_body(doc or "")

        total = len(pairs)
        if total >= _FULL_SOURCE_CHUNK_LIMIT:
            self._src_text.insert(
                tk.END,
                f"\n{'─' * 40}\n(Viser {total} av flere avsnitt — bruk \u00abÅpne PDF\u00bb for hele dokumentet)\n",
                "sep",
            )

        self._src_text.configure(state=tk.DISABLED)
        self._src_text.see("1.0")

        self._src_anchor_var.set(f"Hele kilden ({total} avsnitt)")
        self._status_var.set(f"{source_id} — {total} avsnitt hentet")

    def _open_current_pdf(self) -> None:
        if self._current_src_path:
            self._open_file(self._current_src_path)

    def _toggle_edit_source(self) -> None:
        """Bytt kildevisningen til redigeringsmodus."""
        path = self._current_source_txt_path
        if not path or not Path(path).exists():
            return
        # Les hele filen og vis i editerbar tekst-widget
        try:
            content = Path(path).read_text(encoding="utf-8")
        except Exception:
            return
        self._editing_source = True
        self._src_text.configure(state=tk.NORMAL)
        self._src_text.delete("1.0", tk.END)
        self._src_text.insert("1.0", content)
        # Endre bakgrunnsfarge for å vise at vi er i redigeringsmodus
        self._src_text.configure(background="#FFFFF0", font=("Consolas", 9))
        # Tastatursnarvei: Ctrl+B = bold, Ctrl+I = kursiv, Ctrl+S = lagre
        self._src_text.bind("<Control-b>", lambda e: self._wrap_selection("**"))
        self._src_text.bind("<Control-i>", lambda e: self._wrap_selection("*"))
        self._src_text.bind("<Control-s>", lambda e: self._save_edited_source())
        # Vis lagre/avbryt, skjul andre knapper
        self._edit_src_btn.pack_forget()
        self._open_pdf_btn.pack_forget()
        self._show_full_btn.pack_forget()
        self._save_src_btn.pack(side=tk.LEFT, padx=(0, 6))
        self._cancel_edit_btn.pack(side=tk.LEFT)

    def _save_edited_source(self) -> None:
        """Lagre redigert innhold tilbake til kildefilen."""
        path = self._current_source_txt_path
        if not path:
            return
        content = self._src_text.get("1.0", tk.END).rstrip("\n")
        try:
            Path(path).write_text(content + "\n", encoding="utf-8")
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Lagringsfeil", f"Kunne ikke lagre:\n{e}")
            return
        self._exit_edit_mode()
        self._status_var.set(f"Lagret: {Path(path).name}  (kjør reindeksering for å oppdatere RAG)")

    def _cancel_edit_source(self) -> None:
        """Avbryt redigering og gå tilbake til visning."""
        self._exit_edit_mode()
        # Re-vis kilden som før
        if self._current_source_id:
            # Finn tag som matcher current source
            for tag, (lbl, chunks) in self._source_chunks.items():
                m = (chunks[0].metadata or {}) if chunks else {}
                if m.get("source_id") == self._current_source_id:
                    self._show_source_in_panel(tag)
                    return
        self._show_placeholder()

    def _wrap_selection(self, marker: str) -> str:
        """Wrap/unwrap markert tekst med markdown-markør (**, *)."""
        try:
            sel_start = self._src_text.index(tk.SEL_FIRST)
            sel_end = self._src_text.index(tk.SEL_LAST)
            selected = self._src_text.get(sel_start, sel_end)
        except tk.TclError:
            return "break"  # Ingen seleksjon

        ml = len(marker)
        # Toggle: fjern markør hvis den allerede er der
        if selected.startswith(marker) and selected.endswith(marker) and len(selected) > ml * 2:
            unwrapped = selected[ml:-ml]
            self._src_text.delete(sel_start, sel_end)
            self._src_text.insert(sel_start, unwrapped)
            # Behold seleksjonen
            self._src_text.tag_add(tk.SEL, sel_start, f"{sel_start}+{len(unwrapped)}c")
        else:
            wrapped = f"{marker}{selected}{marker}"
            self._src_text.delete(sel_start, sel_end)
            self._src_text.insert(sel_start, wrapped)
            self._src_text.tag_add(tk.SEL, sel_start, f"{sel_start}+{len(wrapped)}c")
        return "break"  # Forhindre default handling

    def _exit_edit_mode(self) -> None:
        """Gjenopprett kildevisning fra redigeringsmodus."""
        self._editing_source = False
        # Fjern redigerings-bindings
        for key in ("<Control-b>", "<Control-i>", "<Control-s>"):
            self._src_text.unbind(key)
        self._src_text.configure(
            state=tk.DISABLED, background="#FFFDF8", font=("Segoe UI", 9))
        # Gjenopprett knapper
        self._save_src_btn.pack_forget()
        self._cancel_edit_btn.pack_forget()
        self._open_pdf_btn.pack(side=tk.LEFT, padx=(0, 6))
        self._show_full_btn.pack(side=tk.LEFT)
        self._edit_src_btn.pack(side=tk.LEFT, padx=(6, 0))

    def _toggle_source_panel(self) -> None:
        if self._src_visible.get():
            try:
                self._paned.add(self._src_frame, weight=2)
            except Exception:
                pass
        else:
            try:
                self._paned.forget(self._src_frame)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Chat-logg helpers

    def _append(self, text: str, tag: str) -> None:
        self._chat.configure(state=tk.NORMAL)
        self._chat.insert(tk.END, text + "\n", tag)
        self._chat.configure(state=tk.DISABLED)
        self._chat.see(tk.END)

    # ------------------------------------------------------------------
    # Feedback (👍/👎)

    def _insert_feedback_buttons(self, question: str, answer: str) -> None:
        """Sett inn tommel opp/ned-knapper etter et AI-svar."""
        idx = len(self._feedback_log)
        entry = {"question": question, "answer": answer, "rating": None}
        self._feedback_log.append(entry)

        tag_up = f"fb_up_{idx}"
        tag_down = f"fb_down_{idx}"

        tag_copy = f"fb_copy_{idx}"

        self._chat.configure(state=tk.NORMAL)
        self._chat.insert(tk.END, "\n", "feedback_area")
        self._chat.insert(tk.END, "  📋 Kopier svar  ", ("copy_btn", tag_copy))
        self._chat.insert(tk.END, "  👍 ", ("feedback_btn", tag_up))
        self._chat.insert(tk.END, "  👎 ", ("feedback_btn", tag_down))
        self._chat.insert(tk.END, " Var svaret nyttig?", "feedback_label")
        self._chat.insert(tk.END, "\n", "feedback_area")
        self._chat.configure(state=tk.DISABLED)

        self._chat.tag_bind(tag_copy, "<Button-1>",
                            lambda e, a=answer, tc=tag_copy:
                            self._copy_answer(a, tc))
        self._chat.tag_bind(tag_up, "<Button-1>",
                            lambda e, i=idx, tu=tag_up, td=tag_down:
                            self._on_feedback(i, "up", tu, td))
        self._chat.tag_bind(tag_down, "<Button-1>",
                            lambda e, i=idx, tu=tag_up, td=tag_down:
                            self._on_feedback(i, "down", tu, td))
        for t in (tag_up, tag_down, tag_copy):
            self._chat.tag_bind(t, "<Enter>",
                                lambda e: self._chat.configure(cursor="hand2"))
            self._chat.tag_bind(t, "<Leave>",
                                lambda e: self._chat.configure(cursor="arrow"))

    def _copy_answer(self, answer: str, tag_copy: str) -> None:
        """Kopier AI-svar til utklippstavlen."""
        # Strip markdown for ren tekst
        import re as _re
        clean = _re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', answer)
        self.clipboard_clear()
        self.clipboard_append(clean)
        # Visuell bekreftelse
        self._chat.tag_configure(tag_copy, foreground="#2F6D62")
        # Oppdater teksten midlertidig
        try:
            ranges = self._chat.tag_ranges(tag_copy)
            if ranges:
                self._chat.configure(state=tk.NORMAL)
                self._chat.delete(ranges[0], ranges[1])
                self._chat.insert(ranges[0], "  ✓ Kopiert!  ", ("copy_btn_done", tag_copy))
                self._chat.configure(state=tk.DISABLED)
        except Exception:
            pass

    def _on_feedback(self, idx: int, rating: str, tag_up: str, tag_down: str) -> None:
        """Registrer feedback og oppdater visuelt."""
        if idx >= len(self._feedback_log):
            return
        self._feedback_log[idx]["rating"] = rating

        self._chat.configure(state=tk.NORMAL)
        # Oppdater visuelt: aktiv knapp får farge, den andre gråes ut
        if rating == "up":
            self._chat.tag_configure(tag_up, foreground="#2F6D62")
            self._chat.tag_configure(tag_down, foreground="#D7D1C7")
        else:
            self._chat.tag_configure(tag_up, foreground="#D7D1C7")
            self._chat.tag_configure(tag_down, foreground="#C0392B")
        self._chat.configure(state=tk.DISABLED)

        # Lagre til fil
        self._save_feedback(self._feedback_log[idx])

    def _save_feedback(self, entry: dict) -> None:
        """Lagre feedback til JSON-fil."""
        import json
        import app_paths
        from datetime import datetime
        fb_file = app_paths.data_file("fagchat_feedback.json", subdir=".session")
        records: list = []
        try:
            if fb_file.exists():
                records = json.loads(fb_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        records.append({
            "timestamp": datetime.now().isoformat(),
            "question": entry["question"][:500],
            "answer": entry["answer"][:1000],
            "rating": entry["rating"],
        })
        try:
            fb_file.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _insert_formatted(self, text: str, base_tags: tuple) -> None:
        """Insert text with inline bold/italic formatting."""
        last_end = 0
        for m in _INLINE_RE.finditer(text):
            if m.start() > last_end:
                self._chat.insert(tk.END, text[last_end:m.start()], base_tags)
            if m.group(1):        # ***bold italic***
                self._chat.insert(tk.END, m.group(1), (*base_tags, "md_bold_italic"))
            elif m.group(2):      # **bold**
                self._chat.insert(tk.END, m.group(2), (*base_tags, "md_bold"))
            elif m.group(3):      # *italic*
                self._chat.insert(tk.END, m.group(3), (*base_tags, "md_italic"))
            last_end = m.end()
        if last_end < len(text):
            self._chat.insert(tk.END, text[last_end:], base_tags)

    def _resolve_ref(self, ref: str) -> str | None:
        """Finn click_tag for en kildehenvisning, med fuzzy fallback."""
        # Eksakt match: "KRAV-ISA-500 P8"
        tag = self._ref_lookup.get(ref)
        if tag:
            return tag
        # Prøv uten anker: "KRAV-ISA-500" (anker = siste ord som starter med P/A)
        parts = ref.rsplit(" ", 1)
        if len(parts) == 2 and parts[1][:1] in ("P", "A"):
            tag = self._ref_lookup.get(parts[0])
            if tag:
                return tag
        # Prefix-match: finn første nøkkel som starter med ref
        for key in self._ref_lookup:
            if key.startswith(ref):
                return self._ref_lookup[key]
        return None

    def _insert_inline(self, text: str, base_tags) -> None:
        """Insert text with bold/italic + clickable source references."""
        if isinstance(base_tags, str):
            base_tags = (base_tags,)

        # Split by source references: (ISA-200 P5), (KRAV-ISA-500 P8) etc.
        segments = _SOURCE_REF_RE.split(text)
        for i, part in enumerate(segments):
            if i % 2 == 1:
                # This is a captured source reference
                click_tag = self._resolve_ref(part)
                if click_tag:
                    self._chat.insert(tk.END, part, (*base_tags, "inline_ref", click_tag))
                else:
                    self._chat.insert(tk.END, f"({part})", base_tags)
            else:
                self._insert_formatted(part, base_tags)

    def _render_markdown(self, text: str, base_tag: str) -> None:
        """Render markdown text into the chat widget with proper formatting."""
        self._chat.configure(state=tk.NORMAL)
        for line in text.split("\n"):
            stripped = line.strip()

            # Tom linje → paragraf-spacer
            if not stripped:
                self._chat.insert(tk.END, "\n", (base_tag, "md_paragraph_spacer"))
                continue

            # Headers: ## / ### / ####
            hm = _HEADING_RE.match(stripped)
            if hm:
                level = len(hm.group(1))  # 2, 3, or 4
                tag = f"md_h{min(level, 4)}"
                self._insert_inline(hm.group(2), (base_tag, tag))
                self._chat.insert(tk.END, "\n", base_tag)
                continue

            # Checkbox unchecked: - [ ] text
            cm = _CHECKBOX_UNCHECKED_RE.match(stripped)
            if cm:
                self._chat.insert(tk.END, "  \u2610 ", (base_tag, "md_checkbox_symbol"))
                self._insert_inline(cm.group(1), (base_tag, "md_checkbox"))
                self._chat.insert(tk.END, "\n", base_tag)
                continue

            # Checkbox checked: - [x] text
            cx = _CHECKBOX_CHECKED_RE.match(stripped)
            if cx:
                self._chat.insert(tk.END, "  \u2611 ", (base_tag, "md_checkbox_checked"))
                self._insert_inline(cx.group(1), (base_tag, "md_checkbox"))
                self._chat.insert(tk.END, "\n", base_tag)
                continue

            # Bullet: - text (men ikke **bold** som starter med *)
            bm = _BULLET_RE.match(stripped)
            if bm and not stripped.startswith("**"):
                self._chat.insert(tk.END, "  \u2022 ", (base_tag, "md_bullet"))
                self._insert_inline(bm.group(1), (base_tag, "md_bullet"))
                self._chat.insert(tk.END, "\n", base_tag)
                continue

            # Numbered: 1. text
            nm = _NUMBERED_RE.match(stripped)
            if nm:
                self._chat.insert(tk.END, f"  {nm.group(1)} ", (base_tag, "md_numbered"))
                self._insert_inline(nm.group(2), (base_tag, "md_numbered"))
                self._chat.insert(tk.END, "\n", base_tag)
                continue

            # Vanlig tekst
            self._insert_inline(stripped, base_tag)
            self._chat.insert(tk.END, "\n", base_tag)

        self._chat.configure(state=tk.DISABLED)
        self._chat.see(tk.END)

    def _start_thinking(self) -> None:
        """Start animated thinking indicator."""
        self._thinking_step = 0
        self._thinking_active = True
        self._append("Henter faglig kontekst", _TAG_THINKING)
        self._animate_thinking()

    def _animate_thinking(self) -> None:
        """Cycle dots: ·  → ··  → ··· → repeat."""
        if not self._thinking_active:
            return
        self._thinking_step = (self._thinking_step + 1) % 4
        dots = " " + "·" * (self._thinking_step or 1)
        # Oppdater siste thinking-linje
        ranges = self._chat.tag_ranges(_TAG_THINKING)
        if ranges:
            self._chat.configure(state=tk.NORMAL)
            start = ranges[-2]
            end = ranges[-1]
            self._chat.delete(start, end)
            self._chat.insert(start, f"Henter faglig kontekst{dots}\n", _TAG_THINKING)
            self._chat.configure(state=tk.DISABLED)
            self._chat.see(tk.END)
        self.after(400, self._animate_thinking)

    def _remove_thinking(self) -> None:
        self._thinking_active = False
        self._chat.configure(state=tk.NORMAL)
        ranges = self._chat.tag_ranges(_TAG_THINKING)
        if ranges:
            last_start = ranges[-2]
            last_end = ranges[-1]
            self._chat.delete(last_start, last_end)
        self._chat.configure(state=tk.DISABLED)

    def _clear_chat(self) -> None:
        self._thinking_active = False
        self._chat.configure(state=tk.NORMAL)
        self._chat.delete("1.0", tk.END)
        self._chat.configure(state=tk.DISABLED)
        self._last_context = ""
        self._source_chunks = {}
        self._ref_lookup = {}
        self._chat_history = []
        self._show_placeholder()
        self._status_var.set("Klar")

    def _append_clickable_source(self, text: str, click_tag: str) -> None:
        self._chat.configure(state=tk.NORMAL)
        self._chat.tag_configure(click_tag, foreground="#2F6D62", underline=True)
        self._chat.tag_bind(click_tag, "<Button-1>",
                            lambda e, t=click_tag: self._show_source_in_panel(t))
        self._chat.tag_bind(click_tag, "<Enter>",
                            lambda e: self._chat.configure(cursor="hand2"))
        self._chat.tag_bind(click_tag, "<Leave>",
                            lambda e: self._chat.configure(cursor="arrow"))
        self._chat.insert(tk.END, text + "\n", (_TAG_SOURCE, click_tag))
        self._chat.configure(state=tk.DISABLED)
        self._chat.see(tk.END)

    @staticmethod
    def _open_file(path: str) -> None:
        import os
        import subprocess
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=False)
            else:
                subprocess.run(["xdg-open", path], check=False)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Send / query

    def _send(self) -> None:
        if self._busy:
            return
        q = self._input.get().strip()
        if not q:
            return

        self._input.delete(0, tk.END)
        self._chat.configure(state=tk.NORMAL)
        if self._user_avatar:
            self._chat.image_create(tk.END, image=self._user_avatar, padx=4, pady=2)
            self._chat.insert(tk.END, " ", "msg_label_user")
        else:
            self._chat.insert(tk.END, "● ", ("msg_label_user", "label_icon_user"))
        self._chat.insert(tk.END, "Du\n", "msg_label_user")
        self._chat.configure(state=tk.DISABLED)
        self._append(q, _TAG_USER)
        self._start_thinking()
        self._set_busy(True)
        self._status_var.set("⟳ Søker i fagdatabasen…")

        use_llm = self._use_llm.get()
        top_k = max(1, int(self._top_k.get() or 5))
        history_snapshot = list(self._chat_history) if use_llm else None

        def _worker() -> None:
            try:
                if not _ensure_rag():
                    self._queue.put(("error",
                        "RAG-motoren ikke funnet.\n"
                        f"Forventet openai-repo på: {_RAG_REPO or '../openai'}\n\n"
                        "Installer: pip install chromadb openai python-dotenv PyPDF2\n"
                        "Bygg indeks: python run_build_index.py --library kildebibliotek.json --wipe"))
                    return

                from rag_assistant.qa_service import run_query, QueryOutcome  # type: ignore
                from rag_assistant.env_loader import load_env  # type: ignore

                import os
                load_env(_RAG_REPO / ".env")
                if not os.environ.get("OPENAI_API_KEY"):
                    self._queue.put(("error",
                        "OPENAI_API_KEY mangler.\n"
                        "Legg til i openai/.env:\n  OPENAI_API_KEY=sk-..."))
                    return

                outcome: QueryOutcome = run_query(
                    q,
                    db_path=str(_RAG_REPO / "ragdb"),
                    library_path=_LIBRARY_PATH,
                    n_results=top_k,
                    expand_relations=True,
                    use_llm=use_llm,
                    history=history_snapshot,
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
                    outcome = data
                    answer = outcome.answer or None

                    # --- Bygg kildemapping FØR rendering (trengs for inline-refs) ---
                    _groups: dict = {}
                    _order: list = []
                    first_tag = None
                    for _c in (outcome.chunks or []):
                        _m = _c.metadata or {}
                        _sid = _m.get("source_id") or _m.get("source_title") or _m.get("file_name") or "KILDE"
                        _anc = _m.get("anchor") or ""
                        _lbl = f"{_sid}{(' ' + _anc) if _anc else ''}"
                        if _lbl not in _groups:
                            _groups[_lbl] = []
                            _order.append(_lbl)
                        _groups[_lbl].append(_c)

                    # Registrer click-tags og ref_lookup for inline-referanser
                    _type_groups: dict[str, list[str]] = {}
                    _tag_for_label: dict[str, str] = {}
                    for _lbl in _order:
                        _tag = f"src_{len(self._source_chunks)}"
                        self._source_chunks[_tag] = (_lbl, _groups[_lbl])
                        _tag_for_label[_lbl] = _tag
                        self._ref_lookup[_lbl] = _tag
                        # Legg til source_id-only oppslag (uten anker)
                        # slik at (ISA-500) matcher selv om labelen er "ISA-500 A4"
                        _m0 = _groups[_lbl][0].metadata or {}
                        _sid0 = _m0.get("source_id") or ""
                        if _sid0 and _sid0 not in self._ref_lookup:
                            self._ref_lookup[_sid0] = _tag
                        # Konfigurer click-tag
                        self._chat.tag_configure(_tag, foreground="#2F6D62", underline=True)
                        self._chat.tag_bind(_tag, "<Button-1>",
                                            lambda e, t=_tag: self._show_source_in_panel(t))
                        self._chat.tag_bind(_tag, "<Enter>",
                                            lambda e: self._chat.configure(cursor="hand2"))
                        self._chat.tag_bind(_tag, "<Leave>",
                                            lambda e: self._chat.configure(cursor="arrow"))
                        _dtype = (_groups[_lbl][0].metadata or {}).get("doc_type", "ANNET")
                        _type_groups.setdefault(_dtype, []).append(_lbl)
                        if first_tag is None and _dtype != "KONTEKST":
                            first_tag = _tag

                    # --- Render svar ---
                    if answer:
                        self._chat.configure(state=tk.NORMAL)
                        if self._bot_avatar:
                            self._chat.image_create(tk.END, image=self._bot_avatar, padx=4, pady=2)
                            self._chat.insert(tk.END, " ", "msg_label_bot")
                        else:
                            self._chat.insert(tk.END, "● ", ("msg_label_bot", "label_icon_bot"))
                        self._chat.insert(tk.END, "Assistent\n", "msg_label_bot")
                        self._chat.configure(state=tk.DISABLED)
                        self._render_markdown(answer, _TAG_BOT)
                        self._chat_history.append({"role": "user", "content": outcome.question})
                        self._chat_history.append({"role": "assistant", "content": answer})
                        if len(self._chat_history) > self._MAX_HISTORY:
                            self._chat_history = self._chat_history[-self._MAX_HISTORY:]
                    else:
                        self._append(
                            "Assistent: [Context-only — LLM deaktivert]\n"
                            "Klikk en kilde til høyre for å se fagutdraget.",
                            _TAG_BOT,
                        )

                    # --- Kildeliste (kompakt, horisontale pills) ---
                    if _order:
                        self._chat.configure(state=tk.NORMAL)
                        self._chat.insert(tk.END, "\n", _TAG_BOT)
                        self._chat.insert(tk.END, " ── Kilder ", "src_divider_label")
                        self._chat.insert(tk.END, "─" * 40 + "\n", "src_divider_line")
                        self._chat.configure(state=tk.DISABLED)

                        _DISPLAY_ORDER = ["ISA", "KRAV", "SJEKKLISTE", "NRS", "LOV", "FORSKRIFT", "ANNET"]
                        # KONTEKST-kilder skjules fra kildelisten (brukes kun som bakgrunn for LLM)
                        for _dtype in _DISPLAY_ORDER:
                            if _dtype not in _type_groups:
                                continue
                            _type_label = _DOC_TYPE_LABELS.get(_dtype, _dtype)
                            self._chat.configure(state=tk.NORMAL)
                            self._chat.insert(tk.END, f"  {_type_label}   ", "src_group_header")
                            # Horisontale kildelenker med · separator
                            for j, _lbl in enumerate(_type_groups[_dtype]):
                                if j > 0:
                                    self._chat.insert(tk.END, "  \u00b7  ", "src_separator")
                                _t = _tag_for_label[_lbl]
                                self._chat.insert(tk.END, _lbl, (_TAG_SOURCE, _t))
                            self._chat.insert(tk.END, "\n", _TAG_SOURCE)
                            self._chat.configure(state=tk.DISABLED)

                        # Auto-vis første kilde i panelet
                        if first_tag is not None:
                            self._show_source_in_panel(first_tag)

                    elif outcome.sources_text:
                        self._chat.configure(state=tk.NORMAL)
                        self._chat.insert(tk.END, "\n", _TAG_BOT)
                        self._chat.configure(state=tk.DISABLED)
                        self._append("Kilder:", _TAG_HEADING)
                        for line in outcome.sources_text.splitlines():
                            if line.strip():
                                self._append(f"  {line.strip()}", _TAG_SOURCE)

                    # Feedback-knapper (👍/👎)
                    if answer:
                        self._insert_feedback_buttons(
                            question=outcome.question, answer=answer)

                    # Separator etter meldingsgruppe
                    self._chat.configure(state=tk.NORMAL)
                    self._chat.insert(tk.END, "\n", "msg_separator")
                    self._chat.configure(state=tk.DISABLED)

                    self._last_context = outcome.context or ""
                    self._status_var.set(
                        f"Ferdig — {len(outcome.chunks)} chunks hentet"
                        + (", LLM-svar generert" if answer else ", context-only")
                    )

                elif kind == "full_source":
                    source_id, pairs = data
                    self._render_full_source(source_id, pairs)

                elif kind == "error":
                    self._append(f"Feil: {data}", _TAG_ERROR)
                    self._status_var.set("Feil — se feilmelding i chatten")

                if kind != "full_source":
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
    # Offentlig API

    def refresh_from_session(self, _session=None) -> None:
        pass
