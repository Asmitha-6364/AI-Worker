# Autonomous AI Task Worker

An end-to-end autonomous AI task worker that accepts a natural language request and completes it across simulated enterprise software, browser automation (Playwright), document extraction (PDF/Scans), and REST APIs — without step-by-step instructions.

Built with a genuine **Perceive $\rightarrow$ Plan $\rightarrow$ Act $\rightarrow$ Observe $\rightarrow$ Verify** loop featuring adaptive failure recovery, out-of-band verification, human-in-the-loop clarification, and auditable visual traces.

---

## Key Features

- **No Step-by-Step Scripting**: Decomposes high-level goals dynamically via tool-calling.
- **AcmeOps Simulated ERP**: Real local web app (FastAPI + SQLite + HTML UI) with session authentication, invoice inbox, entry form, and deliberate failure modes.
- **Document Intelligence**: Extracts structured fields (vendor, invoice #, amount, due date) from PDFs and scanned images.
- **Playwright Browser Control**: Real Chromium browser navigation, form filling, DOM inspection, and full-page screenshot capture.
- **Adaptive Recovery Engine**: Detects 500 server crashes and deadlocks on the web form, classifies the error, and automatically succeeds via an alternative path (authenticated REST API fallback).
- **Strict Independent Verification**: Compares recorded database records against source document facts before declaring completion.
- **Human-in-the-Loop**: Halts and prompts the operator when ambiguous documents or conflicting invoices are discovered.
- **Auditable Visual Traces**: Generates detailed JSON logs and interactive HTML execution reports with step-by-step screenshots.
- **Zero-Config Reproducibility**: Runs 100% reliably out of the box using a built-in state-aware planner, or with real LLM keys (OpenAI GPT-4o, Google Gemini).

---

## Project Structure

```
AI-Worker/
├── acme_ops/                  # Simulated Company Web Application
│   ├── app.py                 # FastAPI application (Web UI + REST API)
│   ├── database.py            # SQLite database schema, CRUD, and audit log
│   ├── auth.py                # Cookie and Bearer token authentication
│   ├── models.py              # Pydantic data schemas
│   ├── static/style.css       # Enterprise UI styling
│   └── templates/             # Jinja2 templates (login, inbox, form, details, errors)
├── documents/                 # Document Source (invoices)
│   ├── Apex_Technologies_INV-9821.pdf       # Latest invoice ($4,850.00, Due 2026-11-15)
│   ├── Apex_Technologies_INV-8410.pdf       # Past invoice ($2,700.00, Due 2026-08-15)
│   ├── CloudScale_Solutions_INV-3011.pdf    # Storage Tier ($1,250.00, Due 2026-11-01)
│   ├── CloudScale_Solutions_INV-3025.pdf    # Migration Services ($3,450.00, Due 2026-11-20)
│   ├── Quantum_Logistics_INV-5501.pdf       # Freight Shipment ($7,320.00, Due 2026-11-30)
│   └── Apex_Technologies_Scanned_INV-9902.png # Scanned image-style invoice
├── tools/                     # Autonomous Tool Layer
│   ├── base.py                # BaseTool, ToolResult, ToolStatus
│   ├── browser_tool.py        # Playwright browser controller & DOM inspector
│   ├── file_tool.py           # Document listing & PDF/image invoice extractor
│   ├── app_api_tool.py        # AcmeOps REST API client (fallback & verification)
│   ├── messaging_tool.py      # Completion reporting & notification tools
│   └── human_tool.py          # Human-in-the-loop clarification tool
├── agent/                     # Autonomous Agent Core
│   ├── loop.py                # Master Perceive-Plan-Act-Observe-Verify loop
│   ├── planner.py             # LLM reasoning with tool calling (LLM + Deterministic Engine)
│   ├── executor.py            # Safe tool execution & observation capture
│   ├── failure_handler.py     # Error classification & adaptive recovery router
│   ├── verifier.py            # Independent database verification engine
│   └── memory.py              # RunState store, JSON persistence, and HTML report generator
├── traces/                    # Audit logs, JSON run states, and HTML trace reports
│   └── screenshots/           # Full-page step screenshots captured by browser
├── tests/                     # Automated Test Suite (14 passed)
│   ├── test_mock_app.py       # AcmeOps endpoints, auth, and failure mode tests
│   ├── test_tools.py          # Document parsing and tool tests
│   └── test_agent_run.py      # End-to-end agent loop tests across all 3 demo tasks
├── config.py                  # Settings & environment variables
├── run.py                     # Single-command CLI entrypoint
├── seed_data.py               # Generates sample invoice documents and seeds database
├── DESIGN.md                  # Comprehensive architectural design document
└── requirements.txt           # Python dependencies
```

---

## Quickstart

### 1. Installation
Ensure Python 3.10+ is installed:

```bash
git clone <repo-url>
cd AI-Worker
pip install -r requirements.txt
playwright install chromium
```

### 2. Run the 3 Evaluation Demos

You can run any of the 3 required demo tasks with a single command:

#### Task 1: Standard Autonomy Flow
Finds the latest invoice from Apex Technologies, extracts amount and due date, operates the browser to log in and enter the invoice into AcmeOps, and independently verifies it in the database:

```bash
python run.py --demo standard
```

#### Task 2: Injected Failure & Autonomous Recovery
The agent enters an invoice for Quantum Logistics. The web form submission triggers an injected HTTP 500 database lock deadlock. The agent detects the failure, classifies it as `UI_CRASH_OR_500`, activates its recovery strategy, switches to the authenticated AcmeOps REST API fallback, records the invoice, and verifies it in the database:

```bash
python run.py --demo recovery
```

#### Task 3: Human-in-the-Loop Clarification
The agent is asked to record an invoice for CloudScale Solutions. Upon discovering two conflicting invoices with different amounts (`INV-3011` for \$1,250 and `INV-3025` for \$3,450), the agent pauses, asks the human operator for clarification, and completes the task with the selected invoice:

```bash
python run.py --demo clarification
```

---

## Arbitrary Natural Language Tasks

You can give the agent any custom task string directly:

```bash
python run.py "Find the latest invoice from Apex Technologies, extract the amount and due date, enter it into AcmeOps, and tell me when done."
```

---

## Standalone Server & Inspection

If you want to run the AcmeOps ERP web application in a separate terminal and browse it manually in your browser:

```bash
python run.py --server
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser:
- **Username**: `admin`
- **Password**: `acmepass123`

---

## Automated Test Suite

Run the full pytest suite (14 unit and end-to-end integration tests):

```bash
python -m pytest tests/
```

Test coverage:
- **`tests/test_agent_run.py`**: Full end-to-end test of standard run, recovery run, and clarification run.
- **`tests/test_mock_app.py`**: Health check, session auth, web form entry, injected 500 error, duplicate rejection, and REST API verification.
- **`tests/test_tools.py`**: Document parsing, PDF extraction, clarification tool, and reporting tool.

---

## Auditable Visual Traces & Evidence

After every run, the agent writes:
1. **JSON RunState** (`traces/{run_id}.json`): Complete chronological audit log of every step, thought, tool arguments, observation, and status.
2. **Interactive Visual HTML Trace** (`traces/{run_id}_trace.html`): Standalone visual dashboard showing timeline cards, agent thoughts, arguments, observations, and browser screenshots.
3. **Step Screenshots** (`traces/screenshots/`): Full-page browser state at each navigation, form fill, and click.

---

## Optional LLM Configuration

The system runs out of the box without any API keys using its built-in `DeterministicPlannerEngine`. To use real LLMs (e.g. OpenAI GPT-4o or Google Gemini):

Create a `.env` file or export your API keys:

```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Or Google Gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-1.5-pro
```
