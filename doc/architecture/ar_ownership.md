# AR — Aksjonærregister, eierforhold og eide selskaper

**Moduler:**
- [ar_store.py](../../ar_store.py) — kjernelogikk, SQLite + per-klient JSON.
- [brreg_client.py](../../brreg_client.py) — BRREG-oppslag (enhet + regnskap).
- [page_ar.py](../../page_ar.py) — GUI-fane.

**Lagringssteder:**
- Globalt aksjonærregister (SQLite): `<data_dir>/aksjonaerregister/ownership.db`
- Per klient/år: `<data_dir>/clients/<slug>/years/<YYYY>/aksjonaerregister/`
  - `accepted_owned_base.json` — låst "base" for rapportering.
  - `manual_owned_changes.json` — revisors tillegg/endringer.
  - `imports/<orgnr>/<import_id>/` — spor av importerte PDF-er/metadata.

**Sist oppdatert:** 2026-04-17

## Formål

AR-modulen håndterer tre adskilte behov:

1. **Eide selskaper** — hvilke selskaper klienten eier andeler i.
2. **Eiere** — hvem som eier andeler i klienten.
3. **Sporbar import** — PDF-basert aksjonærregister lagres som
   immutable import-record med transaksjonsliste og metadata.

All presentasjon skjer via `get_client_ownership_overview(client, year)`
som slår sammen kilder i prioritert rekkefølge.

## Datalag

### Globalt lag — SQLite

`ownership_relations`-tabellen er *delt på tvers av klienter* og lagrer
årlig snapshot av Skatteetatens aksjonærregister:

```
(year, company_orgnr, shareholder_orgnr, shareholder_name, shareholder_kind,
 shares, total_shares, ownership_pct)
```

Indekseres på `(year, company_orgnr)` og `(year, shareholder_orgnr)` for
toveis-oppslag. Én rad per aksjonær per selskap per år.

### Klientspesifikt lag — JSON

Per (klient, år) lagres to filer:

- **`accepted_owned_base.json`** — "akseptert" grunnlag. Typisk siste
  registerkjøring som revisor har godkjent. Funker som read-only basis.
- **`manual_owned_changes.json`** — liste av operasjoner revisor har
  gjort (legg til, slett, juster eierandel). Appendes, aldri skrives over.

## Merge-semantikk — `get_client_ownership_overview`

```
effective_rows = _merge_owned_relations(accepted_rows, manual_changes)
```

1. Start med `accepted_owned_base.json` som basis.
2. Appliser `manual_owned_changes.json` i kronologisk rekkefølge.
3. Splitt ut "self-ownership" (klienten eier seg selv, vanlig i holdings).
4. For hver rad: berik med `matched_client` (via `find_client_by_orgnr`)
   og `has_active_sb` (om intern SB finnes for året).

Returnerer en stor dict med både eide selskaper, eiere, compare mot
forrige år, og import-metadata.

## Koblinger ut mot resten av appen

- **`find_client_by_orgnr(orgnr)`** — brukes av flere moduler for å
  sjekke om et orgnr tilhører en intern klient i `client_store`.
- **`get_client_ownership_overview(...)`** — kilde for dropdown i SB
  hvor revisor kobler en konto til et eid selskap (slice 2 av
  klassifiserings-arkitekturen, se [plans/peppy-growing-whisper](../../)).
- **`brreg_client.fetch_enhet(orgnr)` / `fetch_regnskap(orgnr)`** —
  24t-cachet BRREG-data for read-only visning av eide selskaper.

## Kjente gotchas

### Historisk fallback ved manglende register-år

Hvis `load_registry_meta(year)` er tom (ingen import for året), bruker
`_find_owners_with_fallback` forrige tilgjengelige år. Dette er bevisst
— men den *år-som-ble-brukt* returneres som `owners_year_used` og må
vises i GUI så revisor ser hvorfor eier-listen ikke matcher valgt år.

### Self-ownership filtreres ut

`_split_self_relations` sørger for at hvis klienten eier seg selv
(holdingselskap som eier egne aksjer), blir disse radene flyttet til
`self_ownership`-seksjonen og IKKE inkludert i `owned_companies` /
`owners`. Dette hindrer dobbeltelling.

### Stale SB-kobling i eide selskaper

`has_active_sb` er en snapshot. Hvis intern SB slettes etter at AR-
overview er generert, viser UI fortsatt True. Løsning: kall
`get_client_ownership_overview` på nytt når AR-fanen åpnes / datasettet
bygges på nytt.

## Testdekning

[tests/test_ar_store.py](../../tests/test_ar_store.py) — roundtrip,
merge-semantikk, self-ownership-split.

Ved nye bugs: dokumenter her med dato, symptom, årsak, fix — per
konvensjonen i [memory/project_doc_architecture](../../../memory/project_doc_architecture.md).
