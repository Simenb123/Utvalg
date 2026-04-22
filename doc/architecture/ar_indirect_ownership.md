# AR — Indirekte eierkjede (kryssreferanse, org-kart, drilldown)

**Moduler:**
- [ar_ownership_chain.py](../../ar_ownership_chain.py) — delt BFS-helper (`walk_indirect_chain`).
- [workpaper_klientinfo.py](../../workpaper_klientinfo.py) — Excel-kryssreferanse som matcher aksjonærer mot rolleinnehavere.
- [workpaper_export_klientinfo.py](../../workpaper_export_klientinfo.py) — henter data + bygger callback for indirekte oppslag.
- [page_ar_chart.py](../../page_ar_chart.py) — tegner direkte + indirekte noder i org-kartet.
- [page_ar_drilldown.py](../../page_ar_drilldown.py) — Toplevel-dialog for ekspanderbar inspeksjon av eierkjeden.

**Sist oppdatert:** 2026-04-21

## Formål

Aksjonærregisteret (RF-1086) viser kun **direkte** eierskap ett ledd opp.
I norske holding-strukturer er virkelige beslutningstakere ofte to–fire
ledd over klienten. Denne modulen følger kjeden oppover slik at både:

1. **Excel-kryssreferansen** kan flagge en person som **indirekte aksjonær**
   når hen både er rolleinnehaver i klienten og eier via en holding-kjede.
2. **Org-kartet** visuelt viser de indirekte leddene som stiplete bokser
   over de direkte eierne.
3. **Drilldown-dialogen** lar revisor grave videre oppover/nedover
   interaktivt uten å kjøre en ny Excel-eksport.

## BFS-helper — én kilde for kjeden

`walk_indirect_chain(start_owners, indirect_owners_fn, max_depth)` i
[ar_ownership_chain.py](../../ar_ownership_chain.py) er det eneste stedet
BFS-logikken finnes. Både Excel-kryssen og kart-rendereren kaller den.

**Kontrakt:**

- **Input:** liste av direkte eiere (fra `get_client_ownership_overview`)
  og en callback `indirect_owners_fn(orgnr)` som returnerer eiere for et
  gitt orgnr (typisk `ar_store.list_company_owners(orgnr, lookup_year)`).
- **Output:** `(chain_nodes, chain_break_orgnrs)` der
  - `chain_nodes` er prosesserte noder med `{orgnr, chain, depth, sub_owners}`.
    `chain` er liste av `(name, pct)` fra direkte holding opp til noden.
  - `chain_break_orgnrs` er orgnrs hvor callback ga tom liste — kjeden
    kunne ikke følges videre opp.
- **Invarianter:**
  - Kun selskaps-aksjonærer (ikke `person`/`unknown`) enqueues for videre
    rekursjon. Personer er alltid blader.
  - `visited`-sett beskytter mot sykler (f.eks. A eier B som eier A).
  - BFS stopper når `depth >= max_depth`.

## Dybdegrenser

| Bruker | `max_depth` | Begrunnelse |
|---|---|---|
| Excel-kryssreferanse | 5 | Gir samme match som revisorer har manuelt bekreftet i reelle klienter. `visited`-settet gjør det trygt å gå dypere. |
| Org-kart | 3 | Balanserer lesbarhet mot dekning. Dypere nivåer blir kjapt uleselige i kart-view. Excel er primærkilden for konklusjonen. |

Konstantene ligger hhv. i `build_klientinfo_workpaper`-kallet i
[workpaper_klientinfo.py](../../workpaper_klientinfo.py) og som
`_CHART_INDIRECT_MAX_DEPTH` i [page_ar_chart.py](../../page_ar_chart.py).

## Flyt — Excel-kryssreferanse

```
export_klientinfo_workpaper (UI-knapp)
  ↓
_indirect_owners(orgnr) callback
  ↓ (bruker ar_store.list_company_owners(orgnr, lookup_year))
build_klientinfo_workpaper
  → build_cross_matches
      → walk_indirect_chain  ← DELT HELPER
      → for hver chain_node: match sub_owners mot rolleinnehavere
  → Kryssreferanse-ark + konklusjons-tekst på forsiden
```

Kjernen er at `build_cross_matches` mottar selve `chain_nodes` og kjører
personnavn-matching mot `roller` (fra BRREG). Matchene får
`match_type="indirect"` og en tekstlig kjedebeskrivelse.

## Flyt — org-kart

```
refresh_org_chart → _build_model
  → _build_indirect_entries
      → _resolve_indirect_lookup_year (overview.owners_year_used || page._year)
      → walk_indirect_chain  ← DELT HELPER
      → bygg én "indirect entry" per sub_owner per chain_node
  → _compute_default_layout (direkte noder) + _layout_indirect_entries (nye rader)
  → _render_from_model tegner stiplete bokser + kanter
```

Nodtyper som skrives inn i `_chart_node_actions`:
- `kind="indirect_owner"` — selskap oppover, videre ekspanderbart.
- `kind="indirect_person"` — person/unknown, ikke ekspanderbart.
- *(ingen action)* — break-placeholder ("Ikke i AR for året").

Bokser bruker egne `pos_key`-prefikser for layout og posisjons-persistens:
`chain:<orgnr>`, `chain_leaf:<parent_orgnr>:<id>`, `chain_break:<orgnr>`.
Edge-tags inkluderer forelder-nøkkelen (`edge:line:<pk>:<parent_pk>`) for
å være unike ved **diamant-eierskap** (samme orgnr er sub_owner av to
forskjellige holdinger).

## Flyt — drilldown

Dobbeltklikk i kartet (handler i [page_ar_chart.py](../../page_ar_chart.py)
`on_chart_double_click`) ruter `owner`/`indirect_owner`/`indirect_person`
til `ARPage._open_owner_drilldown`, som åpner
`_OwnerDrilldownDialog` i [page_ar_drilldown.py](../../page_ar_drilldown.py).

Dialogen er en `ttk.Treeview` med lazy ekspansjon. Hver selskaps-rad får
en placeholder-node `__placeholder__<iid>` som byttes ut med faktiske
eiere første gang raden åpnes (`<<TreeviewOpen>>`). Selskap uten data for
`lookup_year` får innslaget «Ikke importert for {år}» slik at revisor ser
hvor kjeden brytes.

Drilldown bruker **ikke** `walk_indirect_chain` — ekspansjon skjer ett
ledd om gangen på brukerens initiativ, og hver rad er en direkte
`ar_store.list_company_owners`-spørring mot SQLite.

## Break-diagnostikk

Kjeden brytes typisk fordi et mellomledds-holding ikke er importert fra
RF-1086 for `lookup_year`. Diagnostikk på tre steder:

1. **Callback-nivå** ([workpaper_export_klientinfo.py](../../workpaper_export_klientinfo.py) `_indirect_owners`):
   INFO-log «Indirekte eierskap: ingen treff for orgnr=… i AR-året …».
2. **BFS-nivå**: `walk_indirect_chain` returnerer `chain_break_orgnrs`.
3. **Kart-visning**: break-orgnrs blir placeholder-bokser over foreldre-holdingen.

## Kjente gotchas

### Register-år vs. klient-år

`lookup_year` velges som `owners_year_used` (fra overview) → fallback
`page._year` / `session.year`. Hvis klienten har innleveringshull, kan
`owners_year_used` være et **eldre** år enn klientåret — og da må
holdings i kjeden også ha samme år i registeret, ellers brytes kjeden.
Revisor må se INFO-loggen for å forstå hvorfor.

### Diamond-eierskap

Hvis samme orgnr eier to forskjellige holdings som begge eier klienten,
blir det én BFS-node (pga. `visited`-sett) men **to edges** i kartet.
Render deduper bokser via `drawn_pos_keys`, men edge-tags må inkludere
forelder for å unngå at `redraw_edges_for_node` flytter feil linje.

### Personer som blader

Personer enqueues aldri for videre BFS. Kjeden terminerer alltid på
person-nivå eller ved `max_depth`/break. Dette er korrekt fordi
RF-1086 ikke registrerer «eiere» av en privatperson — men betyr at
holdingstrukturer med en tom fysisk eier (kun ASA-styrer e.l.) vil se
brutte kjeder i diagnostikken.

## Testdekning

- [tests/test_workpaper_klientinfo.py](../../tests/test_workpaper_klientinfo.py)
  `TestMultiLevelIndirect::test_indirect_chain_three_levels` — sikrer at
  dypere kjeder (3+ ledd) faktisk blir flagget når `max_indirect_depth=5`.
- [tests/test_page_ar_chart.py](../../tests/test_page_ar_chart.py):
  - `test_build_model_includes_indirect_nodes` — BFS-resultat når opp i kart-modellen.
  - `test_build_model_records_chain_break_when_owners_empty` — break-placeholder registreres.
  - `test_chart_double_click_on_indirect_owner_opens_drilldown` — routing til drilldown.

Ved nye bugs her: dokumenter med dato, symptom, årsak, fix — per
konvensjonen i [memory/project_doc_architecture](../../../memory/project_doc_architecture.md).
