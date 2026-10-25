"""
Base classes and interfaces for the Tool Layer.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum


class ToolStatus(str, Enum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    WARNING = "WARNING"
    AWAITING_INPUT = "AWAITING_INPUT"


class ToolResult(BaseModel):
    tool_name: str
    status: ToolStatus
    output: Any
    error: Optional[str] = None
    error_type: Optional[str] = None
    screenshot_path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_observation_str(self) -> str:
        """Formatted string representation for the LLM perceive phase."""
        if self.status == ToolStatus.ERROR:
            return f"[TOOL ERROR: {self.tool_name}] (Type: {self.error_type or 'General'})\n{self.error}"
        if self.status == ToolStatus.AWAITING_INPUT:
            return f"[AWAITING HUMAN CLARIFICATION]\n{self.output}"
        return f"[TOOL SUCCESS: {self.tool_name}]\n{self.output}"


class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def parameters_schema(self) -> Dict[str, Any]:
        """JSON Schema format matching OpenAI/Gemini function calling schema."""
        pass

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        pass

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            }
        }
