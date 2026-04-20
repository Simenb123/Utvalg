# RL-mapping-drift — kontroll og visning

**Status:** Implementert 2026-04-20.
**Relaterte moduler:**
[rl_mapping_drift.py](../../rl_mapping_drift.py),
[rl_mapping_drift_dialog.py](../../rl_mapping_drift_dialog.py),
[analyse_mapping_ui.py](../../analyse_mapping_ui.py),
[regnskapslinje_mapping_service.py](../../regnskapslinje_mapping_service.py),
[regnskap_client_overrides.py](../../regnskap_client_overrides.py),
[previous_year_comparison.py](../../previous_year_comparison.py).

## Hvorfor

Samme saldobalansekonto kan være mappet til forskjellig regnskapslinje
(RL) i inneværende år vs fjoråret — enten fordi klient-overrides er
endret, eller fordi baseline-intervallene er justert. Når revisor
sammenligner fjorårstall med årets, gir dette *falsk* endring på
regnskapslinje-nivå: UB-fjor forsvinner fra én RL og dukker opp i en
annen.

Før denne kontrollen var slik drift usynlig; brukeren oppdaget bare
symptomet (RL 10 viser 0 selv om den hadde vesentlig UB i fjor).

## Tre kategorier

1. **`changed_mapping`** — kontoen finnes i begge årenes SB, men
   resolverer til *ulik* regnr.
2. **`only_current`** — ny konto i år som er **umappet** (matcher ikke
   intervall og har ingen override). Mappede nye kontoer er ikke drift.
3. **`only_prior`** — konto fra fjor som var **umappet** og ikke finnes
   i år. Riktig mappede avsluttede kontoer er ikke drift.

Nye/avsluttede kontoer med gyldig mapping i sitt eksistens-år filtreres
bort — de er ikke regnskapslinje-drift, bare naturlig SB-rotasjon. Kun
umappede tilfeller er reelle funn revisor må håndtere.

## Tjenesten

`rl_mapping_drift.detect_mapping_drift()` er en ren funksjon uten
GUI-avhengigheter:

- Bygger to `RLMappingContext` — én med årets overrides, én med
  fjorårets (via `load_prior_year_overrides`).
- Unionerer konto-listen fra inneværende og fjor-SB.
- Kaller `resolve_accounts_to_rl` i begge kontekstene.
- Klassifiserer hver konto i én av de tre kategoriene.
- Sorterer på materialitet `max(|UB|, |UB_fjor|)` synkende.

Kontoer hvor begge år viser regnr=None (umappet i begge) eller UB=0 i
eneste tilgjengelige år, ignoreres — de gir ikke reelle revisjonsfunn.

## Integrasjon i analysefanen

- `analyse_mapping_ui.refresh_mapping_issues()` kaller nå
  `_compute_mapping_drifts()` ved siden av eksisterende mapping-issues.
- Drift-summering (f.eks. *"3 kontoer endret RL-mapping siden fjor
  (sum 1,2 MNOK)"*) legges til i `_mapping_warning_var` — samme banner,
  ingen ny widget.
- En ekstra knapp "Se endret mapping..." i bannerframen åpner en dialog
  via `rl_mapping_drift_dialog.open_dialog()`. Knappen er skjult når
  det ikke finnes drift.

Dialogens Treeview viser kolonnene: Konto, Kontonavn, Type,
RL i år, RL i fjor, UB i år, UB i fjor, Endring. Sortert på
materialitet.

## Tester

- [tests/test_rl_mapping_drift.py](../../tests/test_rl_mapping_drift.py)
  dekker alle tre kategorier, tom-input, override-basert drift, og
  summary-tekst.

## Ikke-mål

- Tjenesten *korrigerer* ikke drift. Revisor må manuelt avgjøre hva
  som er riktig (ved å justere override eller ved å akseptere det som
  et reelt funn).
- Drift på sumpost-nivå regnes ikke — kun på konto-nivå, der
  sammenligningen er meningsfull.
