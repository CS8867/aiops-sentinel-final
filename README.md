# Sentinel RCA Agent

An autonomous AI agent that detects production incidents, traces them to root cause, generates a corrected file, and commits the fix to GitHub — end to end, without human intervention.

Built with LangGraph, Google Gemini, ChromaDB, and the Model Context Protocol (MCP).

---

## How It Works

The agent is a multi-node LangGraph pipeline triggered from a Streamlit dashboard. Each node is a discrete reasoning step:

```
Upload CSV + Logs
       │
       ▼
┌─────────────┐
│   Triage    │  Gemini reads service metrics and classifies: INCIDENT or HEALTHY
└──────┬──────┘
       │ INCIDENT
       ▼
┌─────────────┐
│ Log Parser  │  Gemini extracts the relevant stack trace from raw application logs
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  RCA Fixer  │  ChromaDB retrieves the matching source file via semantic search.
│             │  Gemini performs root cause analysis and generates a corrected file.
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ GitHub Push │  MCP GitHub server commits the generated fix to the target branch.
└─────────────┘
```

If triage returns `HEALTHY`, the pipeline short-circuits — no further action is taken.

---

## Key Design Decisions

**LangGraph for orchestration** — Each pipeline stage is an isolated node with explicit typed state. This makes the flow inspectable at runtime and each step independently testable.

**AST-aware code indexing** — Source files are chunked using a tree-sitter `LanguageParser` rather than naive character splitting. This keeps syntactic units (functions, classes) atomic in the vector store, which improves retrieval precision compared to splitting at arbitrary character counts.

**Last-frame retrieval heuristic** — When parsing a traceback, the agent queries the vector store using only the innermost stack frame (the crash site), where the bug has the highest probability of residing. This avoids noise from framework frames higher up the call stack.

**MCP for GitHub integration** — The `@modelcontextprotocol/server-github` Node.js process is spawned as an async subprocess. The Python agent communicates over stdio using an MCP `ClientSession`, decoupling the GitHub API surface from the application logic. The `github_action_node` is declared `async` so LangGraph can continue processing other branches while awaiting I/O.

---

## Tech Stack

| Layer              | Technology                                  |
| ------------------ | ------------------------------------------- |
| UI                 | Streamlit                                   |
| Orchestration      | LangGraph                                   |
| LLM                | Google Gemini (`gemini-flash-latest`)       |
| Embeddings         | HuggingFace `all-MiniLM-L6-v2`              |
| Vector DB          | ChromaDB                                    |
| GitHub integration | MCP (`@modelcontextprotocol/server-github`) |

---

## Repository Structure

```
├── frontend.py              # Streamlit UI — credentials, file uploads, results display
├── app.py                   # LangGraph pipeline (triage → log extraction → RCA → GitHub push)
├── scripts/
│   └── index_codebase.py    # One-time script: builds ChromaDB vector store from source files
├── test-python-code/        # Sample target application (FastAPI service with seeded bug)
│   ├── main.py
│   ├── services.py          # Bug site: ZeroDivisionError in compute_error_rate()
│   ├── models.py
│   └── utils.py
├── data/
│   ├── incident_metrics.csv # Sample metrics showing an active incident
│   └── error_logs.log       # Sample logs with a traceback for the seeded bug
└── requirements.txt
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

Node.js is required for the MCP GitHub server (invoked at runtime via `npx`).

### 2. Configure environment variables

Create a `.env` file in the project root:

```env
GOOGLE_API_KEY=your_google_api_key

# Optional — GitHub push step is skipped gracefully if these are absent
GITHUB_PAT=your_github_personal_access_token
GITHUB_OWNER=your_github_username
GITHUB_REPO=your_target_repo_name
```

The GitHub PAT needs `repo` scope (read + write file contents).

### 3. Index the target codebase

Point the indexer at any Python GitHub repository. It will clone it and build the local vector store:

```bash
# Full URL
python scripts/index_codebase.py --repo-url https://github.com/owner/repo

# owner/repo shorthand
python scripts/index_codebase.py --repo-url owner/repo

# Already cloned locally
python scripts/index_codebase.py --repo-path ./path/to/repo
```

You can also trigger this from the **Target Repository** section of the Streamlit sidebar.

### 4. Launch the dashboard

```bash
streamlit run frontend.py
```

Upload a metrics CSV and application log file, then click **Run AI Analysis**.

---

## Sample Incident Scenario

`data/incident_metrics.csv` and `data/error_logs.log` contain a pre-seeded incident: the `recommendation-engine` service is reporting zero traffic and HTTP 500 errors, caused by a `ZeroDivisionError` in `test-python-code/services.py`. Running the pipeline against this data demonstrates the full triage → RCA → remediation flow.

---

## Notes

- GitHub publishing is optional. The RCA report and generated fix are shown in the UI regardless; the push step is simply skipped with a status message if credentials are not configured.
- This project is a demonstration and evaluation artifact, not a production remediation system.
