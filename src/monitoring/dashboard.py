"""Sidekick-dashboard for ytelsesovervåking.

Standalone Tk-vindu som leser ``events.jsonl`` live og viser hva som
skjer i Utvalg. Starter separat prosess fra hovedappen — påvirker ikke
ytelsen på noen måte.

Kjør:

    python -m src.monitoring.dashboard

Hovedvinduet i Utvalg må kjøres separat. Dashboarden poller
``events.jsonl`` hvert 500 ms og viser nye events live.
"""

from __future__ import annotations

import statistics
import tkinter as tk
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import ttk
from typing import Any, Optional

from src.monitoring.events import TimingEvent, tail_events


# ---------------------------------------------------------------------------
# Konfigurasjon

_TIME_WINDOW_OPTIONS = (
    ("Siste minutt", 60),
    ("Siste 5 min", 300),
    ("Siste 30 min", 1800),
    ("Alt", 0),
)

_POLL_INTERVAL_MS = 500
_MAX_EVENTS_IN_VIEW = 500  # Maksimalt antall events i treet (rullerende)
_SPARKLINE_BUCKETS = 20     # Antall punkter i detalj-grafen


def _default_events_path() -> Path:
    try:
        import app_paths
        return app_paths.data_dir() / "monitoring" / "events.jsonl"
    except Exception:
        return Path(__file__).resolve().parent / "events.jsonl"


def _parse_ts(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        s = ts.rstrip("Z")
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _format_duration(ms: float) -> str:
    if ms < 1:
        return f"{ms * 1000:.0f}µs"
    if ms < 1000:
        return f"{ms:.1f}ms"
    return f"{ms / 1000:.2f}s"


def _format_time(ts_iso: str) -> str:
    dt = _parse_ts(ts_iso)
    if dt is None:
        return ts_iso[:19]  # Fall-back
    local = dt.astimezone()
    return local.strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# Dashboard

class MonitoringDashboardMixin:
    """Felles GUI-logikk for både standalone Tk og popup Toplevel."""

    def _init_dashboard(self, events_path: Optional[Path]) -> None:
        self.events_path = Path(events_path) if events_path else _default_events_path()
        self._file_offset = 0
        self._paused = False
        self._events: deque[TimingEvent] = deque(maxlen=5000)

        self._build_ui()
        self._do_initial_load()
        self.after(_POLL_INTERVAL_MS, self._poll_events)


    # ------------------------------------------------------------------
    # UI-oppbygging

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # Top-bar
        topbar = ttk.Frame(self, padding=(8, 6, 8, 4))
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.columnconfigure(7, weight=1)

        ttk.Label(topbar, text="Område:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        self._var_area = tk.StringVar(value="Alle")
        self._cmb_area = ttk.Combobox(
            topbar,
            textvariable=self._var_area,
            values=["Alle"],
            state="readonly",
            width=14,
        )
        self._cmb_area.grid(row=0, column=1, sticky="w", padx=(0, 12))
        self._cmb_area.bind("<<ComboboxSelected>>", lambda _e: self._refresh_view())

        ttk.Label(topbar, text="Vindu:").grid(row=0, column=2, sticky="w", padx=(0, 4))
        self._var_window = tk.StringVar(value=_TIME_WINDOW_OPTIONS[1][0])
        self._cmb_window = ttk.Combobox(
            topbar,
            textvariable=self._var_window,
            values=[label for label, _ in _TIME_WINDOW_OPTIONS],
            state="readonly",
            width=12,
        )
        self._cmb_window.grid(row=0, column=3, sticky="w", padx=(0, 12))
        self._cmb_window.bind("<<ComboboxSelected>>", lambda _e: self._refresh_view())

        ttk.Label(topbar, text="Min varighet (ms):").grid(row=0, column=4, sticky="w", padx=(0, 4))
        self._var_min_ms = tk.StringVar(value="0")
        ent_min = ttk.Entry(topbar, textvariable=self._var_min_ms, width=6)
        ent_min.grid(row=0, column=5, sticky="w", padx=(0, 12))
        ent_min.bind("<FocusOut>", lambda _e: self._refresh_view())
        ent_min.bind("<Return>", lambda _e: self._refresh_view())

        self._btn_pause = ttk.Button(topbar, text="⏸ Pause", command=self._toggle_pause)
        self._btn_pause.grid(row=0, column=6, sticky="w", padx=(0, 4))
        ttk.Button(topbar, text="🗑 Tøm visning", command=self._clear_view).grid(
            row=0, column=8, sticky="e"
        )

        # Status-bar
        statusbar = ttk.Frame(self, padding=(8, 0, 8, 2))
        statusbar.grid(row=1, column=0, sticky="ew")
        self._var_status = tk.StringVar(value="Kobler til events.jsonl…")
        ttk.Label(statusbar, textvariable=self._var_status, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        # Split: tabell (70%) + detalj-panel (30%)
        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))

        left = ttk.Frame(paned)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        paned.add(left, weight=3)

        self._tree = ttk.Treeview(
            left,
            columns=("tid", "area", "op", "varighet", "meta"),
            show="headings",
            selectmode="browse",
        )
        self._tree.heading("tid", text="Tid", command=lambda: self._sort_by("tid"))
        self._tree.heading("area", text="Område", command=lambda: self._sort_by("area"))
        self._tree.heading("op", text="Operasjon", command=lambda: self._sort_by("op"))
        self._tree.heading("varighet", text="Varighet", command=lambda: self._sort_by("varighet"))
        self._tree.heading("meta", text="Meta")
        self._tree.column("tid", width=90, anchor="w", stretch=False)
        self._tree.column("area", width=90, anchor="w", stretch=False)
        self._tree.column("op", width=260, anchor="w")
        self._tree.column("varighet", width=90, anchor="e", stretch=False)
        self._tree.column("meta", width=260, anchor="w")
        self._tree.grid(row=0, column=0, sticky="nsew")

        ysb = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        ysb.grid(row=0, column=1, sticky="ns")
        self._tree.configure(yscrollcommand=ysb.set)
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._refresh_detail())

        # Detalj-panel
        right = ttk.Frame(paned, padding=(8, 4, 4, 4))
        right.columnconfigure(0, weight=1)
        paned.add(right, weight=2)

        ttk.Label(right, text="Detalj", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self._var_detail_op = tk.StringVar(value="Velg en rad")
        ttk.Label(right, textvariable=self._var_detail_op, wraplength=320).grid(
            row=1, column=0, sticky="w", pady=(0, 4)
        )
        self._var_detail_stats = tk.StringVar(value="")
        ttk.Label(right, textvariable=self._var_detail_stats).grid(
            row=2, column=0, sticky="w", pady=(0, 8)
        )

        self._canvas = tk.Canvas(right, height=120, background="#FAFAF8",
                                 highlightthickness=0, bd=0)
        self._canvas.grid(row=3, column=0, sticky="ew", pady=(0, 4))
        right.rowconfigure(3, weight=0)

        ttk.Label(right, text="Siste 20 kjøringer av denne operasjonen",
                  style="Muted.TLabel").grid(row=4, column=0, sticky="w")

    # ------------------------------------------------------------------
    # Event-loading

    def _do_initial_load(self) -> None:
        self._file_offset = 0
        events, offset = tail_events(self.events_path, since_offset=0)
        for ev in events:
            self._events.append(ev)
        self._file_offset = offset
        self._refresh_area_dropdown()
        self._refresh_view()
        self._set_status()

    def _poll_events(self) -> None:
        try:
            if not self._paused:
                events, offset = tail_events(self.events_path, since_offset=self._file_offset)
                if events:
                    for ev in events:
                        self._events.append(ev)
                    self._file_offset = offset
                    self._refresh_area_dropdown()
                    self._refresh_view()
                elif offset < self._file_offset:
                    # Fil rotert — start fra begynnelsen
                    self._file_offset = 0
            self._set_status()
        finally:
            self.after(_POLL_INTERVAL_MS, self._poll_events)

    def _refresh_area_dropdown(self) -> None:
        areas = sorted({ev.area for ev in self._events if ev.area})
        current_values = list(self._cmb_area["values"])
        expected = ["Alle"] + areas
        if current_values != expected:
            self._cmb_area["values"] = expected
            if self._var_area.get() not in expected:
                self._var_area.set("Alle")

    # ------------------------------------------------------------------
    # Filter + visning

    def _active_filter(self) -> tuple[str, float, float]:
        area = self._var_area.get()
        # Time window
        window_seconds = 0
        for label, secs in _TIME_WINDOW_OPTIONS:
            if label == self._var_window.get():
                window_seconds = secs
                break
        # Min duration
        try:
            min_ms = float(self._var_min_ms.get() or 0)
        except (TypeError, ValueError):
            min_ms = 0.0
        return area, float(window_seconds), min_ms

    def _filtered_events(self) -> list[TimingEvent]:
        area, window_s, min_ms = self._active_filter()
        cutoff: Optional[datetime] = None
        if window_s > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_s)
        out: list[TimingEvent] = []
        for ev in self._events:
            if area != "Alle" and ev.area != area:
                continue
            if ev.duration_ms < min_ms:
                continue
            if cutoff is not None:
                ts = _parse_ts(ev.ts)
                if ts is not None and ts < cutoff:
                    continue
            out.append(ev)
        return out

    def _refresh_view(self) -> None:
        # Husk hvilket event som var valgt så vi prøver å re-markere
        selected_iid = self._tree.focus()

        events = self._filtered_events()
        # Behold bare nyeste N i treet
        events = events[-_MAX_EVENTS_IN_VIEW:]

        existing = set(self._tree.get_children())
        self._tree.delete(*existing)

        for ev in events:
            iid = f"{ev.ts}|{ev.pid}|{ev.op}"
            meta_str = _format_meta(ev.meta)
            try:
                self._tree.insert(
                    "", "end", iid=iid,
                    values=(_format_time(ev.ts), ev.area, ev.op,
                            _format_duration(ev.duration_ms), meta_str),
                )
            except tk.TclError:
                # Duplikat iid (kan skje hvis samme event sees to ganger i buffer)
                continue

        # Scroll til bunnen for live-følelse (med mindre bruker har valgt rad)
        if selected_iid and self._tree.exists(selected_iid):
            self._tree.see(selected_iid)
            self._tree.selection_set(selected_iid)
        else:
            children = self._tree.get_children()
            if children:
                self._tree.see(children[-1])

        self._refresh_detail()

    def _refresh_detail(self) -> None:
        iid = self._tree.focus()
        if not iid:
            self._var_detail_op.set("Velg en rad")
            self._var_detail_stats.set("")
            self._canvas.delete("all")
            return
        # Hent op fra iid
        try:
            _ts, _pid, op = iid.split("|", 2)
        except ValueError:
            return

        # Samle alle samples for denne op'en
        samples = [ev.duration_ms for ev in self._events if ev.op == op]
        if not samples:
            return

        self._var_detail_op.set(op)
        stats = _compute_stats(samples)
        self._var_detail_stats.set(
            f"N={stats['n']} · median={_format_duration(stats['median'])} · "
            f"P95={_format_duration(stats['p95'])} · max={_format_duration(stats['max'])}"
        )
        self._render_sparkline(samples[-_SPARKLINE_BUCKETS:])

    def _render_sparkline(self, samples: list[float]) -> None:
        self._canvas.delete("all")
        if not samples:
            return
        # Bakgrunn
        w = self._canvas.winfo_width() or 300
        h = self._canvas.winfo_height() or 120
        pad = 8
        usable_w = max(20, w - 2 * pad)
        usable_h = max(20, h - 2 * pad)

        max_val = max(samples)
        min_val = min(samples)
        span = max_val - min_val if max_val > min_val else 1.0

        n = len(samples)
        points: list[tuple[float, float]] = []
        for i, v in enumerate(samples):
            x = pad + (i / max(1, n - 1)) * usable_w
            y = pad + (1 - (v - min_val) / span) * usable_h
            points.append((x, y))

        # Linje
        if len(points) > 1:
            flat = [coord for xy in points for coord in xy]
            self._canvas.create_line(*flat, fill="#2F6FED", width=2, smooth=False)
        # Punkter
        for x, y in points:
            self._canvas.create_oval(x - 2, y - 2, x + 2, y + 2,
                                     fill="#2F6FED", outline="#2F6FED")
        # Min/max labels
        self._canvas.create_text(pad, pad, text=_format_duration(max_val),
                                 anchor="nw", fill="#6B7280", font=("Segoe UI", 8))
        self._canvas.create_text(pad, h - pad, text=_format_duration(min_val),
                                 anchor="sw", fill="#6B7280", font=("Segoe UI", 8))

    # ------------------------------------------------------------------
    # Handlinger

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self._btn_pause.configure(text="▶ Fortsett" if self._paused else "⏸ Pause")
        self._set_status()

    def _clear_view(self) -> None:
        self._events.clear()
        self._tree.delete(*self._tree.get_children())
        self._refresh_detail()
        self._set_status()

    def _sort_by(self, col: str) -> None:
        # Enkel sortering av gjeldende visning. Nytt sortering-flagg.
        rows: list[tuple[Any, str]] = []
        for iid in self._tree.get_children():
            values = self._tree.item(iid, "values")
            # Sort-nøkkel avhenger av kolonne
            if col == "varighet":
                raw = values[3]
                key: Any = _parse_duration(raw)
            elif col == "tid":
                key = values[0]
            elif col == "area":
                key = values[1]
            else:  # "op"
                key = values[2]
            rows.append((key, iid))

        reverse = getattr(self, f"_sort_reverse_{col}", False)
        rows.sort(key=lambda r: r[0], reverse=reverse)
        setattr(self, f"_sort_reverse_{col}", not reverse)

        for index, (_, iid) in enumerate(rows):
            self._tree.move(iid, "", index)

    def _set_status(self) -> None:
        n = len(self._events)
        paused = " · PAUSET" if self._paused else ""
        self._var_status.set(f"events.jsonl · {n} samples i buffer{paused}")


# ---------------------------------------------------------------------------
# Hjelpefunksjoner

def _format_meta(meta: dict) -> str:
    if not meta:
        return ""
    parts = [f"{k}={v}" for k, v in meta.items()]
    return " ".join(parts)


def _parse_duration(text: str) -> float:
    """Parser varighet-streng tilbake til millisekunder for sortering."""
    text = str(text or "").strip()
    try:
        if text.endswith("µs"):
            return float(text[:-2]) / 1000.0
        if text.endswith("ms"):
            return float(text[:-2])
        if text.endswith("s"):
            return float(text[:-1]) * 1000.0
        return float(text)
    except (ValueError, AttributeError):
        return 0.0


def _compute_stats(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"n": 0, "median": 0.0, "p95": 0.0, "max": 0.0}
    s = sorted(samples)
    n = len(s)
    p95_idx = max(0, int(0.95 * n) - 1) if n > 1 else 0
    return {
        "n": n,
        "median": float(statistics.median(s)),
        "p95": float(s[p95_idx]) if n else 0.0,
        "max": float(s[-1]),
    }


def main() -> None:
    app = MonitoringDashboard()
    app.mainloop()


if __name__ == "__main__":
    main()


class MonitoringDashboard(MonitoringDashboardMixin, tk.Tk):
    """Standalone dashboard-vindu (python -m src.monitoring.dashboard)."""

    def __init__(self, events_path: Optional[Path] = None) -> None:
        super().__init__()
        self.title("Utvalg Monitor")
        self.geometry("1100x600")
        self.minsize(760, 400)
        self._init_dashboard(events_path)


class MonitoringPopup(MonitoringDashboardMixin, tk.Toplevel):
    """Dashboard som Toplevel — f.eks. åpnet fra Admin-fanen.

    Samme GUI som standalone-varianten, bare wrappet i Toplevel så den
    lever inne i hovedappens event-loop.
    """

    def __init__(self, master: tk.Misc, events_path: Optional[Path] = None) -> None:
        super().__init__(master)
        self.title("Utvalg Monitor")
        self.geometry("1100x600")
        self.minsize(760, 400)
        self._init_dashboard(events_path)
        try:
            self.transient(master.winfo_toplevel())
        except Exception:
            pass


def open_as_popup(master: tk.Misc, events_path: Optional[Path] = None) -> MonitoringPopup:
    """Åpne monitoring-dashboard som popup inne i hovedappen.

    Trygt å kalle flere ganger — hvis det allerede finnes en åpen popup
    løftes den frem i stedet for å lage en ny.
    """
    existing = getattr(master, "_monitoring_popup", None)
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_set()
                return existing
        except Exception:
            pass
    popup = MonitoringPopup(master, events_path)
    try:
        master._monitoring_popup = popup  # type: ignore[attr-defined]
    except Exception:
        pass
    return popup
