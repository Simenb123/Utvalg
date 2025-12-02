# UI-oversikt – Utvalg/Analyse-verktøy

Denne oversikten beskriver de viktigste fanene, knappene og callback-funksjonene i GUI-et.
Formålet er å:

- forstå sammenhengen mellom fanene,
- se hva hver knapp faktisk gjør,
- enklere oppdage “døde” knapper eller gammel funksjonalitet,
- hjelpe ved videre utvikling og testskriving.

---

## 1. Fane: Dataset

**Fil(er):**

- `page_dataset.py` – wrapper rundt `DatasetPane`
- `dataset_pane.py` – hoved-GUI og logikk for innlesing + kolonnemapping

**Formål:**

- Velge fil (SAF-T/hovedbok).
- Mappe kolonner til standardfelter (Konto, Bilag, Beløp, Dato, osv.).
- Bygge `session.dataset` som brukes videre i Analyse/Utvalg.

**Viktige elementer:**

| Element / label                      | Type      | Callback / kode                     | Effekt / kommentar                                                                 |
|-------------------------------------|-----------|-------------------------------------|------------------------------------------------------------------------------------|
| Filsti (Entry)                      | `Entry`   | intern i `DatasetPane`              | Viser valgt filsti.                                                                |
| `Bla...`                            | `Button`  | `DatasetPane._on_browse_clicked`    | Åpner fil-dialog for å velge fil.                                                 |
| `Last inn header`                   | `Button`  | `DatasetPane._on_load_header_clicked` | Leser inn kolonnenavn fra valgt fil.                                           |
| Kolonnemapping (dropdowns per rad)  | `Combobox`| styres i `DatasetPane`              | Velger hvilke kolonner i filen som er Konto, Bilag, Beløp osv.                     |
| `Gjett mapping`                     | `Button`  | `DatasetPane._on_guess_mapping_clicked` | Forsøker å mappe kolonner automatisk basert på navn.                          |
| `Bygg datasett`                     | `Button`  | `DatasetPane._on_build_dataset_clicked` | Leser filen, bygger `session.dataset`, viser antall rader/kolonner.         |
| Statuslinje (f.eks. `Dataset bygget: rader=...`) | `Label` | oppdateres internt                 | Bekrefter at dataset er bygget, og hvor stort det er.                               |

**Planlagt flyt:**

- Etter “Bygg datasett” er det naturlig at appen automatisk bytter til **Analyse**-fanen.
- Dette kan implementeres ved at `_on_build_dataset_clicked` etter vellykket bygg kaller en callback
  (f.eks. `on_dataset_built()`) som igjen gjør `session.NOTEBOOK.select(session.ANALYSE_TAB_ID)`.

---

## 2. Fane: Analyse

**Fil(er):**

- `page_analyse.py` – GUI og logikk for pivot pr. konto og transaksjonsliste
- `page_analyse_hook.py` – eventuelle integrasjonshooks
- `analysis_pkg.py` m.fl. – analysefunksjoner i bakgrunnen

**Formål:**

- Gi et aggregert blikk på hovedboken (pivot pr. konto).
- Velge kontopopulasjon (en eller flere kontoer) for videre testing.
- Sende valgte kontoer til Utvalg (stratifisering).

**Viktige elementer (toppfilter):**

| Element / label             | Type       | Callback / kode                         | Effekt / kommentar                                        |
|-----------------------------|------------|-----------------------------------------|-----------------------------------------------------------|
| Søk (tekstfelt)             | `Entry`    | `AnalysePage._on_search_changed`        | Filtrerer pivot/transaksjoner på tekst/kontonavn.        |
| `Retning`                   | `Combobox` | `AnalysePage._on_filters_changed`       | Filtrerer på Debet/Kredit/Alle i transaksjonslisten.     |
| `Kontoserier` (1–9)         | `Checkbutton` | `AnalysePage._on_filters_changed`    | Filtrerer på kontonummerets første siffer.               |
| `Vis` (antall)              | `Combobox`/`Spinbox` | `AnalysePage._on_filters_changed` | Antall kontoer/linjer som vises i pivoten.               |
| `Nulstill`                  | `Button`   | `AnalysePage._on_reset_filters`         | Nullstiller alle filtre.                                  |
| `Bruk filtre`               | `Button`   | `AnalysePage._apply_filters`            | Trigger filtrering på høyresiden basert på feltene over. |
| `Marker alle`               | `Button`   | `AnalysePage._on_mark_all_clicked`      | Marker alle kontoene i pivot-listen.                      |
| `Til utvalg`                | `Button`   | `AnalysePage._send_to_selection`        | Samler markerte kontoer og kaller `bus.emit("SELECTION_SET_ACCOUNTS", {"accounts": accounts})`. |
| `Pinned kolonner`           | `Button`   | `AnalysePage._open_column_chooser`      | Åpner dialog for å velge faste kolonner i transaksjonstabell. |

**Viktige elementer (midten):**

| Element / label      | Type        | Callback / kode                       | Effekt                                           |
|----------------------|-------------|---------------------------------------|--------------------------------------------------|
| Pivot pr. konto      | `Treeview`  | dbl-klik: `AnalysePage._on_pivot_dblclick` | Viser kontoer med sum/antall; dobbeltklikk viser transaksjoner til høyre. |
| Transaksjonsliste    | `Treeview`  | (evt. dbl-klik på bilag)             | Viser underliggende transaksjoner for markerte kontoer.                   |

**Flyt mot Utvalg:**

1. Bruker markerer én eller flere kontoer i pivot-listen.
2. Klikker `Til utvalg`.
3. `_send_to_selection` samler kontonumre (`accounts`), setter `session.SELECTION` og kaller:

   ```python
   from bus import emit
   emit("SELECTION_SET_ACCOUNTS", {"accounts": accounts})
