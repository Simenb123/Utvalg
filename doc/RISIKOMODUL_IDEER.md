# Risikomodul og vesentlighetsgrenser

> Status: **Idé** — ikke besluttet. Drøftes her før evt. flytt til TODO.md.

---

## Bakgrunn

Revisjonsplanlegging krever to ting som i dag gjøres manuelt utenfor Utvalg:
1. **Vesentlighetsgrenser** — beregning av materiality (overall, performance, trivial)
2. **Risikovurdering** — identifikasjon av risikoer per regnskapslinje/påstand

Et planleggingslag i Utvalg ville knytte disse to sammen med de analysefunksjonene
som allerede finnes (IB/UB-kontroll, HB-SB-matching, finansiell rapport, konsolidering).

---

## Del A — Vesentlighetsgrenser

### Konsept

Beregningen følger "audit lite"-metodikk eller ISA 320:

| Basisstørrelse | Typisk % | Kommentar |
|----------------|----------|-----------|
| Totalinntekter | 0,5–1 % | Vanlig for ordinære foretak |
| Totaleiendeler | 1–2 % | Alternativ for holdingselskaper |
| Egenkapital | 3–5 % | Alternativ for kapitalintensive |
| Resultat før skatt | 5–10 % | Ustabil — vurder normalisert snitt |

**Performance materiality** settes typisk til 60–75 % av overall materiality.
**Trivial threshold** settes typisk til 3–5 % av overall materiality.

### Hva Utvalg allerede har

- Finansiell rapport henter totalinntekter, totaleiendeler og egenkapital fra SAF-T/HB
- BRREG-klienten (`brreg_client.py`) kan hente historiske nøkkeltall
- Begge kan brukes som basisstørrelser uten ekstra datainnhenting

### Forslag til UI

```
┌─────────────────────────────────────────────────────┐
│  Vesentlighetsgrenser                               │
├─────────────────────────────────────────────────────┤
│  Basis:       [Totalinntekter ▼]   Kr: 45 200 000  │
│  Prosent:     [0,75 %        ]     = 339 000        │
│  Performance: [75 %          ]     = 254 250        │
│  Trivial:     [5 %           ]     = 16 950         │
│                                                     │
│  [Beregn fra HB]  [Hent fra BRREG]  [Lagre]        │
└─────────────────────────────────────────────────────┘
```

Grensene lagres i sesjon/engasjementsfil og brukes som referansepunkter i:
- Dispose-analyse: flagg poster over performance materiality
- Utvalg: foreslå utvalgsstørrelse basert på populasjon vs vesentlighet
- Reskontro: marker åpne poster over performance materiality

---

## Del B — Risikovurdering per regnskapslinje

### Rammeverk

ISA 315 krever risikovurdering per **påstand** (eksistens, fullstendighet, verdsettelse, etc.)
for vesentlige regnskapslinjer. Forslaget er et enkelt skjema der revisor scorer hver linje.

### Datamodell (forslag)

```json
{
  "risks": [
    {
      "regnr": 3000,
      "regnskapslinje": "Salgsinntekter",
      "assertions": ["completeness", "occurrence"],
      "inherent_risk": "high",
      "control_risk": "medium",
      "detection_risk": "low",
      "risk_factors": ["Inntektsmanipulasjon", "Periodisering"],
      "linked_actions": ["hb_sb_matching", "reskontro_kunde", "analytisk"]
    }
  ]
}
```

### Standardiserte risikofaktorer (forhåndsdefinerte)

Disse er typiske risikoområder fra ISA 240/315 som er relevante for norske SMB:

| Kategori | Eksempler |
|----------|-----------|
| Ledelsens overstyring | Manuelle bilag, uvanlige posteringer i perioden |
| Nærstående transaksjoner | Konserninterne, lån til eiere |
| Inntektsrisiko | Periodisering, fiktiv omsetning, returrisiko |
| Estimatrisiko | Avskrivninger, nedskrivninger, tapsavsetninger |
| Likviditetsrisiko | Going concern-indikatorer |

### Estimeringsusikkerhet

For regnskapslinjer med estimater kan Utvalg automatisk flagge linjer der:
- Endring fra IB til UB er uvanlig stor (> X % av vesentlighetsgrense)
- Avskrivningsprofil avviker fra historisk (via SAF-T-data)
- Manuell tekst-kommentar er lagt inn av revisor

Disse flaggene vises i Analyse-fanens RL-modus som et ikon eller farge på raden.

---

## Del C — Kobling til eksisterende Utvalg-funksjoner

Det er ikke nødvendig å bygge alt nytt. Risikovurderingen kan lenke til eksisterende
verktøy i Utvalg:

| Risiko | Eksisterende funksjon | Mangler |
|--------|-----------------------|---------|
| Fullstendighet (inntekt) | HB-SB matching | Kun matching, ikke risikokobling |
| Eksistens (kundefordringer) | Reskontro, åpne poster | — |
| Verdsettelse (lager/anlegg) | Dispose-analyse | Ikke formalisert |
| Periodisering | Analytisk (Analyse-fane, RL) | Ingen grensemarkering |
| Konserninterne | Konsolidering | Ikke koblet til risikoplanlegging |

Ideen er en "planleggingsfane" der revisor klikker på en risiko og får opp
en direktelenke til relevant analyse: «Kjør HB-SB matching for konto 1500».

---

## Del D — Estimert arbeidsmengde og prioritering

| Komponent | Størrelse | Prioritet |
|-----------|-----------|-----------|
| Vesentlighetsberegner (UI + lagring) | Liten (2–4t) | Høy — brukes hvert engasjement |
| Risikovurderingsskjema (CRUD + lagring) | Medium (1–2 dager) | Medium |
| Kobling risiko → Utvalg-funksjoner | Medium (1–2 dager) | Lav — nice to have |
| Estimeringsusikkerhet-flagging | Liten–Medium | Lav — kan vente |

**Anbefalt rekkefølge:** Start med vesentlighetsberegneren alene. Den er selvstendig,
gir umiddelbar verdi, og er ikke avhengig av risikovurderingsskjemaet.

---

## Åpne spørsmål

- [ ] Skal vesentlighetsgrensene lagres per engasjement (sesjonsfil) eller per klient (CRMSystem)?
- [ ] Ønsker vi en "audit lite"-formel hardkodet, eller skal revisor fritt velge basis og prosent?
- [ ] Skal risikovurderingen produsere et utskrivbart planleggingsdokument (PDF)?
- [ ] Er ISA 315-påstandene (assertions) relevante å ha eksplisitt i UI, eller er de for tekniske?
- [ ] Kobling til CRMSystem: skal ferdigstilte risikovurderinger synkroniseres tilbake til CRMSystem?
