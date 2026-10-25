"""
Failure Handling and Recovery Engine.
Detects errors, timeouts, and unexpected states; classifies failure types;
and determines adaptive recovery strategies (e.g. API fallback when web UI fails).
"""

from typing import Dict, Any, Optional, Tuple
from config import MAX_RETRIES_PER_FAILURE
from tools.base import ToolResult, ToolStatus


class FailureClassifier:
    """Classifies error symptoms into actionable failure categories."""

    @staticmethod
    def classify(result: ToolResult, context_text: str = "") -> Optional[str]:
        if result.status == ToolStatus.SUCCESS:
            return None

        combined = f"{result.error or ''} {result.error_type or ''} {context_text}".lower()

        if "500" in combined or "lock timeout" in combined or "internal server error" in combined:
            return "UI_CRASH_OR_500"
        if "element_not_found" in combined or "not found" in combined or "selector" in combined:
            return "ELEMENT_NOT_FOUND"
        if "401" in combined or "unauthorized" in combined or "authentication required" in combined:
            return "AUTH_FAILURE"
        if "duplicate" in combined:
            return "DUPLICATE_KEY"
        if "verification_mismatch" in combined or "mismatch" in combined:
            return "VERIFICATION_MISMATCH"
        if "ambiguous" in combined or "multiple" in combined:
            return "AMBIGUOUS_DATA"
        if "connection" in combined or "network" in combined or "timeout" in combined:
            return "NETWORK_ERROR"

        return result.error_type or "UNKNOWN_ERROR"


class RecoveryStrategy:
    """Determines the appropriate fallback or alternative path based on failure classification."""

    @staticmethod
    def get_recovery_plan(error_type: str, retry_count: int, state_facts: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        """
        Returns (strategy_description, suggested_tool_name).
        """
        if retry_count > MAX_RETRIES_PER_FAILURE:
            return (
                f"Retry limit ({MAX_RETRIES_PER_FAILURE}) exceeded for {error_type}. Escalating to human.",
                "ask_human_clarification"
            )

        if error_type == "UI_CRASH_OR_500":
            return (
                "Web UI form worker crashed with 500 error / database lock. "
                "Executing recovery strategy: Bypass broken web UI and use direct authenticated AcmeOps REST API (app_api_create_invoice).",
                "app_api_create_invoice"
            )

        if error_type == "ELEMENT_NOT_FOUND":
            return (
                "Control or button not located on current page. "
                "Executing recovery strategy: Re-inspect DOM summary to check current URL and look for navigation links.",
                "browser_get_dom_summary"
            )

        if error_type == "AUTH_FAILURE":
            return (
                "Session missing or rejected. "
                "Executing recovery strategy: Navigate to /login and re-authenticate.",
                "browser_navigate"
            )

        if error_type == "AMBIGUOUS_DATA":
            return (
                "Multiple conflicting documents or ambiguous records found. "
                "Executing recovery strategy: Pause automated execution and request human operator clarification.",
                "ask_human_clarification"
            )

        if error_type == "VERIFICATION_MISMATCH":
            return (
                "Recorded database data does not strictly match source invoice facts. "
                "Executing recovery strategy: Re-read source invoice and re-verify database state.",
                "app_api_verify_invoice"
            )

        return (
            f"Transient failure ({error_type}). Retrying action with backoff.",
            None
        )
