# Design system — Utvalg / AarVaaken

Dette dokumentet beskriver det visuelle språket i appen, hvordan farger og
komponenter brukes, og hva som er retningslinjene for ny UI-kode.

**Single source of truth:** [src/shared/ui/tokens.py](../../src/shared/ui/tokens.py)

---

## 1. Designprinsipper

Appen er et **revisjonsverktøy som brukes 8 timer/dag**. Det styrer alle
designbeslutninger:

1. **Lesbarhet før estetikk.** Tabeller med tall må være lette å skanne —
   det betyr lys nøytral bakgrunn og høy kontrast i data-celler.
2. **Visuell sammenheng med Vaak/AarVaaken-merket.** Logo-fargene gjenkjennes
   i tabs, banner og aktive elementer — ikke som dominerende bakgrunn.
3. **Tkinter-realisme.** Vi forsøker IKKE å matche vaak.no pixel-presist —
   Tkinter har begrensninger (ingen runde hjørner, ingen myke skygger,
   begrenset typografi). Vi sikter på funksjonell skjønnhet, ikke web-imitasjon.
4. **Audit-bærekraft.** Subtile fargemarkeringer (rødt minus, grønt OK,
   gult advarsel) må fungere visuelt på enhver bakgrunn.

---

## 2. Fargesystem

### 2.1 Hovedpalett (bakgrunn)

| Token | Hex | Bruk |
|---|---|---|
| `BG_SAND` | `#D2BD9C` | Tabs, hovedbanner, aktive flater. Eksakt match til AarVaaken-logoens banner. |
| `BG_SAND_SOFT` | `#E5D5B8` | Paneler, kort, dialog-bakgrunner. Mellomtone. |
| `BG_NEUTRAL` | `#F3ECDC` | **Hovedbakgrunn på alle sider.** Lys cream — favoriserer tabell-lesbarhet uten å være pure hvit. |
| `BG_DATA` | `#FFFFFF` | Tabellceller, scrollable lister. Maks kontrast for tall. |
| `BG_ZEBRA` | `#F8F2E4` | Alternerende rader i tabeller. Diskret. |

### 2.2 Tekst

| Token | Hex | Bruk |
|---|---|---|
| `TEXT_PRIMARY` | `#3A1900` | Standard tekst. Mørk varm-brun (matcher logo-tekst). |
| `TEXT_MUTED` | `#6B5540` | Sekundær tekst, hjelpetekster, sub-titler. |
| `TEXT_ON_SAND` | `#3A1900` | Tekst på `BG_SAND`. |
| `TEXT_ON_FOREST` | `#FFFFFF` | Hvit tekst på grønne knapper. |

### 2.3 Aksenter / status

| Token | Hex | Bruk |
|---|---|---|
| `FOREST` | `#325B1E` | Primærknapper, aktive piller, "OK"-status. |
| `FOREST_HOVER` | `#24451A` | Hover-state på primærknapper. |
| `SAGE` | `#BDE5AE` | Lys grønn — sekundær aksent. |
| `SAGE_DARK` | `#8CBF7C` | Mørkere variant av SAGE. |
| `SAGE_WASH` | `#EAF2DE` | Veldig lys grønn — "ready"-paneler. |
| `OLIVE` | `#A5B572` | Olivengrønn — neutral aksent. |
| `SELECT_BG` | `#2F5FBA` | Markert rad i Treeview. |

### 2.4 Status-farger

| Token | Hex | Bruk |
|---|---|---|
| `POS_TEXT` / `POS_SOFT` | `#325B1E` / `#E6F3DD` | Positiv (overskudd, OK). |
| `NEG_TEXT` / `NEG_SOFT` | `#8B2A1F` / `#F3DDD7` | Negativ (underskudd, feil). |
| `WARN_TEXT` / `WARN_SOFT` | `#B7791F` / `#F6E5C8` | Advarsel. |
| `POS_TEXT_DARK` | `#2E7D32` | Mørk grønn for tekst på lys bakgrunn (statistikk, pille). |
| `NEG_TEXT_DARK` | `#C62828` | Mørk rød for tekst på lys bakgrunn. |
| `INFO_TEXT` / `INFO_SOFT` | `#1565C0` / `#DBEAFE` | Informativ/manuell — IKKE feil/advarsel. |
| `SAGE_WASH_SOFT` | `#EAF7F0` | Veldig lys grønnaktig wash for chat/info-bakgrunn. |
| `BORDER_LIGHT` | `#D7D1C7` | Nøytral grålig border (skiller seg fra `BORDER` som er tan). |

### 2.5 Rammer / borders

| Token | Hex | Bruk |
|---|---|---|
| `BORDER` | `#C0A580` | Standard rammer (separator, panel-kant). |
| `BORDER_SOFT` | `#DDC9AE` | Subtile delere. |

---

## 3. Tonal hierarki

```
banner-tan      D2BD9C  ████████ Tabs, hovedbanner
soft-tan        E5D5B8  ████░░░░ Paneler
neutral-cream   F3ECDC  ███░░░░░ Hovedbakgrunn (lys nok for tabeller)
zebra-light     F8F2E4  █░░░░░░░ Alternerende rader
white           FFFFFF  ░░░░░░░░ Data-celler
```

Hovedregelen: **jo dypere ned brukeren leter etter detaljer, jo lysere
bakgrunn**.

---

## 3.1 Lint-test som håndhever regelen

Filen [tests/test_no_hardcoded_colors.py](../../tests/test_no_hardcoded_colors.py)
fanger automatisk nye hardkodede `"#XXXXXX"`-strenger:

- **`test_no_hardcoded_colors_outside_allowlist`** — feiler hvis nye filer
  utenfor en kjent allowlist har hardkodede farger. Tvinger ny kode til å
  bruke tokens.
- **`test_total_hardcoded_color_count_does_not_increase`** — total telling
  med BASELINE som tak. Feiler hvis totalen øker.
- **`test_allowlist_entries_actually_exist`** — fanger stale entries i
  allowlist (filer som er slettet/migrert).

**Kjør:**
```bash
pytest tests/test_no_hardcoded_colors.py -v
```

**Når du rydder en fil:**
1. Migrer hardkodede farger til tokens (eller `# design-exception: <grunn>`)
2. Fjern fila fra `_ALLOWLIST` i testen
3. Senk `BASELINE` med antall farger du fjernet

**Per-linje-unntak:** Legg til `# design-exception: <grunn>` på samme linje:
```python
LOGO_BLUE = "#1A4C7A"  # design-exception: ekstern logo må matches eksakt
```

---

## 4. Når man skal bruke tokens vs hardkodet

### Bruk **alltid** tokens når:

- Du setter en bakgrunn på en `ttk.Frame`, `ttk.Label` etc.
- Du tegner en separator
- Du legger til status-farge (rød, grønn, gul)
- Du importerer farge fra `src.shared.ui.tokens`-modulen

```python
import src.shared.ui.tokens as tk_tokens
from src.shared.ui.tokens import hex_gui

frame.configure(background=hex_gui(tk_tokens.BG_NEUTRAL))
```

### Hardkodede farger er **kun** akseptabelt når:

- Det er et **engangs-tilfelle** uten gjenbruksverdi (f.eks. en spesifikk
  kategori-farge i en chart som bare finnes der)
- Det er **dokumentert** med kommentar hvorfor det ikke er token

```python
# Spesialtilfelle: matchende farge til ekstern tjenestelogo
LOGO_BLUE = "#1A4C7A"  # docs: konstant fordi den binder til ekstern brand
```

### Hardkodet er **forbudt** når:

- Det er en standard bakgrunn (skal være `BG_*`)
- Det er en standard tekst-farge (skal være `TEXT_*`)
- Det er en status-indikator (skal være `POS_*`/`NEG_*`/`WARN_*`)

---

## 5. Komponenter

### 5.1 PageHeader

Felles topptittel for alle hovedfaner.

**Plassering:** [src/shared/ui/page_header.py](../../src/shared/ui/page_header.py)

**Migrert til** (per 2026-04-28): Regnskap, Skatt, Utvalg, MVA,
Materiality, AR, Scoping, Reskontro, Analyse, Konsolidering (10/15 hovedfaner).

**Gjenstår:** A07, Dataset, Saldobalanse, Driftsmidler, Konsolidering-sub-tabs.

```python
from src.shared.ui.page_header import PageHeader

header = PageHeader(self, title="Regnskap", subtitle="Klient — År")
header.set_refresh(command=self._on_refresh, key="<F5>")
header.add_export("Excel", command=self._export_xlsx)
header.add_export("PDF",   command=self._export_pdf)

# Side-spesifikke kontroller — knapper, filtre, statuslabels:
ttk.Button(header.center, text="Importer…", command=...).pack(side="left")
```

Standard layout: tittel/sub-tittel venstre · custom-widgets midt · refresh + eksport høyre.
Refresh = ↻-ikon, eksport = ⬇-ikon (logo-grønn). Multi-eksport blir
automatisk en dropdown.

**Når header.center brukes:** Fyll med side-spesifikke kontroller som
hører hjemme i header-rad (filtre, dropdowns, status-labels). Hvis
toolbaren er for stor for én rad, behold den som egen rad UNDER headeren.

**Implementeringsnote:** PageHeader cacher PIL-bildet (root-uavhengig),
men bygger PhotoImage per Tk-rot for å unngå
`image "pyimageN" doesn't exist`-feil i tester som ødelegger og
gjenoppretter Tk-roten.

### 5.2 ManagedTreeview

Standard tabellkomponent med drag-n-drop, kolonneveljer, sortering, persistens.

**Plassering:** [src/shared/ui/managed_treeview.py](../../src/shared/ui/managed_treeview.py)
**Playbook:** [docs/TREEVIEW_PLAYBOOK.md](../../docs/TREEVIEW_PLAYBOOK.md)

### 5.3 Dialoger

Alle nye modale popups skal bruke `make_dialog()`.

**Plassering:** [src/shared/ui/dialog.py](../../src/shared/ui/dialog.py)
**Standard:** [docs/POPUP_STANDARD.md](../../docs/POPUP_STANDARD.md)

```python
from src.shared.ui.dialog import make_dialog

dlg = make_dialog(parent, title="Tittel", width=480, height=320, modal=True)
```

### 5.4 Treeview-sortering

Klikk-på-header-sortering for vanlige Treeviews.

**Plassering:** [src/shared/ui/treeview_sort.py](../../src/shared/ui/treeview_sort.py)

```python
from src.shared.ui.treeview_sort import enable_treeview_sorting

enable_treeview_sorting(tree, columns=("col1", "col2", "col3"))
```

---

## 6. Typografi

```
FONT_FAMILY_DISPLAY = "Segoe UI Variable"  → titler, banner
FONT_FAMILY_BODY    = "Segoe UI"           → standard tekst
FONT_FAMILY_MONO    = "Consolas"           → tabeller, kode

FONT_DISPLAY  = (DISPLAY, 22, bold)        → splash, store overskrifter
FONT_H1       = (DISPLAY, 16, bold)        → side-titler i PageHeader
FONT_H2       = (DISPLAY, 13, bold)        → seksjons-titler
FONT_BODY     = (BODY, 10, normal)         → standard
FONT_BODY_BOLD= (BODY, 10, bold)           → fremhevelse i tekst
FONT_SMALL    = (BODY, 9, normal)          → metadata, hjelpetekster
FONT_MONO     = (MONO, 10, normal)         → tabeller med tall (valgfritt)
```

---

## 7. Tkinter-begrensninger og kompromisser

Disse er **kjente** og vi unngår å kjempe mot dem:

| Effekt | Tkinter-status | Workaround |
|---|---|---|
| Runde hjørner på knapper | Ikke støttet | Bruk Canvas hvis kritisk; ellers aksepter rektangulær |
| Drop shadows | Ikke støttet | Bruk diskrete rammer (`BORDER`) i stedet |
| Hover-overganger | Begrenset | Bruk `style.map(... [("active", ...)])` for state-endringer |
| Variable fonter | Ikke støttet | Bruk `Segoe UI` (Windows) som beste alternativ |
| Subpixel antialiasing | OS-avhengig | Aksepter, ikke prøv å overstyre |

---

## 8. Migrasjons-roadmap

**Status 2026-04-28:** **513 hardkodede hex-farger igjen** (fra 652).
139 farger er enten migrert til tokens eller markert som
`# design-exception:` siden Fase 4 startet.

Gjenstående verstinger:

| Fil | Antall hardkodede farger | Status |
|---|---|---|
| `src/pages/fagchat/page_fagchat.py` | 95 | Lav prio (deaktivert) |
| Diverse dialoger og audit_actions | ~50 filer i allowlist | Migreres on-touch |

**Migrert hittil:**

| Fil | Til tokens | Markert | Dato |
|---|---|---|---|
| `src/pages/scoping/frontend/page.py` | 4 | 32 | 2026-04-28 |
| `src/pages/skatt/page.py` | 5 | 4 | 2026-04-28 |
| `src/audit_actions/statistikk/frontend/page.py` | 13 | 18 | 2026-04-28 |
| `src/pages/ar/frontend/page.py` | 3 | 31 lines | 2026-04-28 |
| `src/pages/ar/frontend/chart.py` | 0 | 19 lines | 2026-04-28 |

**Strategi:**

1. **Ikke en stor migrasjon.** Vi unngår én "rydd opp alle farger"-PR siden
   den blir massiv og høyrisiko.
2. **Migrer når du uansett rører fila.** Hvis du fikser en bug eller legger
   til en feature i `page_X.py`, ta også fargene mens du er der.
3. **Nye hardkodede farger er forbudt.** Bruk tokens. Hvis token mangler,
   legg til ny token i `tokens.py` og dokumenter her.
4. **Lint-test håndhever regelen** — se §3.1.

---

## 9. Når palettverdier endres

Hvis logo-fargene blir oppdatert, eller designeren foreslår en ny tone:

1. Endre verdiene i [tokens.py](../../src/shared/ui/tokens.py) (single
   source of truth)
2. Oppdater dette dokumentet
3. Sjekk at testene fortsatt passerer (`pytest tests/ -k "theme or tokens"`)
4. **Vit at endringen kun når token-baserte steder.** Hardkodede farger må
   migreres separat — eller lev med en ujevn overgang inntil migrering er
   gjort.

---

## 10. Excel-eksport bruker samme tokens

[src/shared/ui/excel_theme.py](../../src/shared/ui/excel_theme.py) leser
tokens og bruker dem i `openpyxl`-baserte Excel-eksporter. Dette gir
visuell konsistens mellom GUI-en og eksportene revisor sender til klient.
Ny tokens som påvirker tabell-celler bør også reflekteres her.
