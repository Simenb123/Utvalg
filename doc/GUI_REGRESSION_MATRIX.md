# GUI Regression Matrix og Gates

Dette dokumentet beskriver minste testnivaa per boelge for store GUI-features i `Utvalg-1`.

## Felles prinsipper
- Hver boelge maa ha:
  - enhetstester for ny logikk
  - headless GUI-naere tester for state, controllers og view-builders
  - minst en manuell smoketest paa reelle klientdata
- Popupvinduer er kun tillatt for filvalg, admin og avanserte noedverktoey.
- Performance skal vurderes paa store SAF-T-/dataset-caser foer hver gate.

---

## Gate 1: Analyse, A07 og MVA

### A07 — Scenarioer

| # | Scenario | Starttilstand | Handling | Forventet resultat | Moduler |
|---|----------|---------------|----------|-------------------|---------|
| A1 | Last A07-data | Datasett lastet, A07-fane aktiv | Klikk "Last A07" | A07-koder vises i hoyre liste, GL-kontoer i venstre | page_a07 |
| A2 | Kun aktive filter | A07 lastet, mange 0-kontoer | "Kun aktive" avhuket (standard) | 0-kontoer skjult, mappede kontoer beholdes | page_a07: filter_control_gl_df |
| A3 | Tryllestav | A07 lastet, koder uloste | Klikk "Tryllestav" | Forslag genereres, beste forslag markert groent | page_a07 |
| A4 | Bruk forslag | Forslag generert for valgt kode | Klikk "Bruk forslag" | Mapping oppdatert, kode markert som Sjekk | page_a07 |
| A5 | Drag/drop mapping | GL-konto valgt, A07-kode valgt | Dra konto til A07-kode | Konto tildeles koden, GL-liste oppdatert | page_a07 |
| A6 | Fjern mapping | Konto mappet til kode | Velg konto i "Mappede kontoer", klikk "Fjern valgt" | Mapping fjernet, konto vises som umappet | page_a07 |
| A7 | Eksporter | A07 ferdig mappet | Klikk "Eksporter" | Excel-fil generert med korrekte tall | page_a07 |
| A8 | Gjenapning | A07 eksportert, app lukket | Aapne app, last A07 igjen | Mapping gjenopprettet fra lagring | page_a07, a07_feature/storage |
| A9 | Detaljpanel kompakt | Velg kode med forslag | Klikk kode i A07-liste | "Valgt: {kode}" tittel, kompakt meta-linje, effekt-sammendrag uten duplikat | page_a07 |
| A10 | Tom A07 | Ingen data lastet | Aapne A07-fanen | Tom arbeidsflate uten feilmeldinger | page_a07 |

### MVA — Scenarioer

| # | Scenario | Starttilstand | Handling | Forventet resultat | Moduler |
|---|----------|---------------|----------|-------------------|---------|
| M1 | MVA-pivot | Datasett med MVA-koder | Velg "MVA-kode" i aggregerings-dropdown | MVA-koder per termin vises i pivot | page_analyse_mva |
| M2 | MVA-oppsett | MVA-pivot aktiv | Klikk "MVA-oppsett" | Dialog for MVA-kodemapping aapnes | mva_config_dialog |
| M3 | Kontoutskrift-import | MVA-pivot aktiv | Handlinger > MVA-avstemming > importer kontoutskrift.xlsx | Kontoutskrift parset, data lastet | mva_avstemming |
| M4 | Avstemming | Kontoutskrift importert | Verifiser HB vs innrapportert per termin | Differanser vises, avvik markert roedt | mva_avstemming_dialog |
| M5 | MVA-eksport | Avstemming gjennomfoert | Klikk "Eksporter" i avstemmingsdialogen | Excel med MVA-avstemming og MVA per kode | mva_avstemming_excel |
| M6 | MVA-innstillinger bevart | MVA-oppsett konfigurert | Lukk og aapne app | Regnskapssystem og kodemapping bevart | regnskap_client_overrides |
| M7 | MVA uten MVA-data | Datasett uten MVA-kolonner | Velg "MVA-kode" i dropdown | Tom pivot, ingen krasj | page_analyse_mva |

### Analyse — Scenarioer

| # | Scenario | Starttilstand | Handling | Forventet resultat | Moduler |
|---|----------|---------------|----------|-------------------|---------|
| AN1 | Last datasett | App startet | Last SAF-T via Dataset-fanen | Analyse oppdateres med kontodata | page_analyse, page_dataset |
| AN2 | Konto-pivot | Datasett lastet | Velg "Konto" i aggregerings-dropdown | Kontoer med sum og antall vises | page_analyse_pivot |
| AN3 | RL-pivot | Datasett + SB lastet | Velg "Regnskapslinje" i dropdown | Regnskapslinjer med IB/Endring/UB vises | page_analyse_rl |
| AN4 | Bytt visning | RL-pivot aktiv | Bytt "Visning" til "Saldobalansekontoer" | SB-tre vises med kontoer for valgt RL | page_analyse_sb |
| AN5 | Drill SB-konto | SB-visning aktiv | Dobbeltklikk paa en konto | Bytt til TX-visning, filtrert paa valgt konto | page_analyse_sb |
| AN6 | Skjul nulllinjer | Konto-pivot med 0-kontoer | Huk av "Skjul 0" | Kontoer med saldo=0 skjult | page_analyse_pivot |
| AN7 | Skjul sumposter | RL-pivot med sumlinjer | Huk av "Skjul sigma" | Sigma-sumlinjer fjernet fra pivot | page_analyse_rl |
| AN8 | Kommentar konto | Konto-pivot aktiv | Hoyreklikk konto > "Kommentar..." | Dialog aapnes, kommentar lagres, ikon vises i pivot | page_analyse_columns, page_analyse_pivot |
| AN9 | Kommentar RL | RL-pivot aktiv | Hoyreklikk RL > "Kommentar..." | Dialog aapnes, kommentar lagres, blaatt ikon + tekst | page_analyse_columns, page_analyse_rl |
| AN10 | Tilleggsposteringer | RL-pivot aktiv | Handlinger > Tilleggsposteringer, legg til en postering | Postering lagret, "(N)" vises ved checkbox | page_analyse, tilleggsposteringer |
| AN11 | Inkluder AO | Tilleggsposteringer lagret | Huk av "Inkl. AO" | Pivot og SB oppdatert med AO-justeringer | page_analyse_rl, page_analyse_sb |
| AN12 | Motpost-analyse | Kontoer valgt i pivot | Handlinger > Motpost-analyse | Motpost-dialog aapnes med valgte kontoer | views_motpost_konto |
| AN13 | Nr-seriekontroll | Kontoer valgt i pivot | Handlinger > Nr.-seriekontroll | Nr-serie dialog med gap-analyse | views_nr_series |
| AN14 | Eksport regnskapsoppstilling | RL-pivot aktiv | Handlinger > Eksporter regnskapsoppstilling | Excel-fil med regnskapsoppstilling | analyse_regnskapsoppstilling_excel |
| AN15 | Periodefilter | Datasett lastet | Dra periodevelger til mnd 3-9 | Pivot og TX filtrert til valgt periode | page_analyse_filters_live |
| AN16 | Kontoserie-filter | Datasett lastet | Klikk av kontoserie 5 (utgifter) | Kun kontoer i serien 5xxx vises | page_analyse_filters_live |
| AN17 | Retningsfilter | Datasett lastet | Velg "Debet" i retnings-dropdown | Kun debetposteringer vises | page_analyse_filters_live |
| AN18 | Fjoraarskolonner | RL-pivot med fjoraars-SB | Verifiser UB fjor, Endring fjor, Endring % | Fjoraarsdata vises med riktige tall | previous_year_comparison |
| AN19 | Aarsspesifikk mapping | Mapping lagret for 2024 | Last 2025 datasett for samme klient | 2025 har egen mapping, 2024 brukes som forslag | regnskap_client_overrides |

### Analyse TB-only — Scenarioer

| # | Scenario | Starttilstand | Handling | Forventet resultat | Moduler |
|---|----------|---------------|----------|-------------------|---------|
| TB1 | TB-only indikator | Kun SB lastet, ingen transaksjoner | Aapne Analyse | "Kun saldobalanse" vises i toolbar | page_analyse |
| TB2 | TX-dropdown deaktivert | TB-only modus | Sjekk TX-visning dropdown | Dropdown er disabled, SB-visning aktiv | page_analyse |
| TB3 | RL-pivot fungerer | TB-only modus | Velg "Regnskapslinje" | RL-pivot vises med IB/Endring/UB fra SB | page_analyse_rl |
| TB4 | Hovedbok-indikator | Full datasett med transaksjoner | Aapne Analyse | "Hovedbok" vises i toolbar | page_analyse |
| TB5 | SB-visning fungerer | TB-only modus | Bytt til SB-kontovisning | Kontoer vises med SB-data | page_analyse_sb |

### Edge cases — Scenarioer

| # | Scenario | Starttilstand | Handling | Forventet resultat | Moduler |
|---|----------|---------------|----------|-------------------|---------|
| E1 | Tom datasett | Ingen data lastet | Aapne Analyse | Tom pivot, ingen krasj | page_analyse_pivot |
| E2 | Stort datasett | SAF-T med >100k transaksjoner | Last og naviger | Pivot rendres <2s, scrolling smooth | page_analyse |
| E3 | Gjenapning av state | Kommentarer + mapping + AO lagret | Lukk og aapne app | Alle innstillinger bevart | regnskap_client_overrides |
| E4 | Bytt klient | Klient A aktiv | Last data for klient B | Klient B sine innstillinger lastes | session, regnskap_client_overrides |
| E5 | Filtre nullstilt | Diverse filtre aktive | Klikk "Nullstill" | Alle filtre tilbake til standard | page_analyse |

---

## Gate 2: Konsolidering MVP

| # | Scenario | Starttilstand | Handling | Forventet resultat | Moduler |
|---|----------|---------------|----------|-------------------|---------|
| K1 | Opprett prosjekt | App aapen | Opprett klient/aar konsolideringsprosjekt | Prosjekt lagret, arbeidsflate klar | consolidation |
| K2 | Importer TB | Prosjekt opprettet | Importer TB for selskap A og B | Begge TBer lastet og normalisert | consolidation |
| K3 | Map kontoer | TBer importert | Map vesentlige kontoer til konsernlinjer | Mapping lagret, review-status oppdatert | consolidation |
| K4 | Elimineringsbatch | Mapping ferdig | Foer minst en elimineringsbatch | Batch lagret, balansekrav sjekket | consolidation |
| K5 | Kjoer konsolidering | Elimineringer foert | Kjoer konsolidering | Konsolidert resultat generert uten feil | consolidation |
| K6 | Eksporter | Konsolidering kjoert | Eksporter arbeidsbok | Excel med alle ark generert | consolidation |
| K7 | Gjenapning | Alt lagret | Lukk og aapne app | State gjenopprettet komplett | consolidation |
| K8 | TB-only flyt | Ingen hovedbok | Fulfoer K1-K6 kun med TB | Hele flyten fungerer uten hovedbok | consolidation |

## Gate 3: Reskontro v1

| # | Scenario | Starttilstand | Handling | Forventet resultat | Moduler |
|---|----------|---------------|----------|-------------------|---------|
| R1 | Aapne kunder | Datasett med kundekontoer | Aapne reskontro, modus Kunder | Motpartsoversikt med saldo vises | reskontro |
| R2 | Filtrer motpart | Motpartsoversikt aktiv | Filtrer paa tekst eller saldo!=0 | Liste filtrert korrekt | reskontro |
| R3 | Drill til TX | Motpart valgt | Klikk motpart | Transaksjoner for motpart vises | reskontro |
| R4 | Bytt modus | Kunder aktiv | Bytt til Leverandoerer | Leverandoer-motparter vises | reskontro |
| R5 | Risikosignaler | Motpart uten ID | Sjekk risikoindikatorer | "Mangler ID" flagg synlig | reskontro |
| R6 | Konto/periodefilter | Reskontro aktiv | Filtrer paa konto og periode | Resultater filtrert korrekt | reskontro |

## Gate 4: Rapporter og arbeidspapirer

| # | Scenario | Starttilstand | Handling | Forventet resultat | Moduler |
|---|----------|---------------|----------|-------------------|---------|
| RP1 | Excel-utdata | Analyse/A07/MVA ferdig | Eksporter Excel | Korrekt formatert Excel-fil | export |
| RP2 | PDF-utdata | Analyse ferdig | Generer PDF | PDF med riktige tall og layout | export |
| RP3 | Output vs GUI | Excel/PDF generert | Sammenlign tall med GUI | Tall stemmer overens | export |
| RP4 | Revisjonskontekst | Output generert | Verifiser kobling | Output kan kobles til klient/aar/analyse | export |
