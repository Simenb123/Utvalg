# Handlinger — bekreftede regnskapslinje-koblinger

**Modul:** [action_workpaper_store.py](../../action_workpaper_store.py)
**Konsument:** [page_revisjonshandlinger.py](../../page_revisjonshandlinger.py)
**Lagringssted:** `<data_dir>/clients/<slug>/years/<YYYY>/handlinger/workpapers.json`
**Sist oppdatert:** 2026-04-17

## Formål

En CRM-handling (risikovurdering, kontroll, etc.) knyttes automatisk til en
regnskapslinje via auto-match mot handlingens tekst/scope. Revisor må kunne:

- **Bekrefte** auto-koblingen → workpaper med `source = "confirmed"`.
- **Overstyre** til en annen RL → workpaper med ny `confirmed_regnr`.
- **Fjerne** bekreftelsen → faller tilbake til auto eller tom.

Bekreftede koblinger lagres per klient/år som et eget workpaper. Dette er
slice 1 av "Handlinger 2.0" — fundamentet for framtidige toveis-sporbare
arbeidsdokument-lenker (se [project_arbeidsdokument_ide](../../../memory/project_arbeidsdokument_ide.md)).

## Filformat

```json
{
  "42": {
    "action_id": 42,
    "confirmed_regnr": "560",
    "confirmed_regnskapslinje": "Aksjer i datterselskap",
    "confirmed_at": "2026-04-17T09:12:05+00:00",
    "confirmed_by": "simenb",
    "note": "RL-overstyring pga. reklassifisering i 2025"
  }
}
```

- Nøkkel = `action_id` som string (int-castable).
- Kun handlinger med *eksplisitt* bekreftelse lagres. Auto-matchede
  uten bekreftelse er ikke i fila.
- Alfabetisk sortering på nøkkel ved `sort_keys=True` for stabil diff.

## API-kontrakt

`action_workpaper_store` eksponerer:

- `load_workpapers(client, year) -> dict[int, ActionWorkpaper]` —
  alle bekreftede koblinger, indeksert på `action_id`. Tom dict hvis
  fil mangler eller ugyldig JSON.
- `confirm_regnr(client, year, action_id, *, regnr, regnskapslinje="", ...)`
  — lagrer ny bekreftelse (tidsstempel default = nå i UTC).
- `clear_confirmation(client, year, action_id) -> bool` —
  fjerner bekreftelse, returnerer True hvis noe ble slettet.
- `resolve_effective_regnr(action_id, auto_regnr, auto_regnskapslinje, workpapers)
  -> (regnr, regnskapslinje, source)` — sentral prioritets-regel (se under).

## Prioritet ved visning

`resolve_effective_regnr` følger denne rekkefølgen:

1. **Bekreftet workpaper** → `source = "confirmed"`.
2. **Auto-match** (fra handlingens metadata) → `source = "auto"`.
3. **Ingen** → `source = ""`.

Denne regelen *eies* av `action_workpaper_store.py` og må ikke duplikeres
i GUI-kode. `page_revisjonshandlinger` leser kun effective-tuple og viser
kilde via tagger (`wp_confirmed`, `wp_auto`, `wp_unmatched`).

## Kjente gotchas

Ingen rapporterte så langt (slice 1 gikk i drift 2026-04-17).

**Potensiell felle — har ikke materialisert seg ennå:**
Når RL-katalogen endres (f.eks. RL 560 omdøpes), vil
`confirmed_regnskapslinje` i workpaper inneholde *gammel* tekst. Løsningen
er å alltid vise *live* regnskapslinje-tekst via RL-oppslag på `regnr`,
ikke den bufrede teksten. Dagens kode gjør dette allerede — men endres
det, må vi revurdere.

## Relaterte felt i samme lagringsmappe

Under `years/<YYYY>/handlinger/` er `workpapers.json` forventet å være
den første av flere fremtidige workpaper-typer. Planlagt:

- `action_risks.json` — handling ↔ risiko-kobling (toveis-sporing).
- `action_documents.json` — handling ↔ arbeidsdokument-kobling.

Alle følger samme mønster: JSON-dict med action_id som nøkkel, ett
toppnivå-dokument per type.

## Testdekning

[tests/test_action_workpaper_store.py](../../tests/test_action_workpaper_store.py) — 20 tester:

- Roundtrip (save → load bevarer alle felt).
- Validering (`action_id <= 0` og tom `regnr` feiler).
- Priortitet i `resolve_effective_regnr` (confirmed > auto > tom).
- Clear-semantikk (kun sletter hvis finnes).

[tests/test_page_revisjonshandlinger_workpaper.py](../../tests/test_page_revisjonshandlinger_workpaper.py) — 8 GUI-tester:

- Knapper aktiveres/deaktiveres riktig ved valg.
- Tagger settes riktig i treeview (confirmed/auto/unmatched).
- Confirm + clear round-trip via GUI-knapper.
