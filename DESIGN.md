# Design Document: Autonomous AI Task Worker

## Executive Summary
This document specifies the architecture, engineering principles, and operational design of the **Autonomous AI Task Worker** — an agentic system capable of completing end-to-end knowledge and computer operations without step-by-step guidance. The worker accepts high-level natural language goals, dynamically decomposes tasks, perceives multi-modal environments (DOM trees, PDF invoices, HTTP APIs), detects failures, recovers via alternative execution strategies, and performs strict independent verification before claiming success.

---

## 1. System Architecture

```mermaid
graph TD
    User([User / CLI Goal]) --> AgentLoop[Autonomous Agent Loop]
    
    subgraph "Perceive-Plan-Act Core"
        AgentLoop --> Planner[LLM Planner / Reasoning Engine]
        Planner -->|Next Tool Call & Thought| Executor[Tool Executor]
        Executor -->|Observation & Screenshot| AgentLoop
        AgentLoop --> Memory[(RunState Store & Fact Memory)]
        Memory --> Planner
    end

    subgraph "Adaptive Resilience Layer"
        Executor -->|Error / Timeout / 500| FailureClassifier[Failure Classifier]
        FailureClassifier --> RecoveryEngine[Recovery Strategy Router]
        RecoveryEngine -->|Alternative Path| Planner
    end

    subgraph "Independent Verification"
        AgentLoop -->|Outcome Check| Verifier[Independent Verifier]
        Verifier -->|Direct Query| Database[(AcmeOps SQLite DB)]
        Verifier -->|Verification API| AcmeOpsAPI[AcmeOps REST API]
    end

    subgraph "Environment & Tooling"
        Executor --> BrowserTool[Playwright Browser Tool]
        Executor --> FileTool[Document & PDF Parser Tool]
        Executor --> AppApiTool[AcmeOps REST API Tool]
        Executor --> HumanTool[Human Clarification Tool]
        Executor --> MessagingTool[Notification Tool]
    end

    subgraph "Target Environment (AcmeOps)"
        BrowserTool --> AcmeOpsWeb[AcmeOps Web UI: HTML / Forms]
        AppApiTool --> AcmeOpsAPI
        FileTool --> DocumentRepo[Invoices: PDFs & Scans]
    end
```

### Component Breakdown
1. **Agent Loop (`agent/loop.py`)**: Orchestrates the master lifecycle: Perceive $\rightarrow$ Plan $\rightarrow$ Act $\rightarrow$ Observe $\rightarrow$ Verify.
2. **Planner (`agent/planner.py`)**: Selects tools using structured function/tool-calling. Operates in two complementary modes:
   - **Production LLM Mode**: Calls OpenAI (`gpt-4o`) or Gemini (`gemini-1.5-pro`) using structured tool schemas.
   - **Deterministic Engine Mode**: A state-aware reasoning engine that guarantees reproducible, zero-API-key demonstrations and deterministic CI test suites.
3. **Executor (`agent/executor.py`)**: Dispatches tool calls, captures DOM states, records full-page screenshots, enforces timeouts, and synchronizes memory facts.
4. **Memory (`agent/memory.py`)**: A structured run-state store (`RunState`) tracking goal, subtasks, extracted business facts, full chronological tool history, and clarification questions. Persisted to disk as JSON after every step and rendered as an interactive visual HTML audit trace.
5. **Failure & Recovery Engine (`agent/failure_handler.py`)**: Classifies failures into taxonomies (`UI_CRASH_OR_500`, `ELEMENT_NOT_FOUND`, `AUTH_FAILURE`, `AMBIGUOUS_DATA`, `VERIFICATION_MISMATCH`) and routes execution to adaptive recovery strategies.
6. **Verifier (`agent/verifier.py`)**: Performs independent out-of-band verification by comparing recorded database records against source document facts.
7. **Simulated Company Application ("AcmeOps") (`acme_ops/`)**: A real local FastAPI + SQLite web app featuring session-cookie auth, vendor bills inbox, invoice entry form, deliberate failure modes (deadlock 500 error), duplicate key detection, and a robust REST API.

---

## 2. Why the Loop is Structured This Way

### Rejection of Hardcoded Scripting
Traditional RPA (Robotic Process Automation) relies on brittle, linear step scripts ($A \rightarrow B \rightarrow C$). If step $B$ fails (e.g. a button moves, a worker crashes, or an invoice format changes), the entire script collapses. 

In contrast, this system implements a genuine **Perceive $\rightarrow$ Plan $\rightarrow$ Act $\rightarrow$ Observe $\rightarrow$ Verify** loop:
1. **Perceive**: The agent observes current state from its environment (page URL, DOM summary, file contents, extracted facts).
2. **Plan**: The planner evaluates: *“Given my goal and current observation, what is the single next best action?”*
3. **Act**: The executor runs the tool with validated arguments.
4. **Observe**: The outcome is captured (DOM change, HTTP status, or error trace).
5. **Verify**: The outcome is validated against an independent ground truth.

This architecture enables:
- **Opportunistic Execution**: If the agent is already logged in, it skips the login step.
- **Dynamic De-duplication**: If an invoice is already entered, the agent notices and verifies rather than attempting a duplicate write.
- **Feedback-driven Adaptation**: Observations dictate the next plan rather than an inflexible recipe.

---

## 3. Failure Handling, Adaptive Retries, and Recovery

Autonomous agents must not give up when an action fails, nor should they mindlessly repeat the exact same failing action in an infinite loop.

### Failure Classification Taxonomy
When an action fails, `FailureClassifier` maps the error into a deterministic category:

| Error Symptom | Classification | Adaptive Recovery Strategy |
| :--- | :--- | :--- |
| `500 Internal Server Error`, Database deadlock | `UI_CRASH_OR_500` | **API Fallback**: Switch from failing browser form to authenticated REST API (`POST /api/invoices`). |
| Selector timeout, element hidden/moved | `ELEMENT_NOT_FOUND` | **DOM Re-inspection**: Inspect DOM summary to locate alternative controls or re-navigate. |
| 401 Unauthorized, redirect to `/login` | `AUTH_FAILURE` | **Re-authentication**: Navigate to `/login` and re-authenticate. |
| Multiple documents match query | `AMBIGUOUS_DATA` | **Human Escalation**: Halt execution and prompt human operator for clarification. |
| DB value differs from source document | `VERIFICATION_MISMATCH` | **Re-extraction**: Re-parse original document and reconcile conflicting fields. |

### Bounded Retries with Strategy Switching
- Every failure type maintains an independent retry counter in `RunState.failure_counts`.
- If an action fails once, the system switches execution channels (e.g. Web UI $\rightarrow$ REST API).
- If retries exceed `MAX_RETRIES_PER_FAILURE` (default: 3), the agent safely halts and escalates to a human operator.

---

## 4. Independent Verification: Never Trust Tool Status Alone

A core flaw of naive task workers is "optimistic completion" — assuming that because a button was clicked without a crash, the business transaction succeeded. In enterprise systems, clicks can fail silently (unhandled client-side validation, dropped background workers, database rollback).

### The 3-Step Verification Protocol
1. **Out-of-Band State Check**: The agent queries the database directly (`get_invoice_by_vendor_and_number`) or queries the independent `/api/verify` endpoint.
2. **Strict Multi-Field Ground Truth Comparison**:
   $$\text{Match} = (\text{DB}_{\text{vendor}} == \text{Doc}_{\text{vendor}}) \land (\text{DB}_{\text{inv}} == \text{Doc}_{\text{inv}}) \land (|\text{DB}_{\text{amt}} - \text{Doc}_{\text{amt}}| < 0.01) \land (\text{DB}_{\text{due}} == \text{Doc}_{\text{due}})$$
3. **Cryptographic Evidence Hashing**: If and only if all fields match, the verifier computes a SHA-256 evidence certificate over the database record and marks the invoice as verified in the ERP audit table.

---

## 5. Human-in-the-Loop Clarification Architecture

When facing ambiguity, an autonomous agent should never guess:
- In Task 3, two invoices match "CloudScale Solutions" (`INV-3011` for \$1,250 and `INV-3025` for \$3,450).
- The planner detects that proceeding without guidance risks entering the wrong financial commitment.
- The agent calls `ask_human_clarification`, setting `status="AWAITING_CLARIFICATION"`.
- The CLI renders an interactive prompt with explicit choices.
- The operator's response is committed to `RunState.clarification_answer`, enabling the agent to resume execution safely.

---

## 6. Known Limitations and Trade-offs

1. **Local Network / Port Scoping**: Playwright runs against `127.0.0.1:8000`. In multi-tenant cloud environments, mock apps would run in isolated Docker containers with ephemeral DNS.
2. **OCR for Highly Distorted Images**: The current image parser handles scanned templates and receipts using layout heuristics and metadata. For degraded physical scans (heavy skew, coffee stains), integrating Tesseract or a vision model (e.g. Gemini Vision API) would be required.
3. **Single Browser Tab Scope**: The prototype maintains a single active page context. Highly complex enterprise ERPs opening multi-window popups would require multi-tab page tracking.

---

## 7. Next Steps & Production Roadmap

1. **Multi-Modal Vision Inspection**: Pass real-time page screenshots to multimodal LLMs (e.g. Gemini 1.5 Pro) to perceive visual layout anomalies, canvas controls, and CAPTCHAs.
2. **Subagent Delegation**: For large document batches (100+ invoices), instantiate specialized subagents to extract PDFs in parallel while a submission subagent queues entries into AcmeOps.
3. **Self-Healing Selectors**: Use vector similarity over DOM embeddings to automatically repair broken CSS selectors when web app frontends undergo redesigns.
4. **Interactive Web Dashboard**: Upgrade the terminal CLI to a live web-based control room where human reviewers can approve high-value invoices with one click.
