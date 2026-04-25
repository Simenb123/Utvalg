# Utvalg

## Lønn og klassifisering

- [`a07_payroll/STATUS_AND_GOAL.md`](a07_payroll/STATUS_AND_GOAL.md) - samlet status, formal og arbeidsretning for A07/A-melding, RF-1022 og trygg matching.
- [`SALDOBALANSE_LONN_ARBEIDSFLYT.md`](SALDOBALANSE_LONN_ARBEIDSFLYT.md) - daglig arbeidsflyt i `Saldobalanse` for A07, RF-1022 og læring.
- [`KLASSIFISERINGSFELTER_LONN.md`](KLASSIFISERINGSFELTER_LONN.md) - forklaring av felter, forslag, historikk, status og lønnsflagg.
- [`RF1022_BEHANDLINGSLOGIKK.md`](RF1022_BEHANDLINGSLOGIKK.md) - workbook-logikken for RF-1022, inkludert skyldig/påløpt og periodisering.

## Datakilder og struktur

- [`architecture/datakilder_og_mapping_navaerende_struktur.md`](architecture/datakilder_og_mapping_navaerende_struktur.md) - gjeldende modell for delt datamappe, aktiv mapping, lokal cache og hva som ble ryddet i stabiliseringsrunden.

---

## Arbeidsmetode — ideer og oppgaver

Vi bruker to nivåer for å skille mellom det vi drøfter og det vi har besluttet:

| Nivå | Fil | Formål |
|------|-----|--------|
| **Ideer** | `doc/*_IDEER.md` | Åpne forslag som trenger drøfting før de eventuelt besluttes. Ingen forpliktelse til å implementere. |
| **TODO** | `doc/TODO.md` | Besluttede oppgaver vi er enige om å gjøre. Flyttes hit fra IDEER-filer etter drøfting. |

**Flyt:**
1. Ny ide → skrives inn i relevant `*_IDEER.md` (eller lages en ny)
2. Ideen drøftes — hvis vi bestemmer oss: flytt til `TODO.md` under «Aktive oppgaver»
3. Implementert og committet → flytt til «Fullført» i `TODO.md`

Eksisterende IDEER-filer:
- [`ANALYSE_UX_IDEER.md`](ANALYSE_UX_IDEER.md) — mulige forbedringer til Analyse-siden
- [`KLIENTLISTE_IDEER.md`](KLIENTLISTE_IDEER.md) — integrasjon av CRMSystem klientliste inn i Utvalg (fil-basert sync vs API)
- [`RISIKOMODUL_IDEER.md`](RISIKOMODUL_IDEER.md) — vesentlighetsgrenser, risikovurdering per regnskapslinje, kobling til eksisterende funksjoner

---

**Beskrivelse**
Dette prosjektet er et GUI‑basert verktøy for å analysere og trekke utvalg fra
regnskapsdata i henhold til norsk revisjonspraksis (NGAAP). Det er basert på
Tkinter og pandas, og støtter import av hovedbokfiler fra ulike formater som
SAF‑T og Excel. 


**Hurtigstart**
1. Kopiér alle filene ved siden av dine eksisterende `.py`-filer (samme nivå som `app.py`).
2. Start `python app.py`
3. (Valgfritt) Bytt din nåværende `dataset_pane.py` med denne for å få loading+fastload+ML.


**Innhold**
- `preferences.py` – kompatibel modul med get/set + load/save (lagrer i .session/preferences.json om mulig)
- `views_virtual_transactions.py` – robust, rask transaksjonstabell (NaN-sikker, limit-visning, dblklikk-callback)
- `ui_loading.py` – global loading overlay (modal Toplevel + indeterminate progressbar)
- `page_analyse.py` – Analyse med overlay, paging, pivot (observed=True), sikre fallbacks
- `page_utvalg.py` – Utvalg med overlay, sikre fallbacks, paging
- `ml_map_utils.py` – last/lagre/suggest/update mapping i .ml_map.json (bakoverkompatibel)
- `dataset_build_fast.py` – hurtig innlesing med usecols + robust parsing
- `dataset_pane.py` – valgfri drop-in som kobler inn overlay + fastload + ML


**Trygghet**
- Alle filer er bakoverkompatible. Hvis enkelte moduler (f.eks. `views_column_chooser`) mangler, bruker vi stubs for å unngå krasj.


## Testing

Prosjektet bruker `pytest` for automatiserte tester.

### Installere avhengigheter

Opprett og aktiver et virtuelt miljø (valgfritt, men anbefalt), og installer avhengigheter:

```bash
pip install -r requirements.txt
pip install pytest



Programmet åpner et vindu med flere faner: Dataset, Analyse,
Utvalg, Resultat og Logg. Start med å laste inn en
regnskapsfil i Dataset‑fanen. Bruk deretter Analyse‑fanen for å se en
pivotert oversikt per konto og detaljerte transaksjoner.

Testing

For å kjøre enhetstester benyttes pytest. Alle testfiler ligger i mappen
tests/. Testene dekker blant annet kolonnemapping (alias‑gjetting) og
analysemodellens funksjoner. Kjør testene med:

pytest


Avhengigheten pytest-cov er brukt for å generere testdekning. Rapporter for
testdekning skrives ut etter testkjøringen.

Endringer i denne utgaven
Forbedret kolonnegjenkjenning

Filen ml_map_utils.py har fått utvidet alias‑liste. Den gjenkjenner nå
flere varianter av feltnavn som Bokført beløp, ISO‑kode og Belap i valuta.
Når en fil lastes inn i Dataset‑fanen, brukes aliasene til å foreslå riktige
kolonnekartinger automatisk.

Større nedtrekkslister i Dataset‑fanen

dataset_pane.py setter nå height=15 på alle nedtrekkslister, slik at
flere kolonner vises samtidig. Dette gjør det enklere å finne riktig
kolonnenavn ved manuell mapping.

Nytt analysemodellag

Modulen analyse_model.py inneholder ren datalogi for Analyse‑fanen. Den
tilbyr blant annet:

build_pivot_by_account(df): lager en pivot per konto (og kontonavn hvis
tilgjengelig) med sum av beløp og antall bilag. Pivoten sørger for at
"Konto" alltid er en egen kolonne, slik at DataFrame kan settes til index
uten KeyError.

build_summary(df): genererer en oppsummering av antall rader, sum beløp
samt min/max dato.

filter_by_accounts(df, accounts): filtrerer på en liste av kontoer.

Oppdatert AnalysePage

page_analyse.py har blitt oppdatert slik at refresh_from_session alltid
setter dataset til verdien fra sessionen (enten attributt dataset eller
fallback df). Dette gjør at testene i tests/test_page_analyse.py passer.

Det er fortsatt en minimal implementasjon uten full GUI‑logikk. I en komplett
applikasjon bør _load_from_session overskrives for å bygge pivotert
oversikt og detaljer.

Videre arbeid

Implementere full Analyse‑GUI ved å bruke analyse_model.py i
_load_from_session for å bygge pivottabellen og vise data i treeviews.

Integrere event‑bus mellom Dataset‑, Analyse‑ og Utvalg‑fanene slik at
datasetthendelser automatisk oppdaterer Analyse‑siden.

Utvide aliaslisten ytterligere etter behov og legge til nye testenheter.
