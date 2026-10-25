"""
Messaging and Reporting Tools.
Enables the autonomous worker to report status, evidence, and completion.
"""

from typing import Dict, Any, Optional, List
from tools.base import BaseTool, ToolResult, ToolStatus


class ReportTaskCompleteTool(BaseTool):
    @property
    def name(self) -> str:
        return "report_task_complete"

    @property
    def description(self) -> str:
        return (
            "Declare task completion. Provide a concise executive summary, the verified facts, "
            "and evidence pointers (e.g. invoice record id, database verification match, screenshot path). "
            "Only call this after independent verification succeeds."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Concise summary of actions taken and final outcome."
                },
                "vendor": {"type": "string", "description": "Vendor name processed"},
                "invoice_number": {"type": "string", "description": "Invoice number recorded"},
                "amount": {"type": "number", "description": "Total amount recorded"},
                "due_date": {"type": "string", "description": "Due date recorded"},
                "evidence": {
                    "type": "object",
                    "description": "Key-value evidence of completion (e.g. database_id, channel, verification_status)."
                }
            },
            "required": ["summary", "vendor", "invoice_number", "amount", "due_date"]
        }

    def execute(
        self,
        summary: str,
        vendor: str,
        invoice_number: str,
        amount: float,
        due_date: str,
        evidence: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> ToolResult:
        payload = {
            "summary": summary,
            "vendor": vendor,
            "invoice_number": invoice_number,
            "amount": amount,
            "due_date": due_date,
            "evidence": evidence or {},
            "completed": True
        }
        return ToolResult(
            tool_name=self.name,
            status=ToolStatus.SUCCESS,
            output=payload,
            metadata={"task_completed": True}
        )


class SendNotificationTool(BaseTool):
    @property
    def name(self) -> str:
        return "send_notification"

    @property
    def description(self) -> str:
        return "Send an email or messaging notification to an internal team (e.g. 'accounting@acme.corp') reporting progress."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "recipient": {"type": "string", "description": "Email or channel handle"},
                "subject": {"type": "string", "description": "Message subject"},
                "body": {"type": "string", "description": "Notification body"}
            },
            "required": ["recipient", "subject", "body"]
        }

    def execute(self, recipient: str, subject: str, body: str, **kwargs) -> ToolResult:
        # In a real system this sends SMTP or Slack message; here we log and record it
        return ToolResult(
            tool_name=self.name,
            status=ToolStatus.SUCCESS,
            output={
                "delivered": True,
                "recipient": recipient,
                "subject": subject,
                "preview": body[:120]
            }
        )
