"""
Tool Executor for the Autonomous AI Task Worker.
Safely executes tools from the registry, captures observations,
handles exceptions, and synchronizes memory facts.
"""

from typing import Dict, Any, Optional
import time

from tools import get_default_tools
from tools.base import ToolResult, ToolStatus, BaseTool
from agent.memory import RunState


class ToolExecutor:
    def __init__(self):
        self.tools = get_default_tools()

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any], state: RunState) -> ToolResult:
        if tool_name not in self.tools:
            return ToolResult(
                tool_name=tool_name,
                status=ToolStatus.ERROR,
                output=None,
                error=f"Tool '{tool_name}' is not registered in the tool layer.",
                error_type="UNKNOWN_TOOL"
            )

        tool: BaseTool = self.tools[tool_name]
        try:
            result = tool.execute(**arguments)
            self._sync_state_facts(tool_name, arguments, result, state)
            return result
        except Exception as e:
            return ToolResult(
                tool_name=tool_name,
                status=ToolStatus.ERROR,
                output=None,
                error=f"Unhandled exception during tool execution: {str(e)}",
                error_type="TOOL_CRASH"
            )

    def _sync_state_facts(self, tool_name: str, arguments: Dict[str, Any], result: ToolResult, state: RunState):
        """Update structured run-state facts based on tool execution results."""
        facts = state.extracted_facts

        if tool_name == "list_documents" and result.status == ToolStatus.SUCCESS:
            facts["documents_listed"] = True
            files_data = result.output.get("files", [])
            facts["available_files"] = [f["filename"] for f in files_data]

        elif tool_name == "parse_invoice" and result.status == ToolStatus.SUCCESS:
            facts["invoice_parsed"] = True
            out = result.output
            for k in ["vendor", "invoice_number", "amount", "due_date", "issue_date", "currency"]:
                if out.get(k) is not None:
                    facts[k] = out[k]

        elif tool_name == "browser_navigate" and result.status == ToolStatus.SUCCESS:
            facts["browser_current_url"] = result.output.get("current_url", "")

        elif tool_name == "browser_fill" and result.status == ToolStatus.SUCCESS:
            sel = arguments.get("selector", "")
            if "username" in sel:
                facts["login_username_filled"] = True
            elif "password" in sel:
                facts["login_password_filled"] = True
            elif "input-vendor" in sel:
                facts["form_vendor_filled"] = True
            elif "input-invoice-number" in sel:
                facts["form_inv_num_filled"] = True
            elif "input-amount" in sel:
                facts["form_amount_filled"] = True
            elif "input-due-date" in sel:
                facts["form_due_date_filled"] = True

        elif tool_name == "browser_click":
            sel = arguments.get("selector", "")
            if result.status == ToolStatus.SUCCESS:
                facts["browser_current_url"] = result.output.get("current_url", facts.get("browser_current_url", ""))
                if "btn-login" in sel:
                    facts["login_submitted"] = True
                elif "btn-record-invoice" in sel:
                    facts["on_new_form"] = True
                elif "btn-submit-invoice" in sel:
                    facts["form_submitted"] = True
                    facts["invoice_recorded"] = True
                    facts["created_via"] = "WEB_UI"
            elif result.status == ToolStatus.ERROR:
                if "btn-submit-invoice" in sel:
                    facts["form_submitted"] = False
                    facts["invoice_recorded"] = False

        elif tool_name == "app_api_create_invoice" and result.status in (ToolStatus.SUCCESS, ToolStatus.WARNING):
            facts["invoice_recorded"] = True
            facts["created_via"] = "REST_API"
            facts["api_created_record"] = result.output

        elif tool_name == "app_api_verify_invoice":
            if result.status == ToolStatus.SUCCESS:
                state.verification_passed = True
                state.verification_evidence = result.output
            else:
                state.verification_passed = False

        state.save_to_disk()
