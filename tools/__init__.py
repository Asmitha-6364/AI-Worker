"""
Tools package registry for the Autonomous AI Task Worker.
"""

from typing import Dict, List
from tools.base import BaseTool, ToolResult, ToolStatus
from tools.file_tool import ListDocumentsTool, ParseInvoiceTool
from tools.browser_tool import (
    BrowserNavigateTool,
    BrowserClickTool,
    BrowserFillTool,
    BrowserGetDomSummaryTool,
    get_browser_session,
)
from tools.app_api_tool import AppApiInvoiceTool, AppApiVerifyInvoiceTool
from tools.messaging_tool import ReportTaskCompleteTool, SendNotificationTool
from tools.human_tool import AskHumanClarificationTool


def get_default_tools() -> Dict[str, BaseTool]:
    """Returns all registered tools indexed by tool name."""
    tools: List[BaseTool] = [
        ListDocumentsTool(),
        ParseInvoiceTool(),
        BrowserNavigateTool(),
        BrowserClickTool(),
        BrowserFillTool(),
        BrowserGetDomSummaryTool(),
        AppApiInvoiceTool(),
        AppApiVerifyInvoiceTool(),
        ReportTaskCompleteTool(),
        SendNotificationTool(),
        AskHumanClarificationTool(),
    ]
    return {tool.name: tool for tool in tools}


def get_tools_definitions() -> List[Dict]:
    """Returns OpenAI/Gemini compatible tool definitions."""
    return [tool.get_definition() for tool in get_default_tools().values()]
