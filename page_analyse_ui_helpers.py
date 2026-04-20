"""page_analyse_ui_helpers.py

Rene hjelpere utskilt fra page_analyse_ui.py:
* _safe_period_value — parser månedsverdi (1-12) eller None.
* _build_period_range_picker — tkinter Canvas-basert periodevelger.
* _nk_fetch_brreg — BRREG regnskap-henting + re-render for nøkkeltallvisning.
"""

from __future__ import annotations

from typing import Any


def _safe_period_value(raw: object) -> int | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = int(text)
    except Exception:
        return None
    if 1 <= value <= 12:
        return value
    return None


def _build_period_range_picker(
    master: Any,
    *,
    tk: Any,
    ttk: Any,
    var_date_from: Any,
    var_date_to: Any,
) -> tuple[Any | None, Any | None]:
    canvas_cls = getattr(tk, "Canvas", None)
    if canvas_cls is None:
        return None, None

    outer = ttk.Frame(master)
    ttk.Label(outer, text="Periode:").pack(side="left")

    canvas_width = 380
    canvas_height = 52

    canvas = canvas_cls(
        outer,
        width=canvas_width,
        height=canvas_height,
        highlightthickness=0,
        bd=0,
        relief="flat",
        background="#FFFFFF",
    )
    canvas.pack(side="left", padx=(8, 10))

    btn_reset = ttk.Button(
        outer,
        text="Hele året",
        command=lambda: _set_range(None, None),
    )
    btn_reset.pack(side="left")

    left_pad = 18
    right_pad = 18
    base_y = 24
    marker_r = 5

    def _month_x(month: int) -> float:
        usable = canvas_width - left_pad - right_pad
        if usable <= 0:
            return float(left_pad)
        return float(left_pad + ((month - 1) / 11.0) * usable)

    def _current_range() -> tuple[int | None, int | None]:
        from_value = _safe_period_value(getattr(var_date_from, "get", lambda: "")())
        to_value = _safe_period_value(getattr(var_date_to, "get", lambda: "")())
        if from_value is None or to_value is None:
            return (None, None)
        if from_value <= to_value:
            return (from_value, to_value)
        return (to_value, from_value)

    def _set_range(from_value: int | None, to_value: int | None) -> None:
        try:
            var_date_from.set("" if from_value is None else str(int(from_value)))
            var_date_to.set("" if to_value is None else str(int(to_value)))
        except Exception:
            return
        _redraw()

    def _closest_month(x_value: float) -> int:
        positions = [(month, abs(x_value - _month_x(month))) for month in range(1, 13)]
        return min(positions, key=lambda item: item[1])[0]

    def _on_click(event) -> str:  # noqa: ANN001
        month = _closest_month(float(getattr(event, "x", 0)))
        from_value, to_value = _current_range()
        if from_value is None or to_value is None:
            _set_range(month, month)
            return "break"
        if abs(month - from_value) <= abs(month - to_value):
            from_value = month
        else:
            to_value = month
        if from_value > to_value:
            from_value, to_value = to_value, from_value
        _set_range(from_value, to_value)
        return "break"

    def _on_double_click(_event=None) -> str:
        _set_range(None, None)
        return "break"

    def _redraw() -> None:
        try:
            canvas.delete("all")
        except Exception:
            return

        from_value, to_value = _current_range()
        line_start = _month_x(1)
        line_end = _month_x(12)

        canvas.create_line(line_start, base_y, line_end, base_y, fill="#7A869A", width=2)

        if from_value is not None and to_value is not None:
            canvas.create_line(
                _month_x(from_value),
                base_y,
                _month_x(to_value),
                base_y,
                fill="#2F6FED",
                width=6,
                capstyle="round",
            )

        for month in range(1, 13):
            x = _month_x(month)
            canvas.create_line(x, base_y - 8, x, base_y + 8, fill="#4C6A91", width=1)
            if from_value is None or to_value is None:
                fill = "#FFFFFF"
                outline = "#4C6A91"
            elif from_value <= month <= to_value:
                fill = "#FFF59D" if month not in {from_value, to_value} else "#2F6FED"
                outline = "#2F6FED"
            else:
                fill = "#FFFFFF"
                outline = "#4C6A91"
            canvas.create_oval(
                x - marker_r,
                base_y - marker_r,
                x + marker_r,
                base_y + marker_r,
                fill=fill,
                outline=outline,
                width=2 if month in {from_value, to_value} else 1,
            )
            canvas.create_text(x, base_y + 16, text=str(month), fill="#42526E")

        status_text = "Hele året" if from_value is None or to_value is None else f"{from_value}-{to_value}"
        canvas.create_text(line_end, 8, text=status_text, anchor="e", fill="#2F6FED")

    try:
        canvas.bind("<Button-1>", _on_click)
        canvas.bind("<Double-1>", _on_double_click)
    except Exception:
        pass

    try:
        var_date_from.trace_add("write", lambda *_: _redraw())
        var_date_to.trace_add("write", lambda *_: _redraw())
    except Exception:
        pass

    _redraw()
    return outer, canvas


def _nk_fetch_brreg(page: Any) -> None:
    """Hent BRREG-tall for aktiv klient og oppdater nøkkeltallvisningen."""
    import tkinter.messagebox as _mb
    import threading

    # Finn orgnr: (1) session.meta, (2) client_store.read_client_meta, (3) manuell prompt
    orgnr = ""
    try:
        import session as _sess
        meta = getattr(_sess, "meta", None)
        if isinstance(meta, dict):
            orgnr = (meta.get("org_number") or "").strip().replace(" ", "")
    except Exception:
        _sess = None

    if not orgnr or len(orgnr) != 9:
        try:
            import client_store as _cs
            client_name = getattr(_sess, "client", "") if _sess is not None else ""
            if client_name:
                cmeta = _cs.read_client_meta(client_name)
                if isinstance(cmeta, dict):
                    orgnr = (cmeta.get("org_number") or "").strip().replace(" ", "")
        except Exception:
            pass

    if not orgnr or len(orgnr) != 9:
        # Be bruker om å oppgi orgnr manuelt
        try:
            import tkinter.simpledialog as _sd
            orgnr = _sd.askstring(
                "Org.nr",
                "Skriv inn organisasjonsnummer (9 siffer):",
                parent=page,
            )
        except Exception:
            return
        if not orgnr:
            return
        orgnr = orgnr.strip().replace(" ", "")
        if len(orgnr) != 9 or not orgnr.isdigit():
            _mb.showwarning("Ugyldig org.nr", f"'{orgnr}' er ikke et gyldig 9-sifret organisasjonsnummer.")
            return

    label = getattr(page, "_nk_brreg_label", None)
    btn = getattr(page, "_nk_brreg_btn", None)
    if label:
        label.configure(text=f"Henter fra BRREG ({orgnr})…")
    if btn:
        btn.configure(state="disabled")

    def _worker():
        try:
            import brreg_client
            data = brreg_client.fetch_regnskap(orgnr)
        except Exception as exc:
            page.after(0, lambda: _on_done(None, str(exc)))
            return
        page.after(0, lambda: _on_done(data, None))

    def _on_done(data, error):
        if btn:
            btn.configure(state="normal")
        if error:
            if label:
                label.configure(text="Feil ved BRREG-henting")
            _mb.showerror("BRREG-feil", f"Kunne ikke hente regnskapsdata:\n{error}")
            return
        if data is None:
            if label:
                label.configure(text="Ingen regnskap funnet i BRREG")
            _mb.showinfo("BRREG", f"Ingen innlevert regnskap funnet for org.nr {orgnr}.")
            return

        page._nk_brreg_data = data
        brreg_year = data.get("regnskapsaar", "?")
        if label:
            label.configure(text=f"BRREG {brreg_year} hentet")

        # Re-render nøkkeltall med BRREG-sammenligning
        try:
            page._refresh_nokkeltall_view()
        except Exception:
            pass

        # Vis BRREG-kolonner i RL-pivot og re-render
        try:
            import page_analyse_columns as _pac
            _pac.update_pivot_columns_for_brreg(page=page)
        except Exception:
            pass
        try:
            import page_analyse_rl as _prl
            _prl.refresh_rl_pivot(page=page)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def _nk_auto_fetch_brreg(page: Any) -> None:
    """Silent auto-fetch av BRREG når klient åpnes.

    Ulikt _nk_fetch_brreg: ingen prompt ved manglende orgnr, ingen
    popups ved feil. Bruker eksisterende 24t disk-cache fra brreg_client,
    så det er ofte cache-hit og raskt.
    """
    import threading

    orgnr = ""
    try:
        import session as _sess
        meta = getattr(_sess, "meta", None)
        if isinstance(meta, dict):
            orgnr = (meta.get("org_number") or "").strip().replace(" ", "")
    except Exception:
        _sess = None

    if not orgnr or len(orgnr) != 9:
        try:
            import client_store as _cs
            client_name = getattr(_sess, "client", "") if _sess is not None else ""
            if client_name:
                cmeta = _cs.read_client_meta(client_name)
                if isinstance(cmeta, dict):
                    orgnr = (cmeta.get("org_number") or "").strip().replace(" ", "")
        except Exception:
            pass

    if not orgnr or len(orgnr) != 9 or not orgnr.isdigit():
        return

    def _worker():
        try:
            import brreg_client
            data = brreg_client.fetch_regnskap(orgnr)
        except Exception:
            return
        if data is None:
            return
        page.after(0, lambda: _on_done(data))

    def _on_done(data):
        page._nk_brreg_data = data
        label = getattr(page, "_nk_brreg_label", None)
        brreg_year = data.get("regnskapsaar", "?")
        if label:
            try:
                label.configure(text=f"BRREG {brreg_year} hentet")
            except Exception:
                pass
        try:
            page._refresh_nokkeltall_view()
        except Exception:
            pass
        try:
            import page_analyse_columns as _pac
            _pac.update_pivot_columns_for_brreg(page=page)
        except Exception:
            pass
        try:
            import page_analyse_rl as _prl
            _prl.refresh_rl_pivot(page=page)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()
