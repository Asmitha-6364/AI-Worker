"""
Unit tests for the autonomous tool layer.
"""

import pytest
from tools.file_tool import ListDocumentsTool, ParseInvoiceTool
from tools.human_tool import AskHumanClarificationTool
from tools.messaging_tool import ReportTaskCompleteTool
from tools.base import ToolStatus
from config import DOCUMENTS_DIR


def test_list_documents_tool():
    tool = ListDocumentsTool()
    result = tool.execute(directory=str(DOCUMENTS_DIR), pattern="*.pdf")
    assert result.status == ToolStatus.SUCCESS
    assert result.output["count"] >= 3
    filenames = [f["filename"] for f in result.output["files"]]
    assert any("Apex_Technologies" in fn for fn in filenames)


def test_parse_invoice_tool_pdf():
    tool = ParseInvoiceTool()
    result = tool.execute(filepath="Apex_Technologies_INV-9821.pdf")
    assert result.status == ToolStatus.SUCCESS
    data = result.output
    assert data["vendor"] == "Apex Technologies"
    assert data["invoice_number"] == "INV-9821"
    assert data["amount"] == 4850.0
    assert data["due_date"] == "2026-11-15"


def test_ask_human_clarification_tool():
    tool = AskHumanClarificationTool()
    result = tool.execute(
        question="Which invoice should I record?",
        options=["Option 1", "Option 2"],
        context="Ambiguous document match"
    )
    assert result.status == ToolStatus.AWAITING_INPUT
    assert result.output["options"] == ["Option 1", "Option 2"]
    assert result.metadata["needs_human_response"] is True


def test_report_task_complete_tool():
    tool = ReportTaskCompleteTool()
    result = tool.execute(
        summary="Task finished",
        vendor="Apex Technologies",
        invoice_number="INV-9821",
        amount=4850.0,
        due_date="2026-11-15",
        evidence={"verified": True}
    )
    assert result.status == ToolStatus.SUCCESS
    assert result.output["completed"] is True
    assert result.metadata["task_completed"] is True
