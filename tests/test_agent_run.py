"""
End-to-End autonomous agent run tests.
Tests standard execution, deliberate failure recovery, and clarification flows.
"""

import pytest
import threading
import time
import uvicorn
import httpx

from config import ACME_HOST, ACME_PORT, ACME_BASE_URL
from acme_ops.app import app
from acme_ops.database import init_db
from seed_data import seed_database, seed_documents
from agent.loop import AutonomousAgent


@pytest.fixture(scope="session", autouse=True)
def run_background_server():
    """Ensure AcmeOps server is running for tests."""
    seed_database()
    seed_documents()

    config = uvicorn.Config(app=app, host=ACME_HOST, port=ACME_PORT, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    # Wait for server
    for _ in range(30):
        try:
            r = httpx.get(f"{ACME_BASE_URL}/api/health", timeout=1.0)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.2)
    yield


@pytest.fixture(autouse=True)
def reset_db_each_test():
    seed_database()
    yield


def test_standard_agent_run():
    agent = AutonomousAgent()
    goal = "Find the latest invoice from Apex Technologies, extract the amount and due date, enter it into AcmeOps, and tell me when done."
    state = agent.run(goal=goal)

    assert state.status == "COMPLETED"
    assert state.verification_passed is True
    assert state.extracted_facts["vendor"] == "Apex Technologies"
    assert state.extracted_facts["invoice_number"] == "INV-9821"
    assert float(state.extracted_facts["amount"]) == 4850.0
    assert state.extracted_facts["due_date"] == "2026-11-15"
    assert state.verification_evidence["verified"] is True


def test_recovery_agent_run():
    agent = AutonomousAgent()
    goal = "Record the invoice for Quantum Logistics in AcmeOps and verify it."
    state = agent.run(goal=goal)

    assert state.status == "COMPLETED"
    assert state.verification_passed is True
    assert state.extracted_facts["vendor"] == "Quantum Logistics"
    assert state.extracted_facts["invoice_number"] == "INV-5501"
    assert float(state.extracted_facts["amount"]) == 7320.0
    # Assert failure occurred and recovery succeeded
    assert state.failure_counts.get("UI_CRASH_OR_500", 0) >= 1
    assert state.verification_evidence["source_channel"] == "REST_API"


def test_clarification_agent_run():
    agent = AutonomousAgent()
    goal = "Find the invoice from CloudScale Solutions and record it into AcmeOps."

    # Programmatic human response callback picking option 2 (INV-3025)
    def mock_human_input(question, options):
        assert "CloudScale Solutions" in question
        return options[1]  # Selects INV-3025

    state = agent.run(goal=goal, human_input_fn=mock_human_input)

    assert state.status == "COMPLETED"
    assert state.verification_passed is True
    assert state.extracted_facts["vendor"] == "CloudScale Solutions"
    assert state.extracted_facts["invoice_number"] == "INV-3025"
    assert float(state.extracted_facts["amount"]) == 3450.0
    assert state.clarification_question is not None
    assert "INV-3025" in state.clarification_answer
