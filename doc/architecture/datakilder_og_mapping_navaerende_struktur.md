# Datakilder og mapping - naavaerende struktur

**Status:** gjeldende arbeidsmodell etter stabiliseringsrunden i april 2026  
**Gjelder for:** `Utvalg-1`  
**Formaal:** beskrive hvor data faktisk ligger, hva som er kilde til sannhet, og hva vi nylig har ryddet.

## Kortversjon

Utvalg bruker na tre hovedtyper data:

1. `Delt arbeidsdata`
   Dette er felles data som flere brukere skal se likt. Her ligger klientmapper, aktiv mapping for regnskapslinjer/kontoplan, AR-data og andre arbeidsfiler.

2. `Lokal brukerprofil og cache`
   Dette er personlige innstillinger, lokale hjelpefiler og cache. Dette skal ikke vaere kilde til sannhet for klientarbeid.

3. `Appregler og kode`
   Dette er filer som hører til selve appen/repoet, for eksempel teamoppsett og enkelte regelsett i `config/`.

Den viktigste avklaringen er:

- `klientmapper skal ikke ligge i repoet`
- `aktiv mapping for regnskapslinjer og kontoplan skal ikke ligge i repoet`
- `aktiv mapping ligger i delt datamappe`

## Hva vi har jobbet med

Det ble gjort et forsok paa aa flytte `Regnskapslinjer` og `Kontoplanmapping` til repo-lokal adminlogikk. Det var feil for denne appens faktiske bruksmønster, fordi:

- klientarbeidet lever i delt datamappe
- flere brukere maa kunne se samme mapping
- Analyse og andre faner forventer at aktiv mapping er felles

Dette ble derfor stabilisert tilbake.

Resultatet na er:

- runtime leser igjen aktiv mapping fra delt datamappe
- admin-redigering peker igjen mot den delte JSON-kilden
- GUI-et er ryddet slik at det beskriver dette som `Felles mapping`
- misvisende tekst om lokal admin-sannhet er fjernet eller tonet ned

Vi har med andre ord **ikke** innført noen ny lokal mappingmodell. Vi har tvert imot landet tilbake paa delt sannhet for mapping.

## Kilde til sannhet per omraade

### 1. Klientdata

**Type:** delt arbeidsdata  
**Lagring:** under aktiv `data_dir`

Eksempler:

- klientmapper
- aarsdata / versjoner / imports
- dokumentkontroll-data
- klientspesifikke profiler og overstyringer

Viktig:

- dette er operative arbeidsdata
- dette skal ikke flyttes inn i repoet

Relevante moduler:

- `app_paths.py`
- `client_store.py`
- `document_control_store.py`
- `regnskap_client_overrides.py`

### 2. Regnskapslinjer og kontoplanmapping

**Type:** delt arbeidsdata  
**Kilde til sannhet:** JSON i delt datamappe

Aktive filer:

```text
<data_dir>/config/regnskap/regnskapslinjer.json
<data_dir>/config/regnskap/kontoplan_mapping.json
<data_dir>/config/regnskap/regnskap_config.json
```

Viktig:

- dette er aktiv runtime-sannhet
- Analyse, Admin og andre flater skal lese samme delte JSON-kilde
- Excel er ikke aktiv runtime-kilde
- Excel er heller ikke fallback i dagens modell

Relevante moduler:

- `regnskap_config.py`
- `page_admin_rl.py`
- `page_admin_rl_models.py`
- `views_settings.py`

### 3. Klientspesifikke overstyringer

**Type:** delt arbeidsdata  
**Lagring:** i delt datamappe per klient / aar

Dette er ikke det samme som global mapping. Dette er finjusteringer per klient.

Eksempel:

- konto -> regnskapslinje-overstyringer i `regnskap_client_overrides.py`

Se ogsaa:

- `doc/architecture/regnskap_overrides.md`

### 4. BRREG-oppslag

**Type:** ekstern tjeneste  
**Kilde:** BRREGs API-er

Dette er ikke lagret som egen sannhetskilde i appen. Det er oppslag mot eksterne endepunkter.

Relevante moduler:

- `brreg_client.py`
- `page_ar_brreg.py`
- `reskontro_brreg_actions.py`

### 5. BRREG-cache

**Type:** lokal cache  
**Formaal:** ytelse / mindre nettverkstrafikk

Dette er **ikke** delt arbeidsdata og **ikke** kilde til sannhet. Det er bare en teknisk mellomlagring av eksterne oppslag.

Viktig:

- kan i prinsippet slettes
- skal ikke brukes som beslutningsgrunnlag for hvor klientdata ligger

### 6. Brukerinnstillinger

**Type:** lokal brukerprofil

Eksempler:

- preferences
- presets
- kolonnevalg

Dette er personlige valg, ikke felles klientdata.

## Datakilder-fanen i GUI

`Admin -> Oppsett -> Datakilder` er na ment som en **oversikt**, ikke som en ny lagringsmodell.

Visningen bruker disse begrepene:

- `Appregler`
- `Delt arbeidsdata`
- `Min profil`
- `Lokal cache`
- `Eksterne tjenester`
- `Sidekilder`

Disse navnene er laget for aa vaere mer forståelige i GUI enn de interne gruppenavnene i koden.

Viktig:

- interne ID-er i koden er beholdt for stabilitet
- GUI-navnene er et visningslag oppa dette
- dette endrer ikke hvor data lagres

## Aktiv datamappe

Aktiv datamappe styres via:

- `Admin -> Oppsett -> Generelt`
- hintfil / path-oppsett i `app_paths.py`

For regnskapsmapping betyr dette:

```text
regnskap_config.config_dir() = <data_dir>/config/regnskap
```

Det er denne plasseringen appen na bruker som aktiv sannhet.

## Hva som ikke skal antas lenger

Dette er viktige avklaringer etter oppryddingen:

- `Regnskapslinjer` er ikke repo-lokal sannhet
- `Kontoplanmapping` er ikke repo-lokal sannhet
- klientmappene skal ikke ligge i repoet
- BRREG-cache er ikke delt arbeidsdata
- Datakilder-fanen er ikke en migreringsmekanisme

## Praktisk huskeregel

Hvis dataene svarer paa sporsmaalet:

- `maa flere brukere se dette likt?`

Da skal de som hovedregel ligge i delt datamappe.

Hvis dataene svarer paa sporsmaalet:

- `er dette bare min preferanse eller en teknisk cache?`

Da skal de som hovedregel vaere lokale.

## Relevante filer aa kjenne til

### Runtime og path-oppsett

- `app_paths.py`
- `views_settings.py`

### Aktiv mapping

- `regnskap_config.py`
- `page_admin_rl.py`
- `page_admin_rl_models.py`

### Klient-/arbeidsdata

- `client_store.py`
- `document_control_store.py`
- `ar_store.py`
- `regnskap_client_overrides.py`

### BRREG

- `brreg_client.py`
- `brreg_mapping_config.py`

## Anbefalt videre arbeidsretning

Na som modellen er stabil igjen, boer videre arbeid holde seg til dette:

1. behold aktiv mapping i delt datamappe
2. behold klientdata i delt datamappe
3. behold cache og personlige innstillinger lokalt
4. fortsett aa forbedre GUI-ordlyd uten aa endre lagringsmodell ubevisst
5. gjor eventuelle fremtidige strukturendringer eksplisitt og migrerbart

## Oppsummering

Den operative strukturen i dag er:

- `repoet` inneholder kode og appnaere regler
- `data_dir` inneholder delt arbeidsdata og aktiv mapping
- `lokal profil/cache` inneholder personlige valg og teknisk mellomlagring

Det viktigste resultatet av arbeidet vi nettopp gjorde er at appen igjen er tilbake paa denne modellen, og at GUI-et na forklarer den tydeligere.
