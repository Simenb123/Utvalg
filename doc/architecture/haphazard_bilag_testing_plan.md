# Haphazard bilag-testing — granskning som dokumenteres automatisk

**Sist oppdatert:** 2026-04-27

> ⚠️ **IKKE NESTE STEG.** Brukeren har avklart at vi først må igjennom
> mer grunnleggende arbeid (root-cleanup, polish, andre plan-doc'er).
> Denne planen er dokumentert SÅ ideen ligger trygt for fremtiden,
> ikke som en kø-jobb.

Plan for haphazard sampling som førsteklasses funksjon i Utvalg:
revisor browser transaksjoner ad-hoc, gransker bilag i split-view,
lagrer test som "haphazard"-utvalgsmetode — og resultatet inngår
automatisk i den totale bilagskontroll-historikken med korrekt
metode-klassifisering.

## 1. Hvorfor

**ISA 530** anerkjenner haphazard sampling som gyldig metode (når
statistisk sampling ikke er nødvendig). I praksis foregår det slik
i dag:

- Revisor ser på en transaksjon, blir nysgjerrig
- Klikker seg gjennom bilaget (eksternt PDF-vindu eller papir)
- Vurderer om alt er riktig
- Skriver ned konklusjon i Word/Excel hvis noe avvikende
- Glemmer å registrere det som del av total bilagskontroll
- Eller registrerer det manuelt under "annet"

**Problemet:** Haphazard-tester forsvinner ofte fra dokumentasjonen.
Senere (revisorens egen kvalitetskontroll, DNR-tilsyn) er det
vanskelig å vise at metoden ble brukt systematisk.

**Løsningen:** Når split-view-popupen er åpnet for et bilag, gi
brukeren en "Lagre granskning"-knapp som registrerer testen i
historikken med metode-flagg "Haphazard" + brukerens korte
konklusjon.

## 2. Brukerflyt (foreslått)

```
1. Revisor i Analyse → ser en transaksjon (f.eks. høy beløp + ny leverandør)
2. Dobbeltklikk → split-view popup åpnes
3. Studerer bilag-føring + PDF side-ved-side
4. Tar en vurdering (ok / avvik / ikke-konkluderende)
5. Klikker "Lagre granskning..."
6. Liten dialog:
     ┌────────────────────────────────────────────────┐
     │ Lagre haphazard-granskning                    │
     ├────────────────────────────────────────────────┤
     │ Bilag: 11148                                  │
     │ Sum:   2 908,00                               │
     │ Konto: 6903 (Mobiltelefon)                    │
     │                                                │
     │ Konklusjon: ( ) OK                            │
     │             ( ) Avvik — beskriv:              │
     │             ( ) Ikke-konkluderende            │
     │                                                │
     │ Notat (valgfritt):                            │
     │ ┌──────────────────────────────────────────┐  │
     │ │                                          │  │
     │ └──────────────────────────────────────────┘  │
     │                                                │
     │            [Avbryt]  [Lagre]                  │
     └────────────────────────────────────────────────┘
7. Lagres i clients/<navn>/years/<år>/audit_tests/haphazard.jsonl
8. Vises i Dokumentkontroll-fanen som del av total kontroll-status
```

## 3. Datamodell

```json
{
  "test_id": "ha-2026-04-27-14-32-15-abc123",
  "test_method": "haphazard",
  "klient": "Air Cargo Logistics AS",
  "år": "2025",
  "bilag_nr": "11148",
  "transaksjon_id": "...",
  "konto": "6903",
  "kontonavn": "Mobiltelefon",
  "beløp": 2908.00,
  "dato": "2025-05-05",
  "konklusjon": "ok",
  "notat": "Faktura fra Telenor stemmer med bestilling. OK.",
  "granskede_av": "snb",
  "granskede_dato": "2026-04-27T14:32:15Z",
  "session_id": null,
  "pdf_attached": true,
  "pdf_path_relative": "vouchers/extracted/11148.pdf"
}
```

## 4. Lag-inndeling

### Lag 1 — "Lagre granskning"-knapp i split-view (~½ dag)

- Knapp i bunn av `BilagSplitView`-popupen
- Åpner liten dialog (3 radio-knapper + notat-felt)
- Skriver til `clients/<navn>/years/<år>/audit_tests/haphazard.jsonl`
- Suksess-indikator i popupen ("✓ Lagret 14:32")

### Lag 2 — Visning i Dokumentkontroll-fanen (~½ dag)

- Eget panel "Haphazard-granskninger" i Dokumentkontroll
- Viser liste: Dato | Bilag | Konto | Beløp | Konklusjon | Notat
- Filtrer på status (OK / Avvik / Ikke-konkluderende)
- Klikk åpner samme split-view (re-trekk PDF)

### Lag 3 — Inkludert i total bilagskontroll (~½ dag)

- Bilagskontroll-rapport (Excel-eksport) viser haphazard-tester som
  egen seksjon med metode-klassifisering
- Statistikk: "X bilag haphazard-testet (av Y mulige). Z avvik."
- Knytte sammen med statistisk utvalg fra Utvalg-fanen for total
  dekningsgrad

### Lag 4 — Knytning til handlinger (RH-XX) (~½ dag)

- Hver test kan knyttes til en eller flere revisjonshandlinger
- "Denne haphazard-testen oppfyller kravet i RH-12 (Test av
  varekostnader > vesentlighet)"
- Vises i Handlinger-fanen som dokumentert evidens

### Lag 5 — Voice/AI-integrasjon (avhenger av andre planer)

- Hvis [voice_action_log_plan.md](voice_action_log_plan.md) er
  implementert: tale-transkripsjon under granskning lagres som
  notat automatisk
- Hvis [ai_bilag_agent_plan.md](ai_bilag_agent_plan.md) Nivå 3+:
  AI kan foreslå konklusjon basert på bilag-innhold + kontekst
  (revisor godkjenner)

## 5. Hva vi IKKE bygger

- **Erstatte statistisk sampling** — haphazard er supplement, ikke
  erstatning
- **Auto-konklusjon** — revisor må alltid signere
- **Eksternt API for å hente haphazard-data** — det er lokal
  revisjons-historikk, ikke client-data
- **Separat "haphazard mode"** — det er ren browse + grand-test, ikke
  egen modus

## 6. Avhengigheter

| Avhengighet | Status |
|---|---|
| Bilag-PDF-visning (split-view) | ✓ Implementert (commit `ea12933`) |
| Voucher-indeks per klient/år | ✓ Implementert (`document_control_voucher_index`) |
| Klient/år-mapping | ✓ Implementert |
| Bilagskontroll-rapport-rammeverk | ✓ Eksisterer i Dokumentkontroll-fanen |
| Bruker-/team-info | ✓ Eksisterer (Visena-integrasjon) |
| Handlinger-fanen med RH-IDs | ✓ Eksisterer |

**Konklusjon:** Alt grunnlag finnes. Implementering er en ren
påbygging.

## 7. Forretningsmessig verdi

- **Compliance:** ISA 530 og ISA 230 dokumentasjon dekkes automatisk
- **Tidsbesparelse:** Eliminerer manuell loggføring av haphazard-tester
- **Sporbarhet:** Senere (kvalitetskontroll, tilsyn) kan revisjonen
  vise nøyaktig hvilke bilag som ble haphazard-testet, hvorfor, og
  med hvilken konklusjon
- **Differensiering:** Få (om noen) norske revisjonsverktøy har
  haphazard som førsteklasses funksjon

## 8. Relaterte plan-dokumenter

- [ai_bilag_agent_plan.md](ai_bilag_agent_plan.md) — agent-modus kan
  ta haphazard-resultater inn i kontekstgrunnlag
- [voice_action_log_plan.md](voice_action_log_plan.md) — tale-
  transkripsjon under granskning kan auto-fylle notat-feltet
- [analyse_pivot_plan.md](analyse_pivot_plan.md) — pivot-resultater
  kan brukes til å identifisere haphazard-kandidater (f.eks.
  uvanlige beløp)
