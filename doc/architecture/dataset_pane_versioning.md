# Dataset-fanen: klient, år og versjoner

**Moduler:**
- [dataset_pane_store_section.py](../../dataset_pane_store_section.py) — refresh/state for Datakilde-blokken.
- [dataset_pane_store_ui.py](../../dataset_pane_store_ui.py) — widget-bygging.
- [dataset_pane_store_logic.py](../../dataset_pane_store_logic.py) — `apply_active_version_to_path_if_needed` (filsti-regler).
- [client_store.py](../../client_store.py) — versjonsbutikk (per klient, per år, per dtype).

**Sist oppdatert:** 2026-04-18

## Formål

Datakilde-blokken øverst på Dataset-fanen samler:

1. **Klient** (bold Label drevet av `client_var`) — hvilket selskap. Byttes via `Bytt klient…`-knappen som åpner `open_client_picker`.
2. **År** (combobox) — hvilket regnskapsår.
3. **Kildeversjon** — administreres i egen Versjoner-dialog. Internt holder `hb_var` gjeldende HB-versjon; selve valget skjer via `Versjoner…`-knappen eller ved klikk på HB/SB-status-pillene.

Disse styrer sammen hvilken fil som lastes inn som aktiv HB/SAF-T-kilde for hele applikasjonen.

## Dataflyt ved bytte

`cb_year` er bundet til `sec._debounced_refresh()`. Klient-bytte skjer kun via `Bytt klient…` → `_on_pick_client` som kaller `refresh()` direkte etter at bruker har valgt en klient. `refresh()` som:

1. Henter klientlisten fra `client_store.list_clients()` — brukes til å validere at lagret klient fortsatt finnes (nullstiller `client_var` hvis ikke).
2. Lister versjoner for *(client, year)* via `client_store.list_versions(...)`.
3. Oppdaterer `hb_var` (se regler nedenfor).
4. Kaller `apply_active_version_to_path_if_needed(sec, force=...)` som setter selve filstien.
5. Oppdaterer status-pillene (HB/SB/KR/LR) via `_update_status_pills()` og speiler klient+år i vindustittel via `_update_window_title()`.

`_last_applied_client` og `_last_applied_year` brukes for å oppdage at bruker faktisk har byttet klient eller år (og trigge `force_apply`).

## Regler for `hb_var`-reset

`hb_var` settes til aktiv versjon når **én** av to betingelser er sann:

1. **Gjeldende verdi finnes ikke i ny versjonsliste** (klient hadde ikke denne versjonen lenger, eller listen ble tom).
2. **Klient eller år er endret siden sist `refresh()` ble applied** (`_last_applied_*` vs. nåværende).

Hvis ingen av delene: `hb_var` beholdes urørt.

## Regler for filsti

`apply_active_version_to_path_if_needed` følger disse prioritetene (se modulens docstring for fullt regelsett):

1. Ekstern fil (utenfor `clients/`-root): ikke overstyr.
2. Tom/manglende fil → sett til aktiv versjon.
3. Intern fil som ikke er aktiv → bytt til aktiv versjon.
4. Ingen aktiv versjon for (klient, år) → tøm feltet.

## Kjente gotchas

### "Kildeversjon oppdateres ikke ved år-bytte" (løst 2026-04-17)

**Symptom:** Bytte fra 2025 → 2024 oppdaterte filstien (peker på `years/2024/...`), men Kildeversjon-dropdown viste fortsatt 2025-filens versjons-id.

**Årsak:** `refresh()` satte kun `hb_var` til aktiv versjon hvis gjeldende verdi *ikke* fantes i nytt års liste. Hvis samme id tilfeldigvis fantes i begge år, ble valget stående.

**Fix:** Lagt til `client_or_year_changed`-sjekk mot `_last_applied_client`/`_last_applied_year`. Ved endring tvinges reset til nytt års aktive versjon. Se [test_refresh_resets_hb_var_when_year_changes](../../tests/test_dataset_pane_store_autopath.py).

## Relaterte felt i samme UI

Øvrige deler av Datakilde-blokken som oppdateres av samme refresh:

- **Status-pills** (`_status_pills`) — HB/SB/KR/LR. Grønne med ✓ når aktiv versjon finnes for dtypen, ellers grå. Klikk åpner Versjoner-dialog for HB/SB; KR/LR viser "kommer"-info.
- **Info-bokser** — 3 parallelle `LabelFrame`-er under status-pillene:
  - **Selskap** (`_company_labels`): org.nr, knr (lokalt) + org.form, næring, MVA, adresse (BRREG-lazy). `status`-raden vises *kun* ved rødt flagg (konkurs/avvikling/slettedato) via `_set_status_row_visible`; ellers `grid_remove`-es både key- og value-label for å unngå tom "Status: –"-rad.
  - **Roller** (`_role_labels`): daglig leder, styreleder, nestleder, styremedlemmer, varamedlemmer, revisor, regnskapsfører (BRREG-lazy). Match går på stabil `rolle_kode` (DAGL/LEDE/NEST/MEDL/VARA/REVI/REGN) — ikke beskrivelse, fordi BRREG returnerer f.eks. "Styrets leder" for LEDE.
  - **Team** (`_team_labels`): partner (initialer → fullt navn via `team_config`), manager, medarbeidere (fra `client_meta_index`).
- **Vindustittel** — "Utvalg — {år} — {klient}" (`_update_window_title`).
- Filstien nederst (håndteres av `apply_active_version_to_path_if_needed`).

## BRREG-anrikning (lazy)

Selskap-boksen (status/adresse/morselskap) og Roller-boksen fylles via BRREG lazy i bakgrunnstråd — aldri blokkerende for `refresh()`.

**Dataflyt:**

1. `_update_client_info()` henter `meta` fra `client_meta_index.get_index()` og fyller orgnr/knr + Team-boks synkront.
2. Kaller `_update_brreg_fields(meta)` som plukker ut `org_number`.
3. Hvis orgnr finnes i `_brreg_cache`: render umiddelbart via `_render_brreg_labels`.
4. Ellers: sett Selskap/status til "Laster…", bump `_brreg_request_id`, start `threading.Thread(target=_brreg_worker, …)`.
5. Worker kaller `brreg_client.fetch_enhet` + `fetch_roller` (24t cache internt), scheduler `_brreg_apply_result` via `frame.after(0, …)`.
6. `_brreg_apply_result` lagrer *alltid* i cache (selv stale) — dropper render hvis `request_id` ikke matcher siste eller `orgnr` har endret seg siden.

**Render-regler (Selskap-felt):**

Faste rader (alltid synlige) fylles uavhengig av flagg:
- `orgform` = `organisasjonsform`
- `naering` = `naeringsnavn`
- `mva` = `✓` hvis `registrertIMvaregisteret`, ellers `–`
- `address` = `forretningsadresse`

`status`-raden vises *kun* ved rødt flagg (`#c62828`), prioritet: konkurs → tvangsavvikling → avvikling → slettedato. Ellers `grid_remove`-es hele raden.

**Render-regler (Roller):**

For hver rolle-type plukkes *første* match fra `fetch_roller`-listen:
- `Daglig leder`, `Styreleder`, `Nestleder`, `Revisor`, `Regnskapsfører` — enkeltverdier.
- `Styremedlem` og `Varamedlem` — samles som kommaseparert liste (kan være flere personer).

**Team-rendering:**

`_update_team_labels` leser `responsible`, `manager`, `team_members` fra klient-meta. Partner-initialene sendes gjennom `team_config.resolve_initials_to_name`; viser "Fullt Navn (INI)" hvis navn finnes, ellers initialene i uppercase. Medarbeidere normaliseres fra newline-/kommaseparert Visena-streng.

**Stale-check:** `_brreg_request_id` bumpes ved hver ny forespørsel; `_brreg_current_orgnr` speiler hvilken orgnr UI faktisk viser. Begge må matche for at apply skal rendres.

**Testdekning:** [tests/test_dataset_pane_store_brreg.py](../../tests/test_dataset_pane_store_brreg.py) dekker cache-render, konkurs/avvikling-flagg, MVA-tegn, stale-drop + cache-lagring ved stale, orgnr mangler, rolle-plukking (inkl. styremedlem-joining), parent-formatering (dict/streng) og team-labels (partner-oppslag, fallback til initialer, medarbeidere-joining).

Når man bygger et nytt datasett (`Bygg datasett`-knapp) lagres HB-fila som ny versjon via `client_store.create_version(...)` og blir aktiv — da må `refresh()` kalles for å plukke opp endringen.

## Globale innstillinger

"Oppsett…"-knappen (datamappe, klientliste, eksportvalg) er flyttet ut av Datakilde-blokken og ligger nå nederst i Admin-fanen, siden det er globale innstillinger som ikke er klient-/år-spesifikke.

## Testdekning

[tests/test_dataset_pane_store_autopath.py](../../tests/test_dataset_pane_store_autopath.py)

- Aktiv versjon brukes når filfeltet er tomt.
- Eksisterende gyldig filsti overstyres ikke.
- `hb_var` resettes til nytt års aktive versjon ved år-bytte (regresjon for 2026-04-17-bug).

[tests/test_dataset_pane_store_section.py](../../tests/test_dataset_pane_store_section.py)

- `_on_select_sb`: auto-reader first, preview-fallback ved feil, avbrudd-håndtering.
