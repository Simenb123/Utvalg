# Cross-feature Interaction Grammar

Felles interaksjonsregler for alle arbeidsflater i Utvalg: Analyse, A07, Konsolidering og Reskontro.
Dette dokumentet er normativt — nye features skal følge disse mønstrene med mindre det finnes en dokumentert grunn til avvik.

## 1. Arbeidsflatestruktur

Alle store arbeidsflater følger samme soneinndeling:

```
┌─────────────────────────────────────────────────────────┐
│  Toolbar: modus, filtre, handlinger                     │
├──────────────────────┬──────────────────────────────────┤
│                      │                                  │
│  Venstre liste       │  Høyre liste / detalj            │
│  (primærvalg)        │  (sekundærvalg / drill)          │
│                      │                                  │
├──────────────────────┴──────────────────────────────────┤
│  Statuslinje: kontekst, antall, advarsler               │
└─────────────────────────────────────────────────────────┘
```

### Regler
- **Venstre liste** er alltid primærnivå (regnskapslinjer, A07-koder, selskaper, motparter).
- **Høyre liste** viser detaljer for valgt element i venstre (kontoer, transaksjoner, bilag).
- **Toolbar** ligger over begge lister. Aldri mer enn to rader.
- **Statuslinje** nederst viser kontekst (klient/år), antall rader, og eventuelle advarsler.
- Alle soner bruker `pack(fill="both", expand=True)` eller `grid` med `weight` for at layouten skalerer.
- Ingen fast bredde/høyde — alt er responsivt.

### Feature-spesifikk mapping

| Feature        | Venstre liste           | Høyre liste              |
|----------------|-------------------------|--------------------------|
| Analyse/RL     | Regnskapslinjer (pivot) | SB-kontoer + transaksjoner |
| Analyse/Konto  | Kontopivot              | Transaksjoner            |
| Analyse/MVA    | MVA-koder (pivot)       | Transaksjoner            |
| A07            | A07-koder               | GL-kontoer + mapping     |
| Konsolidering  | Selskaper + konsernlinjer | Elimineringer + review  |
| Reskontro      | Motparter               | Transaksjoner for motpart |


## 2. TB-only og redusert modus

Mange revisjonsoppdrag starter med kun saldobalanse (TB) før full hovedbok/SAF-T er tilgjengelig.
Alle features skal håndtere dette tydelig.

### Datanivåer

| Nivå          | Data tilgjengelig                        | Typisk kilde         |
|---------------|------------------------------------------|----------------------|
| TB-only       | Kontonr, kontonavn, IB, UB, netto        | Excel, CSV, SAF-T TB |
| Hovedbok      | TB + transaksjoner med dato, bilag, beløp | SAF-T GL             |
| Berika        | HB + MVA-koder, motpart-ID, dimensjoner  | Fullt SAF-T-uttrekk  |

### Feature-tilgjengelighet per nivå

| Feature          | TB-only                              | Hovedbok                    | Berika        |
|------------------|--------------------------------------|-----------------------------|---------------|
| Analyse/RL       | Pivot med IB/UB/netto, ingen drill   | Full pivot + transaksjoner  | + MVA-filter  |
| Analyse/Konto    | Kontoer med saldo, ingen drill       | Full pivot + transaksjoner  | + MVA-filter  |
| Analyse/MVA      | Ikke tilgjengelig                    | MVA-pivot fra HB            | Full flyt     |
| A07              | Mapping med TB-tall                  | + avstemming mot GL         | Full flyt     |
| Konsolidering    | Full MVP-flyt (TB er nok)            | Full MVP-flyt               | Full MVP-flyt |
| Reskontro        | Ikke tilgjengelig                    | Motpartsoversikt fra HB     | Full flyt     |

### GUI-regler for TB-only
- **Aldri skjul features som ikke er tilgjengelige.** Vis dem som disabled med forklaring.
- Toolbar-elementer som krever HB: `state="disabled"` + tooltip "Krever hovedboksdata".
- Drill-knapper som krever transaksjoner: disabled med muted tekst.
- Statuslinje skal vise datanivå: "TB-only — kun saldobalanse lastet" (Warning-style) eller "Hovedbok — fullt datasett" (Ready-style).
- Treeview-kolonner som kun er meningsfulle med HB (f.eks. "Antall transaksjoner") skal skjules i TB-only, ikke vises tomme.

### Implementasjonsmønster
```python
def _has_transactions() -> bool:
    """Sjekk om datasett inneholder transaksjoner (ikke bare TB)."""
    df, cols = session.get_dataset()
    return df is not None and cols is not None and len(df) > 0

def _update_tb_only_state(page) -> None:
    """Oppdater enabled/disabled-state basert på datanivå."""
    has_hb = _has_transactions()
    for widget in page._hb_required_widgets:
        widget.configure(state="normal" if has_hb else "disabled")
    level = "Hovedbok" if has_hb else "TB-only"
    page._data_level_var.set(level)
```


## 2. Valg og navigasjon

### Treeview-valg
- `<<TreeviewSelect>>` er eneste trigger for detalj-refresh. Aldri bruk timer eller polling.
- Etter programmatisk `selection_set()`, kall alltid `focus()` og `see()` for synlighet.
- Multi-select er tillatt i høyre liste (kontoer, transaksjoner). Venstre liste er normalt enkeltvalg.

```python
# Kanonisk mønster for programmatisk valg
tree.selection_set(item_id)
tree.focus(item_id)
tree.see(item_id)
```

### Tastatur

| Tast          | Kontekst           | Handling                                    |
|---------------|--------------------|--------------------------------------------|
| `Enter`       | Treeview           | Drill ned / åpne detalj                    |
| `Escape`      | Dialog             | Lukk uten å lagre                          |
| `Delete`      | Valgt element      | Slett / fjern markering                    |
| `Ctrl+A`      | Treeview           | Velg alle                                  |
| `Ctrl+C`      | Treeview           | Kopier valgte rader som TSV til clipboard  |
| `Double-click`| Treeview-rad       | Åpne editor / drill ned                   |
| `F2`          | Valgt rad          | Inline-redigering (der tilgjengelig)       |

**Alle bindings skal returnere `"break"` for å forhindre default-oppførsel.**

```python
tree.bind("<Control-a>", lambda _e: (_select_all(tree), "break")[-1])
```

### Navigasjonsflyt
- Klikk i venstre liste → høyre liste oppdateres.
- Dobbeltklikk i høyre liste → drill til neste nivå (bilag, transaksjonsdetalj).
- Tilbake-navigasjon: bruk Escape eller en eksplisitt "Tilbake"-knapp øverst i detaljpanelet.


## 3. Drag-and-drop

Implementasjonen bruker ren tkinter uten DND-biblioteker.

### Tilstandsmaskin

```
IDLE → [ButtonPress-1] → PRESSING → [Motion > 8px] → DRAGGING → [ButtonRelease-1] → DROP
                              ↓                                          ↓
                         [ButtonRelease-1                          [Utfør handling
                          uten bevegelse]                           + refresh]
                              ↓
                           IDLE (normalt klikk)
```

### Regler
- **Terskel**: 8 piksler bevegelse før drag aktiveres. Aldri tidsbasert delay.
- **Visuell feedback**: Cursor endres til `"hand2"`. Tooltip (Toplevel med `overrideredirect`) følger musen med 16px x-offset og 8px y-offset.
- **Tooltip**: Opprett én gang ved drag-start. Oppdater posisjon og tekst med `wm_geometry()` og `configure(text=...)`. Aldri destroy+recreate per motion-event.
- **Highlight**: Målelement i venstre liste får midlertidig visuell markering (tag eller selection). Fjernes ved forlating.
- **Multi-drag**: Alle valgte elementer i høyre liste dras som én enhet. Tooltip viser antall ("Flytt 3 kontoer").
- **Drop-validering**: Drop-mål må være et gyldig element i venstre liste. Drop på ugyldig mål (tom plass, seg selv) avbryter uten handling.
- **Etter drop**: Refresh begge lister. Behold valg på kildeelementet (venstre liste) med mindre det er tomt — da gå til målelementet.

### Tilstandsstruktur
```python
drag: dict[str, Any] = {
    "pressing": False,
    "active": False,
    "origin_x": 0,
    "origin_y": 0,
    "payload": [],          # IDs/data som flyttes
    "tip_window": None,
    "tip_label": None,
    "highlighted": None,    # Nåværende mål-highlight
    "source_id": None,      # Kilde-element i venstre liste
}
```


## 4. Høyreklikk / kontekstmeny

### Kanonisk mønster
```python
def _on_right_click(event):
    iid = tree.identify_row(event.y)
    if not iid:
        return

    # Bevar eksisterende multi-select
    if iid not in tree.selection():
        tree.selection_set(iid)
        tree.focus(iid)

    menu = tk.Menu(tree, tearoff=0)
    # ... fyll meny basert på kontekst ...
    menu.tk_popup(event.x_root, event.y_root)
    try:
        menu.grab_release()
    except Exception:
        pass
```

### Regler
- Klikk på et allerede valgt element skal **aldri** endre seleksjonen.
- Menyinnhold tilpasses antall valgte: "Flytt konto..." vs "Flytt 3 kontoer...".
- Separator mellom primærhandlinger (flytt, drill) og sekundærhandlinger (kommentar, kopier).
- Meny lages fersk hver gang (ikke gjenbrukt). `tearoff=0` alltid.


## 5. Dialoger og popups

### Kategorier

| Kategori     | Modal? | Når tillatt                                  |
|--------------|--------|----------------------------------------------|
| Filvelger    | Ja     | Import av filer, eksport                     |
| Editor       | Ja     | Redigere enkeltelementer (kommentar, postering) |
| Bekreftelse  | Ja     | Destruktive handlinger (slett, overskriv)    |
| Admin        | Nei    | Oppsett, konfigurasjon, avanserte verktøy    |
| Progress     | Nei    | Langvarige operasjoner                       |

### Regler
- **Popup er aldri normalflyt.** Alt som gjøres ofte (velg, drill, filtrer, dra) skal skje inline.
- **Modal dialog**: `Toplevel` + `transient(parent)` + `grab_set()`.
- **Sentrering**: Beregn posisjon relativt til forelder, ikke absolutt skjermposisjon.
- **Escape lukker**: Alle dialoger binder `<Escape>` til lukking.
- **Størrelse**: `minsize()` for å unngå for små vinduer. Aldri faste pixelstørrelser som eneste constraint.

```python
# Kanonisk dialog-oppsett
dlg = tk.Toplevel(parent)
dlg.title(title)
dlg.transient(parent)
dlg.grab_set()
dlg.minsize(400, 300)
dlg.bind("<Escape>", lambda _: dlg.destroy())

# Sentrering
dlg.update_idletasks()
w, h = dlg.winfo_width(), dlg.winfo_height()
x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
dlg.geometry(f"+{x}+{y}")
```


## 6. Inline status og advarsler

### Tre nivåer

| Nivå     | Style              | Farge                    | Bruk                           |
|----------|--------------------|--------------------------|---------------------------------|
| Info     | `Status.TLabel`    | Grå (#667085)            | Kontekst, antall, modus        |
| Klar     | `Ready.TLabel`     | Grønn bg (#E2F1EB)      | Alt ok, klar til neste steg    |
| Advarsel | `Warning.TLabel`   | Oransje bg (#FCEBD9)    | Mangler, avvik, krever oppmerksomhet |

### Regler
- Statuslinje nederst i arbeidsflaten. Aldri i popup.
- Oppdateres via `StringVar` + `configure(style=...)`, ikke via destroy/recreate.
- Advarsler forsvinner automatisk når tilstanden er løst (ikke manuell dismiss).
- Aldri bruk rød bakgrunn for statuslinje — rød er reservert for feil i data (se treeview-tags).


## 7. Treeview-tags og farger

### Felles fargekatalog

| Tag               | Bakgrunn   | Forgrunn   | Bruk                              |
|--------------------|-----------|------------|-----------------------------------|
| `sumline`          | #EDF1F5   | fg         | Sumrader, seksjonsoverskrifter    |
| `sumline_major`    | #E0E4EA   | fg, bold   | Hovedsummer (resultat, balanse)   |
| `neg`              | —         | #C0392B    | Negative beløp                    |
| `expected`         | #C6EFCE   | —          | Forventet / godkjent match        |
| `outlier`          | #FFF2CC   | —          | Avviker, trenger oppmerksomhet    |
| `avvik`            | —         | #C0392B    | Tall med avvik (rød tekst)        |
| `review`           | #FCEBD9   | #9F5B2E    | Trenger manuell gjennomgang       |
| `done`             | #E2F1EB   | #256D5A    | Fullført / godkjent               |
| `manual`           | #FCE4D6   | #7B4A1E    | Manuelt overstyrt                 |
| `muted`            | —         | #667085    | Mindre viktig, informativ         |

### Regler
- Tags settes ved `insert()`, ikke i etterkant (unngå dobbeltoppdatering).
- `tag_configure()` kalles én gang ved oppstart av treeview, med `try/except` rundt for tema-kompatibilitet.
- Aldri bland bakgrunnsfarge og forgrunnsfarge i samme tag — velg én retning.
- Beløpsformatering: Negative tall i rødt (`neg`-tag), positive i standard forgrunn.


## 8. Tooltip

### Regler
- Tooltips brukes kun for drag-feedback og for ikoner/knapper der plassbegrensning gjør label umulig.
- Aldri hover-tooltip på treeview-rader (for tregt, for støyende).
- Implementasjon: `Toplevel` med `overrideredirect(True)` + `wm_attributes("-topmost", True)`.
- Bakgrunn: `#FFFDE7` (lys gul), forgrunn: `#333333`, padding 6x3, border `solid` 1px.
- Posisjon: +16px x, +8px y fra musepeker.
- Levetid: opprett ved behov, oppdater posisjon via `wm_geometry`, destroy ved avslutning.


## 9. Kommentarer og markører

### Visuell markering
- Elementer med kommentar vises med `✎`-prefiks foran navnet.
- Kommentarer redigeres via høyreklikk → "Kommentar...".
- Kommentarer lagres per klient via `regnskap_client_overrides`.
- Kommentarer påvirker aldri beregninger — de er kun informative.

### Regler
- Kommentar-dialog er modal (editor-kategori).
- Tomt kommentarfelt = fjern kommentar.
- `✎` vises i tekst-kolonnen, ikke som egen kolonne.


## 10. Performance

### Regler
- **Aldri refresh hele treeview hvis bare detaljer endret seg.** Bruk `tree.item(iid, values=...)` for oppdatering av enkeltrad.
- **Lazy-load detaljer**: Høyre liste fylles først når et element i venstre liste er valgt.
- **Batch insert**: Bruk `tree.insert()` i løkke uten `update_idletasks()` mellom. Kall `update_idletasks()` én gang etter løkken.
- **Deaktiver sortering under bulk-insert**: Sett `tree["displaycolumns"]` til tom liste under insert, gjennopprett etterpå (unngår N*log(N) re-sort).
- **Pandas**: Bruk vektoriserte operasjoner. Aldri iterér rad-for-rad over DataFrame i Python-løkker for aggregering.


## 11. Navngivning

### Knapper og menyer
- Bruk norske verb i imperativ: "Legg til", "Slett", "Eksporter", "Lagre", "Avbryt".
- Aldri "Klikk her" eller "Trykk for å...".
- Handlinger med konsekvens: "Slett valgte (3)" — inkluder antall.
- Sekundære handlinger: "Avansert..." med ellipsis for å signalisere at noe åpnes.

### Statusmeldinger
- Beskriv tilstand, ikke handling: "3 kontoer valgt" (ikke "Du har valgt 3 kontoer").
- Tall formateres med tusenskilletegn: "12 345 transaksjoner".
- Differanser: "Diff: 1 234,56" (rød) eller "Balansert" (grønn).
