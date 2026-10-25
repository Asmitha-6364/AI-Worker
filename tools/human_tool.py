"""
Human-in-the-loop Clarification Tool.
Allows the agent to pause and solicit explicit guidance from the human operator
when facing ambiguous documents, conflicting values, or high-risk actions.
"""

from typing import Dict, Any, Optional, List
from tools.base import BaseTool, ToolResult, ToolStatus


class AskHumanClarificationTool(BaseTool):
    @property
    def name(self) -> str:
        return "ask_human_clarification"

    @property
    def description(self) -> str:
        return (
            "Stop execution and ask the human operator a specific question with options when "
            "ambiguous records are found (e.g. multiple matching invoices for the same vendor), "
            "or when confirmation is strictly required. Do not guess or pick arbitrarily."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Clear question to present to the human user."
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of explicit options for the human to pick from."
                },
                "context": {
                    "type": "string",
                    "description": "Context explaining why clarification is required."
                }
            },
            "required": ["question", "options"]
        }

    def execute(self, question: str, options: List[str], context: Optional[str] = None, **kwargs) -> ToolResult:
        payload = {
            "question": question,
            "options": options,
            "context": context or "Ambiguity detected in source documents."
        }
        return ToolResult(
            tool_name=self.name,
            status=ToolStatus.AWAITING_INPUT,
            output=payload,
            metadata={"needs_human_response": True}
        )
