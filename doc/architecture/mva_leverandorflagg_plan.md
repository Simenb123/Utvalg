# MVA-fradrag på ikke-MVA-registrerte leverandører — kontroll-plan

**Sist oppdatert:** 2026-04-26

Dokumenterer en revisjons-relevant kontroll som brukeren ønsker under
MVA-fanen: identifiser bilag der det er bokført inngående MVA-fradrag
på en leverandør som **ikke** er registrert i MVA-registeret. Dette er
en høyrisiko-feil som direkte påvirker forholdet til Skatteetaten.

**Status:** Kun dokumentert. Ingen kode endret.

## 1. Hva kontrollen skal finne

For hver transaksjon i hovedboken som har:
- En **inngående MVA-kode** (f.eks. norsk standard kode 1, 11, 12, 13)
- Beløp på **leverandør-konto** (typisk 2400-serien)
- Identifisert **leverandør** (orgnr fra SAF-T eller manuell mapping)

Sjekk om leverandøren faktisk er **MVA-registrert** ved oppslag i:
- BRREG-feltet `registrertIMvaregisteret`
- SAF-T-feltet `LeverandørMvaReg` (TaxRegistrationNumber > 0)

Flagg avvik der MVA-fradrag er bokført uten at leverandør er
MVA-registrert.

**Eksempel-flagg:**
> Bilag 1234 (07.01.2025): MVA-fradrag 2.500 kr på leverandør
> "Cleaning Services AS" (org.nr 999888777). Leverandør er IKKE
> registrert i MVA-registeret per BRREG-oppslag. **Mulig
> uberettiget fradrag.**

## 2. Status quo — datakilder finnes allerede

### 2.1 BRREG-data
- `brreg_client.py:213` setter `registrertIMvaregisteret` (boolean)
- `brreg_client.py:184` cacher hele BRREG-record per orgnr lokalt
- Allerede brukt i Reskontro-fanen via `src/pages/reskontro/backend/brreg_helpers.py`

### 2.2 SAF-T-data
- `saft_reader.py:401` parser `TaxRegistrationNumber` → `supplier_tax_reg`
- `saft_reader.py:577` setter `LeverandørMvaReg` (bool) per transaksjon
  i HB-DataFrame
- Også `Leverandørorgnr` settes per transaksjon

### 2.3 MVA-kode-klassifisering
- `src/pages/mva/backend/codes.py` har `STANDARD_MVA_CODES` med
  semantisk klassifisering (utgående/inngående/null/fritak)
- `src/pages/mva/backend/codes.py` har `ACCOUNTING_SYSTEMS` for
  tilfelle der klient bruker proprietære koder (PowerOffice etc.)
- `src.shared.regnskap.client_overrides.load_mva_code_mapping()` gir
  per-klient mapping fra klient-koder til SAF-T-standard

### 2.4 Eksisterende reskontro-BRREG-sjekk (referanse)
- `src/pages/reskontro/backend/brreg_helpers.py` har `_brreg_has_risk()`
  og `_brreg_status_text()` som leser BRREG-status og rapporterer flagg
  som "Konkurs", "Slettet", "Under avvikling" osv.
- Dette mønsteret kan gjenbrukes — utvides med "Ikke MVA-registrert"

## 3. Foreslått implementering

### 3.1 Lokasjon

`src/pages/mva/backend/leverandor_mva_kontroll.py` (ny modul, ren
backend uten Tk).

### 3.2 API-skisse

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class MvaLeverandorFlag:
    bilag: str
    dato: str
    konto: str
    kontonavn: str
    leverandør_orgnr: str
    leverandør_navn: str
    mva_kode: str
    beløp: float
    mva_beløp: float
    årsak: str  # "Ikke MVA-registrert i BRREG" / "Mangler orgnr" / ...
    severity: str  # "high" / "medium" / "low"


def find_flagged_supplier_vat_deductions(
    df_hb: pd.DataFrame,
    *,
    client: str,
    year: int,
    inngaende_koder: set[str] | None = None,
) -> list[MvaLeverandorFlag]:
    """Identifiser inngående MVA-fradrag på ikke-MVA-registrerte
    leverandører.

    Pipeline:
    1. Filtrer df_hb til transaksjoner med inngående MVA-kode
    2. For hver unik leverandør-orgnr, slå opp BRREG MVA-status
       (cached oppslag — bruk eksisterende brreg_client-cache)
    3. Returnér flagg for transaksjoner der leverandør har
       `registrertIMvaregisteret=False`
    """
```

### 3.3 Inngående koder

Vi trenger å vite hvilke MVA-koder som representerer inngående
fradrag. For norske SAF-T-standard er dette typisk:
- **1** — fradragsberettiget inngående mva, høy sats (25%)
- **11** — fradragsberettiget inngående mva, mat (15%)
- **12** — fradragsberettiget inngående mva, lav (12%)
- **13** — fradragsberettiget inngående mva, kjøp av tjenester fra
  utland (snudd avregning)

`STANDARD_MVA_CODES` har feltet `direction` eller lignende — bruke
det for filtrering.

### 3.4 Per-klient kode-mapping

Hvis klient bruker proprietære koder (PowerOffice "P1", Tripletex
"24" osv.), brukes
`src.shared.regnskap.client_overrides.load_mva_code_mapping(client)`
for å oversette til SAF-T-standard.

### 3.5 BRREG-oppslag

Bruk eksisterende `brreg_client.fetch_company(orgnr)` som returnerer
cached record med `registrertIMvaregisteret`-felt. Allerede asynkront
og cached lokalt.

### 3.6 SAF-T-data brukes hvis tilgjengelig

For SAF-T-importerte datasett finnes `LeverandørMvaReg` allerede per
transaksjon. Da kan vi bruke det direkte uten BRREG-oppslag for
raskere første-pass:

```python
# Rask sti for SAF-T
if "LeverandørMvaReg" in df_hb.columns:
    flagged = df_hb[
        (df_hb["MVA-kode"].isin(inngaende_koder)) &
        (df_hb["LeverandørMvaReg"] == False) &
        (df_hb["Leverandørorgnr"] != "")
    ]
```

For ikke-SAF-T (f.eks. Excel-importert HB), faller man tilbake til
BRREG-oppslag per leverandør.

## 4. UI-konsept

Knapp i MVA-fanen: **"Sjekk leverandør-MVA-status"**.

Trykk åpner dialog (popup, ikke fane) med:

```
+--------------------------------------------------------+
| Leverandør-MVA-kontroll                       [X]      |
+--------------------------------------------------------+
| Klient: Spor Arkitekter AS · År: 2025                  |
|                                                        |
| Sjekker inngående MVA-fradrag mot BRREG MVA-register.  |
| [Kjør sjekk]   23 transaksjoner sjekket · 2 flagg      |
|                                                        |
| Flagg (ManagedTreeview):                               |
| +-----+--------+--------+----------+----------+------+ |
| | Bil | Dato   | Konto  | Lev.navn | MVA-bel  | Risiko|
| +-----+--------+--------+----------+----------+------+ |
| | 100 | 07.01  | 6320   | Cleaning | 250.00   | Høy  | |
| | 250 | 15.03  | 6890   | Webhost  | 75.00    | Høy  | |
| +-----+--------+--------+----------+----------+------+ |
|                                                        |
| Eksporter til Excel...   [Lukk]                        |
+--------------------------------------------------------+
```

Lokasjon: `src/pages/mva/frontend/leverandor_mva_dialog.py`

Bruke `ManagedTreeview` (jf. `doc/TREEVIEW_PLAYBOOK.md`) for
flagg-tabellen — sortering, kolonneveiler, persist mellom økter.

## 5. Utvidelser (senere)

- **Kjør automatisk ved data-refresh** og vis badge på MVA-fanen ved
  flagg
- **Inkluder kreditnotaer** — også flagging på utgående MVA på
  ikke-MVA-registrerte kunder (motsatt scenario)
- **Tidsstempel for BRREG-oppslag** — vis "MVA-status sjekket
  2026-04-26" og varsle hvis cache er > X dager gammel
- **Saldo-oppslag** — ikke flagg leverandører som har vesentlig
  utestående saldo (kan være snudd avregning eller konkurs der
  MVA-fradrag er korrekt på bestemte tidspunkter)
- **Excel-eksport** — egen rapport-arket "MVA-leverandør-flagg" i
  arbeidsdokumentet

## 6. Estimat og rekkefølge

**Fase 1 (~2 timer):** Backend-modul + tester
- `leverandor_mva_kontroll.py` med `find_flagged_supplier_vat_deductions`
- Tester for SAF-T-rask-sti og BRREG-fallback
- Tester for kode-mapping-oversettelse

**Fase 2 (~1 time):** UI
- Dialog-popup med ManagedTreeview
- Knapp i MVA-fanen
- Excel-eksport-knapp

**Fase 3 (~30 min):** Integrasjon
- Lazy-load: kjør sjekken kun når dialog åpnes
- Status-oppsummering i MVA-fanens hovedside

**Total: ~3-4 timer for solid v1**

## 7. Risiko og forbehold

- **BRREG-oppslag-rate-limit**: Hvis klient har 200+ unike
  leverandører kan det ta tid første gang. Cachen hjelper for
  påfølgende kjøringer
- **Inngående mva-koder kan være misconfigurerte**: Hvis klient bruker
  egendefinerte koder uten mapping, kan vi miste flagg. Skal varsle
  brukeren tydelig hvis ukjente koder funnet
- **Periodisering**: En leverandør kan være MVA-registrert i deler av
  året — BRREG sier kun "registrert nå". For revisjonsåret må vi
  egentlig sjekke historisk status. Versjon 1 godtar BRREG-snapshot
  som tilstrekkelig — utvides senere hvis behov

## 8. Relaterte dokumenter

- [TREEVIEW_PLAYBOOK.md](../TREEVIEW_PLAYBOOK.md) — UI-mønster for
  flagg-tabellen
- [src_struktur_og_vokabular.md](src_struktur_og_vokabular.md) —
  pages vs audit_actions (denne blir under MVA-fanen, ikke egen)
- [analyse_kolonnevisning_plan.md](analyse_kolonnevisning_plan.md) —
  kolonnehåndtering som flagg-tabellen bør følge
