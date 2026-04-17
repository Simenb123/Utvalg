# Fagchat — arkitektur og driftshåndbok

Fagchat er en RAG-basert (Retrieval Augmented Generation) AI-assistent integrert
som egen fane i Utvalg. Den svarer på faglige spørsmål ved å hente relevante
utdrag fra et lokalt fagbibliotek (ISA-standarder, lover, NRS, artikler m.m.)
og sende dem som kontekst til en OpenAI-modell. **Klientdata blir aldri sendt
til modellen** — kun spørsmål + fagkilder.

---

## 1. Oversikt — hva skjer når brukeren stiller et spørsmål?

```
┌─────────────┐   spørsmål    ┌──────────────┐   top-N chunks   ┌──────────┐
│ page_fagchat│ ────────────▶ │ rag_bridge   │ ────────────────▶│ ChromaDB │
│   (GUI)     │               │ make_context │                  │ (vektor) │
└─────────────┘               └──────────────┘   + BM25 hits    └──────────┘
       ▲                             │                                 ▲
       │ svar + kilder               │ formattert kontekst             │
       │                             ▼                                 │
       │                      ┌──────────────┐                         │
       │                      │  qa_service  │     system prompt       │
       │                      │  run_query   │     + kildeliste        │
       │                      └──────────────┘                         │
       │                             │                                 │
       │                             ▼                                 │
       │                      ┌──────────────┐                         │
       └──────────────────────│   OpenAI     │    Keyword-indeks       │
                              │ gpt-4o-mini  │    (BM25, JSON)         │
                              └──────────────┘                         │
                                                                       │
                      ┌────────────────────┐     indekseres med        │
                      │ kildebibliotek.json│ ───────────────────────── ┘
                      │ (198 kilder)       │    text-embedding-3-small
                      └────────────────────┘
```

---

## 2. Komponenter og filplassering

Fagchat er fordelt på to kodebaser som lever side om side:

| Repo | Mappe | Rolle |
|------|-------|-------|
| `Utvalg-1` | `page_fagchat.py` | GUI-fane (Tkinter). Sender spørsmål, viser svar + klikkbare kilder. |
| `Utvalg-1` | `doc/fagdatabase/` | Råkilder (PDF, .md, .xlsx) og genererte .txt-filer. |
| `openai`   | `src/rag_assistant/` | RAG-motor: indeksering, retrieval, LLM-kall. |
| `openai`   | `kildebibliotek.json` | Kildekatalog (metadata + filpeker for hver kilde). |
| `openai`   | `ragdb/` | ChromaDB-vektorindeks (≈330 MB) + BM25 keyword-indeks. |

### Oppslag av `openai`-repoet

[page_fagchat.py](../page_fagchat.py) har funksjonen `_find_openai_repo()` som
leter etter repoet i denne rekkefølgen:

1. `../openai` (ved siden av Utvalg-1) — **foretrukket, lokal utvikling**
2. `../../openai`
3. `./rag_engine/` (bundlet kopi)
4. Nettverksstier (`sources_dir/openai`, `data_dir/openai`) — kun fallback

Beslutning (april 2026): **Lokal kopi er autoritativ inntil fagchatten er
moden nok til å deles fra nettverk.** Se [MEMORY.md](../../../.claude/projects/c--Users-ib91-Desktop-DIV-VS-CODE-PROJECTS-pythonProject1/memory/MEMORY.md).

---

## 3. Fagbiblioteket (`kildebibliotek.json`)

Flat JSON-liste over alle kilder. Hver kilde har et stabilt ID, en doc_type,
og peker på én eller flere .txt-filer som indekseres.

### Eksempel

```json
{
  "id": "ISA-315",
  "title": "ISA 315 Identifisere og vurdere risikoer",
  "doc_type": "ISA",
  "files": ["C:/.../generated/isa/ISA-315.txt"],
  "tags": ["isa", "risikovurdering"],
  "metadata": { "language": "no" }
}
```

### doc_type-typer (per april 2026)

| doc_type    | Antall | Behandling i prompt | Siterbar |
|-------------|--------|---------------------|----------|
| ISA         | 42     | Primærkilde — «ISA-xxx §nn» | Ja |
| KRAV        | 37     | MÅ-krav fra ISA-ene | Ja |
| NRS         | 26     | Norske regnskapsstandarder | Ja |
| LOV         | 4      | RSL, SKL, SKFVL, SKBL | Ja |
| SJEKKLISTE  | 9      | Sjekklister og maler | Ja |
| ARTIKKEL    | 67     | Fagartikler, **Finanstilsynets tilsynsrapporter**, veiledninger | Ja (merkes `[ARTIKKEL]`) |
| KONTEKST    | 13     | Bakgrunn/fagbegreper | **Nei — filtreres ut av kildelisten** |

**Viktig gotcha:** ID-prefiksen og doc_type er uavhengige. F.eks. har
`KONT-TILSYN-GJENTAKENDE-FUNN` ID-prefiks `KONT-` (fordi filen ligger i
`kontekst/`-mappa) men doc_type `ARTIKKEL`. Det er `doc_type` som styrer
hvordan LLMen behandler kilden — ikke ID-navnet. Se
[qa_service.py:112-113](../../openai/src/rag_assistant/qa_service.py#L112-L113)
og [qa_service.py:173-174](../../openai/src/rag_assistant/qa_service.py#L173-L174).

---

## 4. Indeksering (`build_index.py`)

Kjøres manuelt når nye kilder er lagt til eller eksisterende .txt-filer er
endret. Bryter hver fil opp i chunks (default 1200 tegn, 200 tegn overlapp) og
upserter til ChromaDB + BM25.

### Kjøring

```bash
cd /c/Users/ib91/Desktop/DIV/VS\ CODE\ PROJECTS/openai
PYTHONIOENCODING=utf-8 python -m rag_assistant.build_index \
    --library kildebibliotek.json --wipe
```

`--wipe` tømmer hele ChromaDB-collection først (trygt ved full reindeks).
Uten `--wipe` brukes `purge_existing=True` som kun sletter chunks for kilder
i biblioteket (trygt ved inkrementell oppdatering).

### Artefakter som produseres

| Fil | Innhold |
|-----|---------|
| `ragdb/chroma.sqlite3` | ChromaDB SQL-lager (dokumenter + metadata) |
| `ragdb/<uuid>/` | HNSW-vektorindeks (data_level0.bin, header.bin, …) |
| `ragdb/keyword_index.json` | BM25 keyword-indeks for hybrid search |
| `kildebibliotek.anchors.json` | Anker-inventory for relasjonsekspansjon |

### Metadata som legges på hvert chunk

```python
{
  "source_id": "ISA-315",              # Stabil ID
  "source_title": "ISA 315 ...",
  "doc_type": "ISA",                   # Styrer filtrering/tagging
  "tags": "isa,risikovurdering",
  "anchor": "P13",                     # Paragrafanker (P13 = §13)
  "chunk_index": 7,
  "chunk_total": 129,
  "source_path": "C:/.../ISA-315.txt",
  "display_file": "C:/.../ISA 315.pdf" # PDF som åpnes ved klikk
}
```

### Antall chunks (april 2026)

17 814 chunks fra 198 kilder. Ved ny indeksering er dette den forventede
størrelsesordenen. Hvis `col.count()` er markant lavere — f.eks. 14 000 —
har en tidligere indeksering sannsynligvis blitt avbrutt mens en annen
fortsatt kjørte i bakgrunnen. Sjekk `chroma.sqlite3`-timestamp.

---

## 5. Retrieval (`rag_bridge.make_context`)

Hvert spørsmål hentes i tre trinn:

### 5.1 Source routing
Hvis spørsmålet eksplisitt nevner en kilde-ID (f.eks. "Hva sier ISA-315 §13?"),
pre-filtreres vektorsøket til den kilden via ChromaDB `where`-clause.

### 5.2 Hybrid search (vektor + keyword)
- **Vektor:** `collection.query(query_texts=[q], n_results=2N)` — semantisk søk på cosine similarity
- **Keyword:** BM25 på `keyword_index.json` — eksakt-ord treff
- **RRF fusion:** [`_rrf_merge()`](../../openai/src/rag_assistant/rag_bridge.py#L249) slår sammen listene med Reciprocal Rank Fusion. Treff som finnes i begge rangeres høyere. Topp-N overlever.

### 5.3 Relasjonsekspansjon
Hvis spørsmålet har en anker (f.eks. `§13`) og biblioteket har definerte
relasjoner (`kildebibliotek.json → relations`), hentes relaterte chunks fra
andre kilder med samme paragraf-anker. F.eks. ISA-315 §13 kan trekke inn
ISA-240 §16 hvis relasjonen er definert.

**Anker-fallback:** Hvis den spesifikke ankeren ikke finnes i målkilden,
prøves foreldre: `§1-1(1)[a]` → `§1-1(1)` → `§1-1`. Se
[rag_bridge.py:159-223](../../openai/src/rag_assistant/rag_bridge.py#L159-L223).

---

## 6. Kontekst-formattering og prompt

[`_format_chunk()`](../../openai/src/rag_assistant/rag_bridge.py#L141) lager
header for hvert chunk:

```
[ARTIKKEL] [KONT-TILSYN-GJENTAKENDE-FUNN P5]
Finanstilsynet har i tilsyn med revisorer…
```

- `[ARTIKKEL]` / `[KONTEKST]` kommer fra `doc_type`
- `[kilde-id anker]` kommer fra metadataene
- Primærkilder (ISA, NRS, LOV, KRAV) får ingen tag-prefiks

### System prompt

Bygges dynamisk i
[`build_system_prompt()`](../../openai/src/rag_assistant/qa_service.py#L141) —
kildelisten (`_build_source_list`) genereres fra `kildebibliotek.json` hver
gang en ny øktbegynner, så nye kilder blir automatisk tilgjengelige i prompten.
KONTEKST-kilder utelates fra listen.

Prompt-regler (i sammendrag):
1. Kun kontekst — si tydelig når svaret ikke finnes
2. Kildehenvisning med ID + paragraf
3. Norsk faglig språk, norsk revisjonsterminologi
4. Korte, strukturerte svar med sjekklister der relevant
5. Meta-spørsmål ("har du tilgang på X?") skal besvares positivt hvis
   konteksten inneholder relevante kilder

### Modeller

| Rolle | Default | Env-var |
|-------|---------|---------|
| Chat  | `gpt-4o-mini` | `OPENAI_CHAT_MODEL` |
| Embedding | `text-embedding-3-small` | `OPENAI_EMBED_MODEL` |

API-nøkkel leses fra `openai/.env`: `OPENAI_API_KEY=sk-...`

---

## 7. GUI ([page_fagchat.py](../page_fagchat.py))

- **Venstre panel:** Chat-feed (brukermeldinger + AI-svar med markdown-rendering)
- **Høyre panel:** Kildevisning. Klikk på en kilderef i svaret → åpner
  chunk-tekst + lenke til original-PDF
- **Verktøylinje:** `Bruk LLM`-toggle (av = kun retrieval, på = LLM-svar),
  `top_k`-slider
- **Feedback-knapper:** 👍/👎 på hvert svar, lagres til JSON for evaluering

Kall-flyten (tråd-basert, GUI blokkeres ikke):

1. `_send()` [page_fagchat.py:1249](../page_fagchat.py#L1249) — leser input, starter worker-tråd
2. Worker kaller `qa_service.run_query()` — returnerer `QueryOutcome`
3. Resultatet pushes på `queue.Queue`
4. `_poll_queue()` [page_fagchat.py:1310](../page_fagchat.py#L1310) — hovedtråden leser og rendrer

---

## 8. Drift og feilsøking

### Verifiser at indeksen er komplett

```python
import sys; sys.path.insert(0, 'src')
from rag_assistant.settings_profiles import load_settings
from rag_assistant.rag_index import get_or_create_collection
cfg = load_settings()
col = get_or_create_collection(db_path=cfg.db_path, collection_name=cfg.collection, embedding_model=cfg.embedding_model)
print(col.count())  # forventet ~17 800
```

### Sjekk at en bestemt kilde er indeksert

```python
res = col.get(where={'source_id': 'KONT-TILSYN-GJENTAKENDE-FUNN'}, include=['metadatas'])
print(len(res['ids']))  # > 0 hvis ok
```

### Test retrieval uten LLM

```python
from rag_assistant.rag_bridge import make_context
ctx, chunks = make_context("spørsmål", col, n_results=8,
                            library_path='kildebibliotek.json', db_path=cfg.db_path)
for c in chunks:
    m = c.metadata
    print(m.get('source_id'), m.get('doc_type'), m.get('anchor'))
```

### Vanlige problemer

| Symptom | Sannsynlig årsak | Løsning |
|---------|------------------|---------|
| "Jeg har ikke tilgang på X" når X er i biblioteket | Kilden har `doc_type=KONTEKST` og filtreres | Endre til `ARTIKKEL` i kildebibliotek.json og reindeks |
| `col.count()` << forventet | Forrige indeksering ble avbrutt | Kjør `build_index --wipe` på nytt |
| Nye kilder dukker ikke opp | Kildeliste caches i `_source_list_cache` | Restart Fagchat-fanen (eller hele appen) |
| `OPENAI_API_KEY mangler` | `.env` ikke lastet | Verifiser `openai/.env` eksisterer |
| Kilder vises ikke i sidepanel | `display_file` mangler eller filen er flyttet | Oppdater `display_file` i `kildebibliotek.json` |

---

## 9. Legge til nye kilder

Se [MEMORY.md → Fagdatabase arbeidsmetode](../../../.claude/projects/c--Users-ib91-Desktop-DIV-VS-CODE-PROJECTS-pythonProject1/memory/feedback_fagdatabase_workflow.md)
for etablert workflow.

Kort oppsummert:

1. Legg råkilden i `doc/fagdatabase/<kategori>/` (PDF, md, xlsx)
2. Generer en ren .txt-versjon under `doc/fagdatabase/generated/<kategori>/`
3. Legg til entry i `openai/kildebibliotek.json` med riktig `doc_type`
4. Kjør full reindeks: `python -m rag_assistant.build_index --library kildebibliotek.json --wipe`
5. Test i Fagchat med et spørsmål som bør treffe kilden

---

## 10. Hvordan vi jobber med å forbedre Fagchat

Fagchat er under utvikling. Kvaliteten forbedres iterativt langs fire akser:

### 10.1 Flere/bedre kilder
Den vanligste løftestangen. Ny kilde legges til kildebiblioteket → reindeks →
test. Når retrieval ikke finner noe relevant, er det som regel fordi kilden
ikke finnes — ikke at prompten er dårlig.

### 10.2 doc_type-klassifisering
`ARTIKKEL` vs `KONTEKST` er et bevisst valg, ikke et teknisk detalj:
- **ARTIKKEL** = kan siteres som kilde (tilsynsrapporter, fagartikler, veiledninger)
- **KONTEKST** = filtreres ut av kildelisten (ren bakgrunn, fagbegreper)

Hvis en kilde blir "usynlig" i svaret selv om den er indeksert, sjekk
doc_type først. Historikk: Finanstilsynets tilsynsrapporter (KONT-TILSYN-*)
ble først klassifisert som KONTEKST pga. ID-prefiksen, ble aldri sitert, og
måtte re-klassifiseres til ARTIKKEL.

### 10.3 Prompt-tuning
System prompten i
[qa_service.py:30-92](../../openai/src/rag_assistant/qa_service.py#L30-L92)
endres sjelden, men kirurgisk. Typiske endringer:
- Nytt meta-spørsmål som må håndteres ("har du tilgang på X?")
- Nytt terminologi-krav (norsk term som skal foretrekkes)
- Ny kildetype som må tagges annerledes

**Merk:** `_source_list_cache` caches kildelisten på modul-nivå — endringer
i kildebiblioteket krever restart av appen før prompten ser dem.

### 10.4 Evaluering
- **Feedback-knapper** i GUI (👍/👎) — kvalitativ signal per svar
- **Golden-eval** ([qa_service.py:303](../../openai/src/rag_assistant/qa_service.py#L303)) — kjør faste testspørsmål og sammenlign med forventede kilder. Brukes for å validere at en endring (ny kilde, prompt-endring, chunk-størrelse) ikke regresserer på spørsmål som allerede fungerte.

### 10.5 Typisk iterasjonsløp

```
1. Bruker rapporterer: "Fagchat finner ikke X"
2. Reprodusér → test retrieval uten LLM (make_context, n_results=8)
   - Kommer X ut i top-8? Hvis ja → prompt/filter-problem
   - Kommer X ikke ut? → retrieval-problem
3a. Retrieval-problem:
    - Er kilden i kildebiblioteket? (grep kildebibliotek.json)
    - Er den i ChromaDB? (col.get(where=source_id))
    - Stemmer doc_type? (ARTIKKEL/ISA/LOV… ikke KONTEKST?)
    - OCR-kvalitet på .txt-filen?
3b. Prompt/filter-problem:
    - Blir kilden filtrert av format_sources? (doc_type=KONTEKST?)
    - Nevner LLMen den i svaret i det hele tatt?
    - Juster doc_type eller system prompt
4. Reindeks om kildefiler/metadata endret (--wipe ved tvil)
5. Golden-eval for å sjekke at ingen etablerte spørsmål regresserer
```

### 10.6 Lærdommer så langt

- **OCR-kvalitet betyr alt.** Dårlig parset PDF (gjentakende headers, kontrolltegn `\x06`, `\ufffd`-bytes) gir dårlig retrieval. Rens kildefilene før indeksering. Se historikk for RSL/SKL/SKFVL/SKBL og NBS/NRS/ISRE-filer som måtte ryddes.
- **ID-navnet er ikke doc_type.** `KONT-*`-prefiks for en ARTIKKEL er forvirrende og bør unngås for nye kilder — velg f.eks. `TILSYN-*` eller `FT-*` i stedet.
- **Cache-invalidering.** `_source_list_cache` og `_kw_index_cache` krever restart. Ikke forvent at prompt-endringer slår inn umiddelbart.
- **Avbrutt indeksering er stille.** Hvis `col.count()` er markant lavere enn forventet etter en indeksering, har en tidligere prosess sannsynligvis overskrevet halve tilstanden. Kjør `--wipe` på nytt og verifiser.
- **Hybrid search er nødvendig.** Ren vektor-søk bommer på spørsmål med egennavn (lov-titler, selskapsnavn, paragrafnumre). BM25-komponenten fanger disse.
- **Meta-spørsmål krever egen prompt-regel.** LLMen sier gjerne "jeg har ikke tilgang" selv når konteksten inneholder relevante kilder. Se meta-spørsmål-blokken i system prompten.

---

## 11. Relaterte filer

- [page_fagchat.py](../page_fagchat.py) — GUI-fane
- [openai/src/rag_assistant/qa_service.py](../../openai/src/rag_assistant/qa_service.py) — system prompt, run_query, format_sources
- [openai/src/rag_assistant/rag_bridge.py](../../openai/src/rag_assistant/rag_bridge.py) — make_context, hybrid search, relasjonsekspansjon
- [openai/src/rag_assistant/build_index.py](../../openai/src/rag_assistant/build_index.py) — indeksering fra bibliotek
- [openai/src/rag_assistant/kildebibliotek.py](../../openai/src/rag_assistant/kildebibliotek.py) — `Library`-klassen
- [openai/kildebibliotek.json](../../openai/kildebibliotek.json) — kildekatalog
