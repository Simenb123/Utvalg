# Analyse-siden — mulige UX-forbedringer

Dette er en liste over ideer og observasjoner som kan være verdt å se nærmere på.
Ingen av punktene er besluttet — de er åpne for drøfting og prioritering.

---

## Toolbar og filtre

- **Toolbar er kompakt med 4 rader** — avanserte filtre (Min/Maks beløp, Bilag,
  Motpart, Kontoserier) brukes sjelden. Mulig å skjule disse bak en
  «Avansert ▾»-knapp slik at skjermen virker mindre overveldende ved første øyekast.

- **Kontoserier vises som 10 separate checkboxer (0–9)** — kunne vært et mer
  kompakt element, f.eks. multi-select dropdown eller chip-velger.

- **«Vis: 200»-grensen er lite synlig** — hvis resultatet er trunkert ser brukeren
  ikke at det finnes flere rader. Mulig å vise en advarsel, f.eks.
  «⚠ Viser 200 av 543 rader».

- **Nullstill-knappen gir ingen visuell tilbakemelding** på om filtre er aktive
  eller ikke. En liten indikator (f.eks. uthevet knapp) når noe er filtrert
  kunne gjort det tydeligere.

---

## Periode

- **Slideren viser måneder som tall (1–12)** — månedsnavn (Jan–Des) ville vært
  mer intuitivt. Og gjerne et lite tekstfelt ved siden av som viser valgt periode
  tydelig, f.eks. «Apr–Des 2024».

---

## Høyre panel

- **Høyre panel er tomt ved oppstart** — viser bare tomme kolonner med instruksjonen
  «Velg en regnskapslinje». Mulig å bruke plassen bedre med en visuell
  placeholder eller en minioppsummering av valgt regnskapslinje (UB, avvik
  fra i fjor) allerede før man klikker ned i detaljer.

---

## Handlinger-menyen

- **Menyen har ~16 punkter uten visuell gruppering** — kan bli lettere å lese
  med separatorer mellom naturlige grupper, f.eks.:
  - *Eksport* (Excel, PDF)
  - *Analyse* (Motpost, Nøkkeltall, Avstemming)
  - *Innstillinger* (Kolonner, Standard kolonner)

---

## Tabellen (venstre pivot-panel)

- **Kolonner kan ikke sorteres ved å klikke på overskriften** — `ui_treeview_sort`
  finnes allerede i prosjektet og brukes på Reskontro-siden. Kunne kobles inn her også.

- **Ingen statuslinje** under tabellen med f.eks. «N kontoer vist • Sum UB: X».

---

## Tastatur og navigasjon

- Mulige hurtigtaster: `F5` for refresh, `Ctrl+F` for å fokusere søkefeltet,
  `Ctrl+E` for eksport til Excel.

---

*Sist oppdatert: 2026-04-05*
