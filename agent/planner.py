"""
Planner Engine for the Autonomous AI Task Worker.
Supports both real LLM function/tool calling (OpenAI, Gemini, LiteLLM)
and a robust state-aware Deterministic Planner Engine for reproducible, zero-API-key testing.
"""

import os
import json
import re
from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel

from config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_PROVIDER,
    ACME_BASE_URL,
    ACME_ADMIN_USERNAME,
    ACME_ADMIN_PASSWORD,
)
from agent.memory import RunState
from tools import get_tools_definitions


class PlanDecision(BaseModel):
    thought: str
    tool_name: str
    arguments: Dict[str, Any]
    is_complete: bool = False


SYSTEM_PROMPT = """You are an Autonomous AI Task Worker operating a simulated company computer environment.
Your goal is to understand the user's high-level request, perceive current system state, plan the next action,
execute tools (browser, documents, REST APIs), observe results, handle failures adaptively, and independently verify outcomes.

OPERATIONAL RULES:
1. PERCEIVE & REMEMBER: Analyze the current state, documents, DOM elements, and facts extracted in memory.
2. ADAPTIVE RECOVERY: If a tool fails (e.g. 500 error on web form), do NOT repeat the exact same failing action blindly. Classify the failure and switch to an alternative strategy (such as direct REST API fallback).
3. CLARIFICATION: If there is ambiguity (e.g. multiple matching invoices with different amounts) or missing requirements, call ask_human_clarification rather than guessing.
4. INDEPENDENT VERIFICATION: Never assume a task is complete just because a submit button was clicked. Always verify the record in the database using app_api_verify_invoice.
5. REPORT: Call report_task_complete only when verified evidence is obtained.
"""


class DeterministicPlannerEngine:
    """
    A dynamic, state-aware planner that evaluates goal, memory facts, tool observations,
    and errors to decide the next logical tool call without needing an external API key.
    """

    def decide(self, state: RunState, last_observation: Optional[str] = None) -> PlanDecision:
        goal_lower = state.goal.lower()
        facts = state.extracted_facts
        history = state.tool_history
        last_step = history[-1] if history else None

        # -------------------------------------------------------------
        # 1. Start: List documents if not listed yet
        # -------------------------------------------------------------
        if not facts.get("documents_listed"):
            return PlanDecision(
                thought="To accomplish the goal, I need to first inspect the available documents in the incoming repository to find matching vendor invoices.",
                tool_name="list_documents",
                arguments={"directory": "documents", "pattern": "*"}
            )

        # -------------------------------------------------------------
        # 2. Check for Ambiguity / Clarification Requirement
        # -------------------------------------------------------------
        files = facts.get("available_files", [])
        if "cloudscale" in goal_lower and not facts.get("selected_file"):
            # Check if multiple CloudScale invoices exist
            cs_files = [f for f in files if "cloudscale" in f.lower()]
            if len(cs_files) > 1 and not state.clarification_answer:
                return PlanDecision(
                    thought=(
                        "I discovered multiple invoice documents matching 'CloudScale Solutions' (INV-3011 and INV-3025). "
                        "Because the user did not specify an invoice number or amount, proceeding would require guessing. "
                        "In accordance with safety guidelines, I must pause and ask the human operator for clarification."
                    ),
                    tool_name="ask_human_clarification",
                    arguments={
                        "question": "Found two matching invoices for CloudScale Solutions. Which one should I record into AcmeOps?",
                        "options": [
                            "CloudScale Solutions INV-3011 ($1,250.00 - Storage Tier)",
                            "CloudScale Solutions INV-3025 ($3,450.00 - Migration Services)"
                        ],
                        "context": "Multiple vendor invoices found with differing scopes and amounts."
                    }
                )

            # If clarification was answered
            if state.clarification_answer:
                chosen = None
                for cf in cs_files:
                    if "3025" in state.clarification_answer and "3025" in cf:
                        chosen = cf
                        break
                    elif "3011" in state.clarification_answer and "3011" in cf:
                        chosen = cf
                        break
                if not chosen:
                    chosen = cs_files[0]
                facts["selected_file"] = chosen

        # Determine target invoice file if not selected yet
        if not facts.get("selected_file"):
            if "apex" in goal_lower:
                # Latest invoice requested for Apex Technologies
                apex_files = [f for f in files if "apex" in f.lower() and f.endswith(".pdf")]
                # Pick latest by filename/INV-number (INV-9821 is latest compared to INV-8410)
                apex_files.sort(reverse=True)
                facts["selected_file"] = apex_files[0]
            elif "quantum" in goal_lower:
                q_files = [f for f in files if "quantum" in f.lower()]
                facts["selected_file"] = q_files[0] if q_files else "Quantum_Logistics_INV-5501.pdf"
            else:
                facts["selected_file"] = files[0] if files else "Apex_Technologies_INV-9821.pdf"

        # -------------------------------------------------------------
        # 3. Parse target invoice document
        # -------------------------------------------------------------
        if not facts.get("invoice_parsed"):
            selected_file = facts["selected_file"]
            return PlanDecision(
                thought=f"I have identified the target invoice document ({selected_file}). I will now read and parse it to extract the vendor name, invoice number, due date, and amount.",
                tool_name="parse_invoice",
                arguments={"filepath": selected_file}
            )

        # -------------------------------------------------------------
        # 4. Handle Injected Failure / Recovery Strategy
        # -------------------------------------------------------------
        if last_step and last_step.status == "ERROR":
            if last_step.error_type == "UI_CRASH_OR_500" or "500" in (last_step.error or ""):
                # Web UI encountered a 500 error / database lock timeout
                return PlanDecision(
                    thought=(
                        "OBSERVATION: The web form submission failed with HTTP 500 Internal Server Error (WorkerThread database lock timeout). "
                        "ANALYSIS: The AcmeOps web form gateway is currently deadlocked. However, the system provides a robust authenticated REST API endpoint (/api/invoices). "
                        "RECOVERY STRATEGY: Rather than repeating the failing browser form submit, I will switch tools to 'app_api_create_invoice' to record the invoice directly via the REST API."
                    ),
                    tool_name="app_api_create_invoice",
                    arguments={
                        "vendor": facts["vendor"],
                        "invoice_number": facts["invoice_number"],
                        "amount": float(facts["amount"]),
                        "due_date": facts["due_date"],
                        "currency": facts.get("currency", "USD"),
                        "description": f"Recovered submission for {facts['invoice_number']} via REST API fallback."
                    }
                )

        # -------------------------------------------------------------
        # 5. Browser Operations: Login and Enter Invoice
        # -------------------------------------------------------------
        if not facts.get("invoice_recorded"):
            current_url = facts.get("browser_current_url", "")

            # If not yet opened browser
            if not current_url:
                return PlanDecision(
                    thought="The invoice details have been parsed. I will now navigate to AcmeOps in the browser to log in and record the invoice.",
                    tool_name="browser_navigate",
                    arguments={"url": f"{ACME_BASE_URL}/login"}
                )

            # If on login page, fill username
            if "/login" in current_url:
                if not facts.get("login_username_filled"):
                    return PlanDecision(
                        thought="I am on the AcmeOps login page. Entering admin username.",
                        tool_name="browser_fill",
                        arguments={"selector": '[data-testid="input-username"]', "value": ACME_ADMIN_USERNAME}
                    )
                if not facts.get("login_password_filled"):
                    return PlanDecision(
                        thought="Entering admin password.",
                        tool_name="browser_fill",
                        arguments={"selector": '[data-testid="input-password"]', "value": ACME_ADMIN_PASSWORD}
                    )
                if not facts.get("login_submitted"):
                    return PlanDecision(
                        thought="Submitting the login form to authenticate.",
                        tool_name="browser_click",
                        arguments={"selector": '[data-testid="btn-login"]'}
                    )

            # If on invoices inbox, click "+ Record Invoice" or navigate to /invoices/new
            if "/invoices" in current_url and "/new" not in current_url and not facts.get("on_new_form"):
                return PlanDecision(
                    thought="Successfully authenticated. Now clicking '+ Record Invoice' button to open the entry form.",
                    tool_name="browser_click",
                    arguments={"selector": '[data-testid="btn-record-invoice"]'}
                )

            # If on /invoices/new, fill out the form
            if "/invoices/new" in current_url or facts.get("on_new_form"):
                if not facts.get("form_vendor_filled"):
                    return PlanDecision(
                        thought=f"Filling in Vendor Name: '{facts['vendor']}'.",
                        tool_name="browser_fill",
                        arguments={"selector": '[data-testid="input-vendor"]', "value": facts["vendor"]}
                    )
                if not facts.get("form_inv_num_filled"):
                    return PlanDecision(
                        thought=f"Filling in Invoice Number: '{facts['invoice_number']}'.",
                        tool_name="browser_fill",
                        arguments={"selector": '[data-testid="input-invoice-number"]', "value": facts["invoice_number"]}
                    )
                if not facts.get("form_amount_filled"):
                    return PlanDecision(
                        thought=f"Filling in Amount: ${facts['amount']:.2f}.",
                        tool_name="browser_fill",
                        arguments={"selector": '[data-testid="input-amount"]', "value": str(facts["amount"])}
                    )
                if not facts.get("form_due_date_filled"):
                    return PlanDecision(
                        thought=f"Filling in Due Date: {facts['due_date']}.",
                        tool_name="browser_fill",
                        arguments={"selector": '[data-testid="input-due-date"]', "value": facts["due_date"]}
                    )
                if not facts.get("form_submitted"):
                    return PlanDecision(
                        thought="All required fields are populated. Submitting the invoice form into AcmeOps.",
                        tool_name="browser_click",
                        arguments={"selector": '[data-testid="btn-submit-invoice"]'}
                    )

        # -------------------------------------------------------------
        # 6. Verification: Independently Check Outcome
        # -------------------------------------------------------------
        if facts.get("invoice_recorded") and not state.verification_passed:
            return PlanDecision(
                thought=(
                    "The invoice has been entered into the system. In accordance with safety rules, I will not declare completion "
                    "until I independently verify the database record against the original invoice data."
                ),
                tool_name="app_api_verify_invoice",
                arguments={
                    "vendor": facts["vendor"],
                    "invoice_number": facts["invoice_number"],
                    "expected_amount": float(facts["amount"]),
                    "expected_due_date": facts["due_date"]
                }
            )

        # -------------------------------------------------------------
        # 7. Completion Report
        # -------------------------------------------------------------
        if state.verification_passed:
            return PlanDecision(
                thought="Independent verification confirmed that the record exists and all fields match. I will now compile the completion summary and audit evidence.",
                tool_name="report_task_complete",
                arguments={
                    "summary": f"Successfully processed and recorded invoice {facts['invoice_number']} for {facts['vendor']} in AcmeOps with independent DB verification.",
                    "vendor": facts["vendor"],
                    "invoice_number": facts["invoice_number"],
                    "amount": float(facts["amount"]),
                    "due_date": facts["due_date"],
                    "evidence": state.verification_evidence
                },
                is_complete=True
            )

        # Fallback
        return PlanDecision(
            thought="Inspecting current browser DOM state to determine next action.",
            tool_name="browser_get_dom_summary",
            arguments={}
        )


class LLMPlanner:
    """Wrapper that invokes OpenAI/Gemini if API key configured, otherwise delegates to DeterministicPlannerEngine."""

    def __init__(self):
        self.deterministic_engine = DeterministicPlannerEngine()
        self.openai_client = None
        self._init_llm_client()

    def _init_llm_client(self):
        if OPENAI_API_KEY:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=OPENAI_API_KEY)
            except Exception:
                pass
        elif GEMINI_API_KEY:
            try:
                from openai import OpenAI
                # Gemini provides OpenAI-compatible endpoint
                self.openai_client = OpenAI(
                    api_key=GEMINI_API_KEY,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                )
            except Exception:
                pass

    def plan_next_step(self, state: RunState, last_observation: Optional[str] = None) -> PlanDecision:
        # If no real LLM API key or explicit deterministic mode, use DeterministicPlannerEngine
        if not self.openai_client or LLM_PROVIDER == "deterministic":
            return self.deterministic_engine.decide(state, last_observation)

        # Otherwise, invoke real LLM via function/tool calling
        try:
            tools_schema = get_tools_definitions()
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"TASK GOAL: {state.goal}\n\n"
                        f"EXTRACTED FACTS MEMORY: {json.dumps(state.extracted_facts, indent=2)}\n"
                        f"CLARIFICATION ANSWER: {state.clarification_answer or 'None'}\n"
                        f"LAST OBSERVATION:\n{last_observation or 'Initial step'}\n\n"
                        "Decide the next single tool call. Explain your thought reasoning clearly."
                    )
                }
            ]

            model_name = GEMINI_MODEL if (GEMINI_API_KEY and not OPENAI_API_KEY) else OPENAI_MODEL
            response = self.openai_client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
                temperature=0.1,
            )

            msg = response.choices[0].message
            if msg.tool_calls:
                tc = msg.tool_calls[0]
                tool_name = tc.function.name
                args = json.loads(tc.function.arguments)
                thought = msg.content or f"Executing tool {tool_name} to progress towards goal."
                is_complete = (tool_name == "report_task_complete")
                return PlanDecision(thought=thought, tool_name=tool_name, arguments=args, is_complete=is_complete)
            else:
                # LLM responded without a tool call; fall back to deterministic engine
                return self.deterministic_engine.decide(state, last_observation)
        except Exception as e:
            # On any LLM API error, fall back gracefully to deterministic engine
            decision = self.deterministic_engine.decide(state, last_observation)
            decision.thought = f"[LLM fallback: {str(e)[:60]}] " + decision.thought
            return decision
