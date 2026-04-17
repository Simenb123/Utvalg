# Flowchart Editor

Standalone Tkinter-editor for flowcharts med Mermaid-import og -eksport.
Pakken ligger under [flowchart_editor/](../flowchart_editor/) og er uavhengig
av resten av Utvalg-1 — den kan kjøres alene via
`python -m flowchart_editor`, direkte fra `app.py` (F5 i VS Code), eller via
`start_flowchart.bat`.

## Hensikt

Intern verktøy for å skisse og vedlikeholde flytdiagrammer (revisjonsprosess,
arbeidsflyter, arkitekturskisser) som kan:
- Lagres lokalt som `.fcjson` (JSON, full modell).
- Importeres/eksporteres som Mermaid slik at samme diagram kan deles i
  Markdown, Miro, Notion, osv.

## Status (2026-04-12)

MVP (M1–M7) fullført + visnings-iterasjon fullført. **45 tester grønne.**

**Hva funker:**
- Fire node-former (rect, round, rhombus, subroutine) med farge + label.
- Fire kant-stiler (`-->`, `---`, `-.->`, `==>`) med valgfrie labels.
- Subgraphs med egen retning (TB/LR/BT/RL) og dedikert headerbar.
- Mermaid-import av `.mermaid`, `.mmd` og Markdown med ` ```mermaid `-blokker.
- Automatisk kompakt grid-layout ved import.
- Ortogonale L-/Z-formede kanter (ikke diagonale).
- Auto-høyde på noder basert på antall label-linjer.
- Zoom (musehjul, ankret til peker), panorering (venstreklikk-dra),
  fit-to-content.
- Edge-modus: klikk kilde → klikk mål for å opprette kant.

**Hva er utelatt (bevisst, kan gjøres senere):**
- Kurvede bezier-kanter.
- Grid-snap ved drag.
- Høyreklikk-meny / dobbeltklikk-for-ny-node.
- Hover-effekter.
- Obstacle-avoidance i kant-ruting (kanter kan krysse noder hvis mange
  tilbake-kanter går gjennom samme korridor).
- Variabel node-bredde (holdes fast på 160 px for å bevare grid-justering).

## Arkitektur

Single-source-of-truth er `Diagram`-dataclass. Alle lag leser/skriver den:

```
┌──────────────────┐        ┌──────────────────┐
│ mermaid_parser   │──────► │                  │ ◄────── storage (JSON)
├──────────────────┤        │                  │
│ mermaid_export   │◄────── │     Diagram      │ ──────► storage (JSON)
└──────────────────┘        │                  │
                            │  nodes: dict     │
┌──────────────────┐        │  edges: list     │        ┌──────────────────┐
│ layout.py        │───────►│  subgraphs: dict │◄───────│ sidepanel.py     │
│ (auto_layout +   │        │  direction: TB/..│        │ (redigering)     │
│  fit_node_height)│        └──────────────────┘        └──────────────────┘
└──────────────────┘                  ▲
                                      │
                            ┌──────────────────┐
                            │ canvas_widget.py │
                            │  (render + input)│
                            └──────────────────┘
                                      ▲
                            ┌──────────────────┐
                            │ app.py           │
                            │  (EditorApp)     │
                            └──────────────────┘
```

### Moduloversikt

| Fil | Ansvar |
|---|---|
| [model.py](../flowchart_editor/model.py) | `Node`, `Edge`, `Subgraph`, `Diagram` dataclasses + to/from_dict. |
| [storage.py](../flowchart_editor/storage.py) | JSON-lagring av `.fcjson`. |
| [mermaid_parser.py](../flowchart_editor/mermaid_parser.py) | Linjebasert regex-state-machine som bygger `Diagram` fra Mermaid-subset. |
| [mermaid_export.py](../flowchart_editor/mermaid_export.py) | `Diagram` → Mermaid-tekst. |
| [layout.py](../flowchart_editor/layout.py) | Kompakt grid-layout per subgraph + auto-høyde på noder. |
| [canvas_widget.py](../flowchart_editor/canvas_widget.py) | `FlowchartCanvas` — rendring, seleksjon, drag, zoom, ortogonal kant-ruting. |
| [sidepanel.py](../flowchart_editor/sidepanel.py) | `PropertiesPanel` — dynamisk skjema for valgt node/kant/subgraph. |
| [toolbar.py](../flowchart_editor/toolbar.py) | Verktøylinje med callback-knapper. |
| [app.py](../flowchart_editor/app.py) | `EditorApp` — hovedvindu, menyer, kommandoer. |
| [style.py](../flowchart_editor/style.py) | Farger, fonter, layout-konstanter. |
| [__main__.py](../flowchart_editor/__main__.py) | Entrypoint for `python -m flowchart_editor`. |

## Viktige designvalg

### Dual-mode import-bootstrap
`app.py` må kunne kjøres både som modul (`python -m flowchart_editor`) og
direkte (F5 i VS Code). Løsningen:

```python
if __package__:
    from .canvas_widget import FlowchartCanvas, Selection
    # ... relative imports
else:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from flowchart_editor.canvas_widget import FlowchartCanvas, Selection
    # ... absolute imports
```

### Ortogonal kant-ruting
`canvas_widget._orthogonal_path(src, dst, direction)` returnerer 2–5 punkter:
- Vertikalt justerte noder (samme X): rett linje ned (2 punkter).
- Forover-kant: `src.bottom → midpoint_y → dst.top` (4 punkter, L/Z-form).
- Tilbake-kant: går ut til siden (40 px margin), rundt, og inn på toppen
  (5 punkter) — unngår å krysse egne noder.
- Retnings-aware: speilvendt logikk for BT/LR/RL.

### Kompakt grid-layout
`layout._layout_grid` velger `cols = max(2, min(GRID_COLS_MAX, ceil(√N)))` og
plasserer noder i rad-hovedrekkefølge etter topologisk sortering. Subgraphs
plasseres i et ytre 2-kolonners grid. Tilbake-kanter bryter ikke rekkefølgen
fordi Kahn-sorteringen faller tilbake på input-rekkefølge ved sykler.

### Auto-høyde på noder
`fit_node_height(node)` beregner høyde fra antall linjer i label:
```
height = max(60, line_count * 18 + 24)
```
Kalles i `auto_layout` og i `sidepanel.commit_label` — så bruker ser noden
vokse mens de skriver.

### Subgraph headerbar
I stedet for label flytende i øvre venstre hjørne, rendres nå en dedikert
farget stripe (`SUBGRAPH_HEADER_HEIGHT = 30`) øverst i subgraph-rammen med
label sentrert. Medlemmer plasseres under stripen via `SUBGRAPH_PADDING`.

## Mermaid-subset som støttes

```
flowchart TB|LR|BT|RL           (også "graph" og "TD" → "TB")
subgraph ID ["Label"]
  direction TB|LR|BT|RL
end
A[Rekt]   A(Rund)   A{Rombe}   A[[Subrutine]]
A --> B     A --- B     A -.-> B     A ==> B
A --label--> B     A -- label --> B     A -->|label| B
A --> B --> C       (kjedet)
style NODE fill:#xxx,stroke:#xxx,color:#xxx
%% kommentarer ignoreres
```

Ikke-forståtte linjer listes i import-rapport-dialog etter import.

## Dataformat

**`.fcjson`** (versjon 1):
```json
{
  "version": 1,
  "direction": "TB",
  "nodes": {"A": {"id": "A", "label": "Start", "shape": "rect", "x": 100, "y": 50, ...}},
  "edges": [{"from_id": "A", "to_id": "B", "label": "", "arrow": "-->"}],
  "subgraphs": {"P1": {"id": "P1", "label": "Fase 1", "direction": "TB", ...}}
}
```

## Tester

```bash
.venv\Scripts\python.exe -m pytest flowchart_editor/tests/ --no-cov
```

**Dekning (45 tester):**
- `test_model.py` (11) — dataclass-kontrakter, rename_node, remove_*.
- `test_storage.py` (3) — JSON round-trip.
- `test_mermaid_parser.py` (15) — alle Mermaid-varianter + full
  revisjonsprosess-fil som E2E.
- `test_mermaid_export.py` (9) — shapes, arrows, subgraphs, styles.
- `test_layout.py` (7) — auto-høyde, grid-unike-posisjoner, subgraphs
  side-om-side.

## Kjente svakheter / mulige neste steg

1. **Obstacle-avoidance i kanter.** Hvis mange kanter fra samme side deler
   korridor, kan de overlappe. Kan løses med stagger-offset (40/55/70 px)
   per edge-indeks.
2. **Manuell rerun av auto-layout.** Nå kjøres `auto_layout` kun ved import.
   Bør eksponeres som verktøylinje-knapp ("Layout om").
3. **Lagret diagram beholder gamle posisjoner.** Hvis bruker åpner en gammel
   `.fcjson` etter auto-høyde-endringen, må de evt. kalle `fit_node_height`
   manuelt. Kan gjøres automatisk ved load.
4. **Ingen undo/redo.** Hver endring skriver direkte til modellen.
5. **Kanter kan ikke bøyes manuelt.** Rutingen er algoritmisk og ikke
   justerbar fra UI.
6. **Subgraph-medlemskap krever ID-kjennskap.** Ingen drag-into-subgraph i UI.

## Hoppe inn igjen

For å fortsette arbeidet:
1. Åpne [flowchart_editor/](../flowchart_editor/) i VS Code.
2. F5 på `app.py` (eller `python -m flowchart_editor`).
3. Fil → Importer Mermaid → `examples/revisjonsprosess.md` for realistisk
   testdiagram.
4. `python -m pytest flowchart_editor/tests/ --no-cov` før enhver endring.

Plan for forrige iterasjon lå på
`C:\Users\ib91\.claude\plans\distributed-knitting-abelson.md` (visnings-
forbedringer — nå fullført).
