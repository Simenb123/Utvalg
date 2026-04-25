# Popup-standard — `ui_dialog.make_dialog()`

Alle nye modale popupvinduer skal bruke
[ui_dialog.make_dialog()](../ui_dialog.py) som konstruktør.

Det gir hver dialog:

- Sentrering over forelder (eller skjerm som fallback)
- 720×520 default-størrelse og fornuftig `minsize`
- Standard vinduskontroller (minimer, maksimer, lukk) — ikke bare X
- Modal atferd (`grab_set` + `focus_set`)
- `Escape` lukker dialogen

Dette erstatter mønsteret:

```python
dialog = tk.Toplevel(master)
dialog.title("...")
dialog.transient(master)   # ← ødelegger max/min på Windows
dialog.grab_set()
dialog.minsize(...)
```

## Minimal bruk

```python
from ui_dialog import make_dialog

def open_my_dialog(master):
    dialog = make_dialog(
        master,
        title="Mitt vindu",
        width=720,
        height=520,
    )

    # …legg til innhold med pack/grid…

    dialog.wait_window()
    return getattr(dialog, "result", None)
```

## Parametere

| Parameter | Default | Beskrivelse |
|---|---|---|
| `title` | (påkrevd) | Vindustittel |
| `width`, `height` | `720`, `520` | Start­størrelse |
| `min_width`, `min_height` | ~60 % av start | Minste tillatte størrelse |
| `modal` | `True` | `grab_set` — blokkerer hovedvinduet |
| `resizable` | `True` | `False` låser størrelsen |
| `center_on` | `"parent"` | eller `"screen"` |
| `bind_escape` | `True` | `Escape` lukker dialogen |

## Når du skal IKKE bruke make_dialog

- **Tooltips og mini-popups** (f.eks. drag-ghost, auto-suggest) —
  disse bruker `wm_overrideredirect(True)` og skal ikke ha
  vinduskontroller.
- **Native dialoger** (`filedialog.askopenfilename` etc.) — allerede
  OS-stilt.
- **Menyer** (`tk.Menu`) — bruker eget popup-mønster via `tk_popup()`.

## Migrere en eksisterende dialog

1. Finn prologen — alltid `dialog = tk.Toplevel(master)` + `title` +
   `transient` + `grab_set` + `minsize`.
2. Bytt til ett `make_dialog(...)`-kall. Alle parametere som tidligere
   var hardkodet (størrelse, minsize) sendes inn som keyword-arg.
3. Fjern eventuell egenskrevet sentrerings­kode (`dialog.geometry(...)`
   med manuell utregning av `x, y`).
4. Fjern manuell `<Escape>`-binding hvis den bare kalte `destroy()`.
   Behold hvis den gjør noe mer (f.eks. setter `result = None` før
   destroy).

## Status — hva som bruker standarden

- ✅ [views_column_chooser.py](../views_column_chooser.py)

## Gjenstår (kan migreres gradvis)

Disse bruker fortsatt direkte `tk.Toplevel`:

- `action_link_dialog.py`
- `mva_avstemming_dialog.py`
- `document_control_review_dialog.py`
- `document_control_batch_dialog.py`
- `document_control_voucher_dialog.py`
- `views_konto_klassifisering.py`
- `views_rl_account_drill.py`
- `rl_mapping_drift_dialog.py`
- `consolidation_pdf_review_dialog.py`
- `analyse_sb_remap.py` (flytt-N-kontoer-dialogen)
- Flere i `motpost/`, `reskontro_*`, `selection_studio/`

Ingen hast — migrer når du uansett er inne i filen av andre grunner.
