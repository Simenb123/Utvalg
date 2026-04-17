# flowchart_editor

Standalone Tkinter-editor for flowcharts med Mermaid-import og -eksport.
Pakken er uavhengig av Utvalg-1-koden; den kjøres med `python -m flowchart_editor`.

## Oppstart

```bash
# Fra Utvalg-1 rot
.venv\Scripts\python.exe -m flowchart_editor
# eller via batch-filen
start_flowchart.bat
```

## Funksjoner

- **Noder**: rektangel, avrundet, rombe, subrutine. Alle har farge- og label-felt.
- **Kanter**: fire stilarter (`-->`, `---`, `-.->`, `==>`), valgfri label.
- **Subgraphs**: grupper som tegnes som ramme rundt medlemmene. Hver subgraph kan
  ha sin egen retning (TB/LR/BT/RL).
- **Mermaid**: Importer `.mermaid`, `.mmd` eller Markdown-filer som inneholder en
  ```` ```mermaid ```` -blokk. Importerte diagrammer får automatisk en lag-basert
  layout som kan finjusteres manuelt. Eksport skriver tilbake samme subset.
- **Lagring**: `.fcjson` (JSON) i `flowchart_editor/diagrams/`.

## Tastatursnarveier

| Tast              | Handling                |
|-------------------|-------------------------|
| Ctrl+N            | Nytt diagram            |
| Ctrl+O            | Åpne fil                |
| Ctrl+S            | Lagre                   |
| Ctrl+Shift+S      | Lagre som…              |
| Del               | Slett valgt element     |
| Esc               | Avbryt kant-modus       |
| Musehjul          | Zoom (ankret til peker) |
| Venstreklikk-dra  | Panorere tomt lerret    |

## Arbeidsflyt for kant-opprettelse

1. Trykk **+ Kant** på verktøylinjen.
2. Klikk kildenoden.
3. Klikk mål-noden. Kanten opprettes og kant-modus avsluttes.
4. Esc avbryter modusen uten å lage kant.

## Mappestruktur

```
flowchart_editor/
  app.py              # EditorApp (hovedvindu)
  canvas_widget.py    # FlowchartCanvas (tegne + interaksjon)
  sidepanel.py        # PropertiesPanel (redigering av seleksjon)
  toolbar.py          # Verktøylinje
  model.py            # Node/Edge/Subgraph/Diagram dataclasses
  storage.py          # JSON-lagring
  mermaid_parser.py   # Mermaid → Diagram
  mermaid_export.py   # Diagram → Mermaid
  layout.py           # Auto-layout for importerte diagrammer
  style.py            # Fargepalett, fonter, konstanter
  diagrams/           # Lagrede diagrammer (.fcjson)
  examples/           # Eksempel-Mermaid-filer
  tests/              # pytest-tester
```

## Kjøre tester

```bash
.venv\Scripts\python.exe -m pytest flowchart_editor/tests/ --no-cov
```

## Subset av Mermaid som støttes

```
flowchart TB|LR|BT|RL
subgraph ID ["Label"]
  direction TB|LR|BT|RL
end
A[Rekt]   A(Rund)   A{Rombe}   A[[Subrutine]]
A --> B     A --- B     A -.-> B     A ==> B
A --label--> B     A -- label --> B     A -->|label| B
A --> B --> C    (kjedet)
style NODE fill:#xxx,stroke:#xxx,color:#xxx
%% kommentarer ignoreres
```

Ikke-forståtte linjer listes i en import-rapport-dialog etter import.
