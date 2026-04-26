# Stemme + handlingslogg — gransknings-økter med kontekst

**Sist oppdatert:** 2026-04-27

> ⚠️ **IKKE NESTE STEG.** Brukeren har signalisert at dette er et
> stykke frem i tid. Vi må først igjennom det grunnleggende:
> root-cleanup, pilot 24+ av src-migrasjonen, gjenstående polish
> i Analyse/Saldobalanse/Reskontro, og andre plan-doc'er før denne.
> Denne planen er dokumentert SÅ den ligger trygt for fremtiden,
> ikke som en kø-jobb. Selv Lag 1 (action-logging-rammeverket) skal
> ikke startes før mer basic ting er på plass.
>
> Se også [ai_bilag_agent_plan.md](ai_bilag_agent_plan.md) — denne
> planen er grunnmuren for AI-agenten, og begge har samme "vent til
> basics er ferdig"-status.

Plan for "gransknings-økt"-funksjonalitet i Utvalg: revisor klikker
"start økt" og appen logger både hva som blir gjort (klikk, bilag-
oppslag, filter-endringer) og hva som blir sagt (lokal transkripsjon
av tale). Begge med presise tidsstempler. Senere kan dataene brukes
manuelt (revisor leser tilbake), eller — på sikt — av en AI-agent som
kobler tale og handlinger sammen via tidsaksen.

Dette er **endgame-grunnmuren** for AI-agent-visjonen
([ai_bilag_agent_plan.md](ai_bilag_agent_plan.md), Nivå 4): når lyd og
strukturert handlingsdata finnes som tidslinje, blir LLM-grounding
trivielt. Men selv uten AI gir dette enorm verdi som
revisjonsdokumentasjon.

## 1. Hvorfor dette løser et reelt problem

ISA 230 krever at revisor dokumenterer *hva* som ble gjort, *når*, og
*hvorfor*. I dag tar dette timer å skrive ned i etterkant — etter at
de ferskeste tankene allerede er borte.

**"Lonely auditor"-problemet:** Revisor husker hvorfor en transaksjon
ble flagget i øyeblikket, men det er vanskelig å artikulere det 3
uker senere. Lyd + handlingslogg = automatisk begrunnelses-spor.

**Junior-onboarding:** Senior-revisorens resonnement fanges opp så
junior kan lære av faktiske vurderinger, ikke bare lærebok-eksempler.

**Kvalitetskontroll og tilsyn:** Full sporbarhet uten ekstra arbeid.
ISA 220 og DNR-tilsyn — du har audit-trail som viser akkurat hva
revisor så og tenkte i øyeblikket.

## 2. Brukerens-design (avklart 2026-04-27)

- **Økt-basert, ikke alltid-på.** Brukeren klikker "🎙️ Start
  gransknings-økt"; opptak og handlingslogg starter samtidig.
  Tydelig banner viser at opptak pågår.
- **Per klient.** Hver økt lagres under aktiv klients mappe, ikke
  globalt. Slettes når klient slettes.
- **Action-logging kun når økt er aktiv.** Ikke alltid-på. Enklere
  mental modell og personvern.
- **Brukerkontroll alltid:** Stop, slett, forkast, fortsett.

## 3. Naturlig brukerflyt

```
1. Revisor jobber normalt i Utvalg
2. Vil gjøre en runde gransking av leverandørgjeld → klikker
   "🎙️ Start gransknings-økt" (knapp i status-bar eller toolbar)
3. App viser banner: "Opptak pågår — klient: Spor Arkitekter
   AS | Økt #47 | 00:03:15"
4. Mikrofon kjører lokalt (Whisper); handlingslogg kjører
5. Revisor:
   - Åpner bilag 212 → logges {ts, action: "open_bilag", bilag: "212"}
   - Sier "denne fakturaen fra BRAGE er ny i år, undersøker..."
   - Søker på leverandør "BRAGE" i analyse-fanen
   - Sier "han er nær, sjekker aksjonærregister"
   - Åpner BRREG-popup
6. Klikker "⏹ Stopp" → dialog: "Lagre / forkast / fortsett"
7. Velger "Lagre" → økten arkiveres med navn (default: dato + klient)
8. Senere: revisor (eller AI senere) kan se gjennom — tidslinje med
   handlinger venstre, transkripsjon høyre, lyd avspillbar
```

## 4. Lag-inndeling

Hvert lag bygger på det forrige, men hvert lag gir egen verdi.

### Lag 1 — Action-logging-rammeverk + session manager (~1 uke)

**Hva:**
- Ny modul `src/audit_session/` (eller `src/shared/audit_session/`)
- `start_session(client, year)` / `stop_session(save=True)` /
  `discard_session()`
- En `AuditSession`-klasse som holder økt-state og logger handlinger
- JSONL-fil per økt: `clients/<navn>/years/<år>/audit_sessions/<session_id>/actions.jsonl`
- Session manifest: `manifest.json` med metadata (start, stopp,
  varighet, bruker, klient, år, hvilke moduser/faner brukt)

**Handlinger som logges (start enkelt, utvid):**
- Klient/år byttet
- Fane byttet (Analyse, Saldobalanse, A07 osv.)
- Bilag åpnet (bilag-nr, klient, år)
- Filter satt (søketekst, retning, periode, beløp)
- Markering: konto/bilag/RL valgt
- Eksport kjørt (hvilken rapport)
- Handling utført (RH-XX flagget, kommentar lagt til)
- Voucher-PDF åpnet (bilag-nr)
- BRREG-oppslag (orgnr)

**Format:**
```json
{"ts": "2026-04-27T14:03:22.153Z", "session_id": "...", "type": "open_bilag",
 "klient": "Spor Arkitekter AS", "år": "2025",
 "bilag": "212", "konto": "4500", "kontonavn": "Refunderbare tjenester"}
```

**Verdi alene (uten lyd, uten AI):**
- Audit trail / "hva gjorde jeg i sted?"
- ISA 230-dokumentasjon
- Statistikk: hvor lang tid bruker jeg på hver klient?
- Debug-data hvis noe blir rart

**Tekniske valg:**
- Async write så GUI ikke blokkeres
- Buffer i minnet, flush hvert sekund
- Toolbar-knapp + status-bar-indikator (samme som monitoring-systemet)

### Lag 2 — Lyd-opptak + lokal transkripsjon (~1-2 uker)

**Hva:**
- Mikrofon-opptak når økt aktiv (PyAudio eller sounddevice)
- Lokal transkripsjon via Whisper (whisper.cpp eller faster-whisper)
- Fil-strukturen:
  ```
  clients/<navn>/years/<år>/audit_sessions/<session_id>/
    ├── manifest.json
    ├── actions.jsonl
    ├── audio.opus           ← komprimert lyd-opptak
    └── transcript.jsonl     ← {ts, segment, text} per setning
  ```

**Tekniske valg:**
- **Whisper-modell:** `small` eller `medium` lokalt — gode på norsk,
  ~1-3 sek per setning på vanlig laptop. Større modeller for høyere
  kvalitet hvis maskinen tåler det.
- **Lyd-format:** Opus (~10 KB/sek) eller MP3. WAV er for stort.
- **Live vs batch:** Start med batch (transkriber etter at økten er
  ferdig). Live-transkripsjon krever streaming-modus og er kompleks.
- **Push-to-talk eller alltid-på under økt:** Begynn med alltid-på
  under aktiv økt — enklere. Push-to-talk kan komme som forbedring.

**Privacy-prinsipper (kritisk):**
- **Lyd forlater ALDRI maskinen** — verken til Whisper-API eller
  noen annen sky-tjeneste. Lokal Whisper er hele poenget.
- Visuell indikator (rød LED-lignende ikon) alltid synlig når
  mikrofon er aktiv
- Transkripsjon vises i sanntid (eller etter pause) så brukeren ser
  hva som blir fanget
- Ett-klikk "slett opptak" tilgjengelig alltid

**Verdi alene (uten AI):**
- Revisor kan høre/lese tilbake egen vurdering
- Bygges automatisk inn i arbeidspapir-tekst (kopier-lim)
- Junior kan lære av senior-økter

### Lag 3 — Økt-viewer (~½ uke)

**Hva:** En egen popup eller fane for å se gjennom lagrede økter
for aktiv klient.

```
┌─────────────────────────────────────────────────────────────┐
│ Gransknings-økter — Spor Arkitekter AS, 2025               │
├─────────────────────────────────────────────────────────────┤
│ ☐ #47   2026-04-27 14:03   25 min   Filter: leverandører  │
│ ☐ #46   2026-04-25 09:30   12 min   Bilag: 200-250        │
│ ☐ #45   2026-04-22 11:15    8 min   A07-avstemming        │
└─────────────────────────────────────────────────────────────┘

Når en økt åpnes:
┌──────────────────┬──────────────────────────────────────────┐
│ TIDSLINJE        │ TRANSKRIPSJON              [▶ Spill av]  │
│                  │                                          │
│ 14:03 Åpnet 212  │ 14:03  "ok, så denne fakturaen fra      │
│ 14:04 Søk: BRAGE │         BRAGE er ny..."                  │
│ 14:05 BRREG-     │ 14:04  "han er nær, sjekker             │
│       oppslag    │         aksjonærregister"                │
│ ...              │ ...                                      │
└──────────────────┴──────────────────────────────────────────┘
```

**Verdi alene:** Direkte revisjonsdokumentasjon. Eksporter til
arbeidspapir.

### Lag 4 — AI-grounding / korrelasjon (kommer fra AI-bilag-agent-planen)

**Hva:** LLM får handlingslogg + transkripsjon + standard regnskaps-
kontekst som input. Kan resonnere som beskrevet i
[ai_bilag_agent_plan.md](ai_bilag_agent_plan.md) Nivå 3-4.

**Hvorfor er Lag 1-3 grunnmuren:** Tidslinjen + transkripsjon + alle
de andre kontekst-lagene (struktur + dokumenter + metodikk) gir
LLM-en en rikdom av grounding-data ingen generell assistent har
tilgang til.

## 5. Lagrings-arkitektur (per klient)

```
data_dir/clients/<klient_navn>/
  years/<år>/
    audit_sessions/
      <session_id>/                  ← kataloger sortert kronologisk
        manifest.json                ← metadata
        actions.jsonl                ← handlingslogg
        audio.opus                   ← komprimert lyd (Lag 2)
        transcript.jsonl             ← transkripsjon (Lag 2)
        notes/                       ← evt. brukernotater
```

Session_id-format: `2026-04-27_140315_<short-hash>` for kronologi +
unikhet.

**Versjonering:** Aldri endre lagrede økter. Hvis revisor vil rette
noe, opprett en `notes/correction_<ts>.md` fil. Sletting er OK
(eksplisitt brukerhandling).

**Eksport:** Hver økt skal kunne eksporteres som ZIP for
arbeidspapir-vedlegg.

## 6. Tekniske valg som må tas

### 6.1 Whisper-deployment
- **whisper.cpp:** C++-kompilert, raskt på CPU, Norwegian støttet
- **faster-whisper:** Python-bindinger, GPU-akseleration mulig
- **Mistral/distill-Whisper:** mindre, raskere, men kvalitetsforskjell
- **Anbefalt:** Test alle tre med norsk revisor-tale på laptop-klasse
  hardware (Intel i7, 16 GB RAM)

### 6.2 Action-deteksjon
- Sentrall hook-system: hvert sted i koden som trigger en handling
  kaller `audit_session.log_action(type, **context)`
- Eller: monitoring-systemet ([src/monitoring/](../../src/monitoring/))
  utvides — det fanger allerede mange events
- **Anbefaling:** Bygg på monitoring-eventene, supplerer med eksplisitte
  audit-events for ting som er revisjonsfaglig viktige (RH-flagget,
  utvalg sendt, eksport kjørt)

### 6.3 GUI-integrasjon
- Status-bar nederst: knapp "🎙️ Start økt" / banner "OPPTAK 00:03:15"
- Globalt tilgjengelig fra alle faner
- Hurtigtast (Ctrl+Shift+R)?
- Bekreftelsesdialog ved første gangs bruk: "Stemme blir transkribert
  lokalt og lagret for klient X. Lyden forlater ikke maskinen."

## 7. Privacy-prinsipper (ufravikelige)

1. **Lyd forlater aldri maskinen** uten eksplisitt samtykke per økt.
2. **Tydelig visuell indikator** alltid synlig under opptak.
3. **Per-økt slett** tilgjengelig fra dialogen som lukker økten.
4. **Bulk-slett pr. klient** i Admin-fanen.
5. **Aldri opptak ved klient-bytte** uten spørsmål — hvis aktiv økt
   pågår når bruker bytter klient: dialog "Stopp og lagre, eller
   fortsett under ny klient?"
6. **GDPR-vennlig design:** økter er tydelig "behandling", med formål
   ("revisjonsdokumentasjon"), kontroller for innsyn/sletting/
   portabilitet (eksport).
7. **Dokumenter for kunde:** når revisor setter opp Utvalg første gang,
   tydelig forklaring av hva som lagres + samtykke.

## 8. Hva vi IKKE bygger

- **Cloud-transkripsjon** — lyd må kjøres lokalt
- **Alltid-på opptak** — kun når brukeren eksplisitt starter
- **Cross-klient-arkiv** — per klient, ikke globalt
- **Sentralt revisjons-firma-arkiv** — hver bruker eier sine egne
  økter på sin maskin
- **Auto-sletting** — sletting er alltid eksplisitt brukerhandling
- **Emosjonsanalyse / vurdering av tonefall** — kun ord, ikke
  paralingvistikk
- **Live-anbefalinger fra LLM under økt** — kommer i Lag 4, men
  også der: revisor signerer alt

## 9. Avhengigheter på tvers av lag

| Avhengighet | Lag 1 | Lag 2 | Lag 3 | Lag 4 |
|---|---|---|---|---|
| Klient/år-mapping | ✓ | ✓ | ✓ | ✓ |
| Action-events fra GUI | ✓ kreves | – | ✓ | ✓ |
| Lokal Whisper-installasjon | – | ✓ kreves | – | nyttig |
| Mikrofon-tilgang | – | ✓ kreves | – | – |
| Audit-trail / sporbarhet | ✓ kreves | ✓ | ✓ | ✓ kreves |
| LLM-API | – | – | – | ✓ kreves |

## 10. Foreslått sekvens hvis vi går videre

1. **Lag 1 minimal MVP** (~3-5 dager)
   - `src/audit_session/`-modul
   - Start/stop/discard knapp i status-bar
   - Logg 5-7 viktigste handlinger (klient-bytte, fane-bytte, bilag-
     åpnet, filter-satt, eksport, høyreklikk-handlinger)
   - JSONL-fil per økt under klient
   - Manifest.json med metadata

2. **Lag 3 økt-viewer (uten lyd ennå)** (~2 dager)
   - Popup som viser lagrede økter for aktiv klient
   - Tidslinje-visning
   - Slett / eksporter ZIP

3. **Pilot på din egen maskin med 1-2 klienter** (~1 uke jobbing)
   - Bruk det selv for å se hva som faktisk er nyttig
   - Hvilke handlinger savner du i loggen?
   - Hvor blir dataene mest verdifulle?

4. **Beslutning: gå videre til Lag 2 (lyd) eller polish Lag 1+3?**
   - Hvis Lag 1+3 er nyttig nok alene → polish
   - Hvis du savner stemmen → Lag 2

5. **Lag 2 lyd + transkripsjon** (~1-2 uker når Lag 1+3 er stabil)

6. **Lag 4 AI-grounding** følger AI-bilag-agent-planen

## 11. Hvorfor dette er strategisk

- **Null AI-avhengighet for Lag 1-3** — virker fra dag 1, gir verdi
  uavhengig av om vi noensinne legger til AI
- **Forsterker AI-bilag-agent-visjonen** — når lyden + handlingene er
  strukturert, blir LLM-grounding 10× kraftigere enn det ville vært
  basert på bare regnskapsdata
- **Differensiering i markedet** — ingen kjente norske revisjonsverktøy
  har dette. Kombinert med eksisterende Utvalg-funksjonalitet
  (SAF-T/RL/A07/handlinger) blir det en pakke ingen kan matche
- **Revisjonsdokumentasjon "for free"** — løser ISA 230-byrden uten
  ekstra arbeid for revisor

## 12. Relaterte plan-dokumenter

- [ai_bilag_agent_plan.md](ai_bilag_agent_plan.md) — fire-nivå AI-
  visjonen som denne grunnmuren legger til rette for
- [analyse_pivot_plan.md](analyse_pivot_plan.md) — pivot/Excel-eksport
  for ad-hoc analyse
- [src_struktur_og_vokabular.md](src_struktur_og_vokabular.md) —
  hvor `audit_session`-modulen bør ligge
- monitoring-systemet i [src/monitoring/](../../src/monitoring/) —
  kan gjenbrukes for action-event-fanging
