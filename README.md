# DocuMind — High Accuracy v2

A locally-run PDF question-answering application built with FastAPI. Version 2 is optimized for **low latency, focused answers, and document-grounded accuracy**.

The included knowledge base is the University of Delhi, School of Open Learning — Undergraduate Prospectus 2026–27.

## What changed in v2

### ⚡ Faster question answering
- PDFs are parsed and indexed once; query-time code **never reopens/reparses the PDF**.
- Uses the already-loaded numpy vector index plus a lightweight lexical index.
- A high-recall retrieval candidate pool is used before reranking.
- The full selected evidence is preserved for high-accuracy generation; query-time truncation is avoided.
- Simple questions remain focused through the answer prompt and validator; generation uses the configured LLM.
- LLM output budgets are selected by question type.

### 🎯 Less unnecessary information
- A deterministic query classifier selects an answer mode:
  - `exact_fact`
  - `list`
  - `procedure`
  - `comparison`
  - `page`
  - `deep`
  - `conversation`
- The answer prompt explicitly says to answer **only what was asked**.
- Retrieved passages are compressed to relevant local snippets before generation.
- A validator/repair path is retained only for strong false "not found" answers, avoiding unnecessary second LLM calls for ordinary short answers.
- Previous conversation context is limited to recent user questions and is never treated as factual evidence.

### 🔎 Better retrieval
- Hybrid retrieval combines vector similarity and lexical matching.
- Exact headings, names, phrases and terminology receive strong ranking signals.
- Section titles are preserved in returned evidence.
- Page numbers remain attached to every chunk.

## Architecture

```text
PDF upload
   │
   ▼
OFFLINE INGESTION
   ├─ PDF extraction
   ├─ header/footer cleanup
   ├─ heading detection
   ├─ chunking
   └─ hashing-vector index
          │
          ▼
   Persisted document index
          │
          ├───────────────┐
          ▼               ▼
   Vector retrieval   Lexical retrieval
          │               │
          └───────┬───────┘
                  ▼
              Reranking
                  │
                  ▼
           Evidence selection
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
  Direct extraction     LLM generation
  (simple facts)        (complex questions)
        │                   │
        └─────────┬─────────┘
                  ▼
            Output validation
                  │
                  ▼
             Final answer
```

## Project structure

```text
app/
├── auth/
├── chat/
├── database/
├── rag/
│   ├── embeddings.py
│   ├── ingestion.py
│   ├── chunking.py
│   ├── vector_store.py
│   ├── retriever.py
│   ├── query_router.py       # v2 query classification
│   ├── generator.py          # focused generation + validation
│   └── pipeline.py           # indexed-once orchestration
├── static/
└── templates/

data/
├── pdf/
├── processed/
└── vector_store/

test/
```

## Installation

```bash
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and configure Ollama Cloud. The included `.env` is preconfigured for the cloud model; change `SECRET_KEY` for your own deployment.

For Ollama / Ollama Cloud:

```env
LLM_PROVIDER=ollama
LLM_MODEL=gpt-oss:120b-cloud
OLLAMA_HOST=http://localhost:11434
OLLAMA_TIMEOUT=600
LLM_MAX_TOKENS=4096
```

Install the Python SDK and sign in to Ollama before using the cloud model:

```bash
pip install -U ollama
ollama signin
ollama pull gpt-oss:120b-cloud
```

The application connects to the local Ollama daemon at `OLLAMA_HOST`. Ollama routes the `-cloud` model through Ollama Cloud after `ollama signin`. `OLLAMA_URL` remains supported as a backward-compatible alias for `OLLAMA_HOST`. The application does not need a separate Ollama Cloud API key in `.env`.

## Run

```bash
python run.py
```

Then open:

```text
http://localhost:8000
```

## Important high-accuracy settings

```env
RETRIEVAL_TOP_K=10
RETRIEVAL_MIN_SCORE=0.18
RERANK_CANDIDATES=80
LLM_MAX_TOKENS=4096
MAX_HISTORY_MESSAGES=8
INDEX_VERSION=2
```

The `INDEX_VERSION` forces an index rebuild when retrieval/index structure changes.

## Reindexing

The application automatically rebuilds when:
- the source PDF changes,
- chunking settings change,
- embedding settings change,
- the index version changes.

You can also use the existing authenticated `/admin/reindex` endpoint.

## Tests

```bash
pytest -q
```

The test suite covers authentication, persistence, chunking, retrieval accuracy and answer-repair behavior.

## Security note

Do not commit a real `.env` file or API credentials. The distributable project uses `.env.example`; create your own `.env` locally.

## Design principle

DocuMind v2 follows:

**Retrieve less → verify harder → answer smaller.**

The LLM should not be responsible for searching the entire document or deciding how much unrelated context to return. Retrieval, evidence selection, and answer formatting are separate stages so simple questions remain fast and focused.

## Automatic answer-format selection

DocuMind classifies each question before generation. The classifier is deterministic and does not use an LLM. It selects `simple`, `list`, or `table` output strategy while factual content still comes only from retrieved PDF evidence.

Table mode is selected for explicit table requests and strongly structured requests such as fee structures, schedules, semester-wise/category-wise information, comparisons, and name/designation lists. Table answers are validated for consistent Markdown columns before being shown.

The web UI renders valid Markdown tables as real responsive HTML tables with horizontal scrolling on narrow screens. Model-generated HTML is never inserted directly into the page.
