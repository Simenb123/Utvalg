# A07 Status, Progresjon Og Videre Plan

Sist oppdatert: 2026-04-29.

Dette er et kort checkpoint for A07-arbeidet for ny utvikler eller ny agent.
Bruk `DEVELOPER_HANDOVER.md` for bredere bakgrunn og `CURRENT_STATUS.md` for
lengre status. Denne filen oppsummerer siste arbeidsbolk og neste konkrete
retning.

## Status Naa

- A07 er teknisk langt ryddigere enn tidligere, men brukerflyten er fortsatt
  under arbeid.
- Tryllestav er hovedhandlingen for forslag og solver. Den skal jobbe paa
  markerte A07-rader, ikke skjult fallback til alle apne koder.
- A07-kode er fortsatt primart matchingnivaa. RF-1022 er kontroll- og
  oppsummeringsnivaa.
- Mappingformatet beholdes: `konto -> A07-kode` eller `konto -> A07_GROUP:*`.
- Gruppeforslag skal fortsatt behandles manuelt som `group_review`.
- Ingen regel eller feedback skal automatisk skrive global mapping uten aktivt
  adminvalg.

## Progresjon Siste Bolk

- Admin/A07-regler er utvidet med regnskapslinjer som faglig filter.
- Global blokkering av regnskapslinje `655 Bankinnskudd, kontanter o.l.` er
  lagt inn for aa stoppe bankkontoer som belopstreff i A07-forslag.
- Globalt foretrukne regnskapslinjer er lagt inn som positivt signal, med
  `40 Lonnskostnad` seedet som globalt foretrukket.
- Regnskapslinjevelger i Admin har sokbar liste, multiselect og drag/drop til
  foretrukne, ekstra, blokkerte og globale felt.
- Sumposter filtreres bort fra regnskapslinjevelgeren, slik at admin velger
  konkrete regnskapslinjer.
- Forslagsfeedback finnes som lokal logg per klient/aar. Feedback skjuler
  eksakte avviste kombinasjoner, men endrer ikke globale regler automatisk.
- Admin-fanen for A07-feedback lastes lazy for aa unngaa treg appoppstart.
- Gruppe-solver finnes og bruker `related_codes` som signal, men Admin-GUI for
  gruppeoppsett er fortsatt for svak.

## Viktige Beslutninger

- Ikke los svak GUI med mer forklaringstekst. Hoved-A07 skal vaere stabil,
  knappene fa og arbeidsflaten selvforklarende.
- UB er standard faglig basis for A07-lonns-/resultatposter. Endring brukes
  bare naar regelen tilsier balanse-/periodiseringslogikk.
- Belop alene er ikke nok for gode forslag. Regler, kontoomraader,
  regnskapslinjer, aliaser, historikk og feedback skal styre prioriteringen.
- Blokkerte kontoomraader og blokkerte regnskapslinjer er harde sperrer for
  forslag.
- Globalt foretrukne regnskapslinjer er bare positivt signal, ikke tvang.
- `related_codes` er riktig naavaerende felt for A07-koder som ofte horer
  sammen.

## Plan Fremover

1. Bygg bedre Admin-GUI for A07-grupper.
   - Erstatt fritekstfeltet i `Grupper` med to lister: relaterte koder og
     tilgjengelige A07-koder.
   - Stott sok, multiselect, drag/drop, legg til og fjern.
   - Vis A07-kode, navn, RF-1022 og AGA.
   - Ikke vis tekniske `A07_GROUP:*`-regler.

2. Normaliser gruppeoppsett ved lagring.
   - Behold JSON-feltet `related_codes`.
   - Fjern duplikater og selvreferanser.
   - Behold bare A07-koder som finnes i regelboken.
   - Lagre relasjoner symmetrisk som standard.

3. Stram gruppe-solver.
   - La regelstyrte grupper rangere foran tilfeldige belopskombinasjoner.
   - Behold krav om eksakt eller veldig godt belopstreff.
   - Fortsett aa returnere `group_review`, ikke automatisk mapping.

4. Etter gruppeoppsettet: rydd forslagssortering og tabelloppsett videre.
   - Null-diff med faglig stotte skal ligge over tilfeldige nesten-treff.
   - Hovedtabeller skal fortsette mot felles kolonnenavn og bedre scrollbars.
   - Full ManagedTreeview-migrering av hovedtraerne tas separat.

## Relevante Tester

Anbefalt baseline for neste runde:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_page_admin.py tests\a07\test_residual_solver.py tests\a07\test_residual_display.py tests\a07\test_residual_magic.py --no-cov -q
.\.venv\Scripts\python.exe -m pytest tests\a07 tests\test_a07_feature_suggest.py tests\test_a07_module_budgets.py --no-cov -q
.\.venv\Scripts\python.exe -m compileall -q src\pages\admin src\pages\a07 a07_feature tests\a07
```
