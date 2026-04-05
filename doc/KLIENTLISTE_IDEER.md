# Klientliste-integrasjon: Utvalg ↔ CRMSystem

> Status: **Idé** — ikke besluttet. Drøftes her før evt. flytt til TODO.md.

---

## Bakgrunn

CRMSystem inneholder klientliste med oppdaterte klientnavn, orgnr, ansvarlig revisor og
eventuelle egendefinerte felt (bransje, selskapsform, konsernrelasjon). I dag må disse
verdiene tastes inn manuelt i Utvalg ved oppstart av hvert engasjement. En kobling mellom
systemene ville fjerne dette dobbeltarbeidet og redusere risiko for feil.

---

## Alternativ 1 — Fil-basert synkronisering (anbefalt utgangspunkt)

CRMSystem eksporterer en JSON-fil til en delt lokasjon (lokal mappe, nettverk, OneDrive).
Utvalg leser filen passivt ved oppstart eller på forespørsel.

```
CRMSystem  ──export──▶  clients.json  ──read──▶  Utvalg
```

### Fordeler
- Ingen nettverksavhengighet under revisjonsarbeidet
- Enkelt å versjonere og feilsøke (åpne i tekstredaktør)
- Utvalg trenger ingen kunnskap om CRMSystem-databasen
- CRMSystem styrer selv når og hva som eksporteres

### Ulemper
- Filen kan bli utdatert (mangler nye klienter lagt til etter siste eksport)
- Krever at noen trigger eksporten jevnlig, evt. automatisk ved oppstart av CRMSystem

---

## Alternativ 2 — Direkte databasekobling

Utvalg kobler seg direkte mot CRMSystem sin SQLite/PostgreSQL-database og leser klienttabellen.

### Fordeler
- Alltid fersk data

### Ulemper
- Tett kobling — databaseskjema endringer i CRMSystem knekker Utvalg
- Krever at begge applikasjoner kjøres på samme maskin eller at databasen er tilgjengelig på nett
- Større risiko: lesefeil mot produksjonsdatabasen

**Konklusjon:** Ikke anbefalt for nåværende stadium. Kan vurderes på sikt.

---

## Alternativ 3 — Lokal REST-API i CRMSystem

CRMSystem eksponerer et enkelt HTTP-endepunkt (`GET /api/clients`) som Utvalg kaller.

### Fordeler
- Fersk data uten direkte databasekobling

### Ulemper
- CRMSystem må kjøre som server-prosess i bakgrunnen
- Portåpning, autentisering, feilhåndtering — mye overhead for intern nytte
- Overkill for to desktop-applikasjoner på samme maskin

**Konklusjon:** Ikke anbefalt med mindre CRMSystem allerede har en API-server.

---

## Forslag til JSON-skjema (`clients.json`)

```json
{
  "exported_at": "2026-04-05T08:00:00",
  "version": 1,
  "clients": [
    {
      "client_id": "K001",
      "name": "Veidekke Entreprenør AS",
      "orgnr": "921070535",
      "responsible_auditor": "Simenb",
      "industry": "Bygg og anlegg",
      "entity_type": "AS",
      "group_parent_orgnr": null,
      "active": true,
      "notes": ""
    }
  ]
}
```

Feltene er minimale og stabile — endrer ikke skjema ofte. `version`-feltet gjør det
trygt å utvide skjemaet uten å knekke Utvalg.

---

## Hva CRMSystem-koden trenger (nødvendige endringer)

### 1. Eksportfunksjon

En ny funksjon (f.eks. i `client_service.py` eller tilsvarende):

```python
def export_clients_json(path: str) -> None:
    """Eksporter alle aktive klienter til JSON for Utvalg."""
    clients = db.query("SELECT ... FROM clients WHERE active = 1")
    data = {
        "exported_at": datetime.utcnow().isoformat(),
        "version": 1,
        "clients": [_to_dict(c) for c in clients],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
```

### 2. Trigger-mekanisme (ett av disse)

| Alternativ | Beskrivelse |
|------------|-------------|
| **Manuell knapp** | «Eksporter til Utvalg»-knapp i CRMSystem UI. Enklest å implementere. |
| **Automatisk ved oppstart** | CRMSystem eksporterer automatisk ved oppstart hvis eksportmappe er konfigurert. |
| **Automatisk ved endring** | CRMSystem eksporterer etter lagring av klient. Mest oppdatert, litt mer komplekst. |

### 3. Konfigurasjon

CRMSystem trenger ett nytt innstillingsfelt: `utvalg_export_path` — stien til eksportmappen.
Kan lagres i eksisterende settings-fil/database.

---

## Hva Utvalg-koden trenger

### 1. Leser/cache-modul (ny: `crm_client_cache.py`)

```python
def load_clients(path: str) -> list[dict]:
    """Les clients.json. Returnerer tom liste hvis filen mangler."""
    ...

def find_client_by_orgnr(clients, orgnr: str) -> dict | None:
    ...

def find_clients_fuzzy(clients, query: str) -> list[dict]:
    """Fuzzy-søk på navn — for autocomplete."""
    ...
```

### 2. Integrasjonspunkter i Utvalg

| Sted | Bruk |
|------|------|
| Dataset-fanen, klient-felt | Autocomplete fra klientlisten |
| Reskontro-fanen, leverandørsøk | Foreslå klientnavn fra lista |
| Rapport-header | Forhåndsutfyll klientnavn + orgnr |
| Ny engasjements-dialog (fremtidig) | Velg klient fra liste |

### 3. Fallback

Hvis `clients.json` ikke finnes eller er ugyldig → Utvalg fungerer som i dag (manuell innskriving).
Ingen breaking change.

---

## Anbefalt første steg

1. Bli enige om `clients.json`-stien (f.eks. `~/Documents/Utvalg/clients.json` eller OneDrive-mappe)
2. Implementer eksportfunksjonen i CRMSystem + manuell knapp
3. Implementer `crm_client_cache.py` i Utvalg
4. Koble til autocomplete i Dataset-fanen

Ingen av disse stegene er spesielt store — dette er et par timers arbeid per applikasjon.

---

## Åpne spørsmål

- [ ] Hvor skal `clients.json` lagres? Lokal mappe, OneDrive, eller nettverksressurs?
- [ ] Skal Utvalg vise en advarsel hvis filen er eldre enn X dager?
- [ ] Hvilke felt fra CRMSystem er faktisk nyttige i Utvalg?
- [ ] Er konsernrelasjon (mor/datter) relevant — f.eks. for konsolideringsmodulen?
