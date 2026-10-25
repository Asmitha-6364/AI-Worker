"""
AcmeOps REST API Tool.
Provides programmatic HTTP communication with AcmeOps ERP endpoints,
acting as both a verification tool and an alternative recovery channel
when UI forms encounter deadlocks or 500 errors.
"""

from typing import Dict, Any, Optional, List
import httpx

from config import ACME_BASE_URL, ACME_ADMIN_USERNAME, ACME_ADMIN_PASSWORD
from tools.base import BaseTool, ToolResult, ToolStatus


class AppApiClient:
    _instance = None

    def __init__(self, base_url: str = ACME_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.token: Optional[str] = None
        self.client = httpx.Client(base_url=self.base_url, timeout=10.0)

    def login(self, username: str = ACME_ADMIN_USERNAME, password: str = ACME_ADMIN_PASSWORD) -> str:
        res = self.client.post("/api/auth/token", json={"username": username, "password": password})
        if res.status_code == 200:
            self.token = res.json()["access_token"]
            return self.token
        raise RuntimeError(f"API Login failed: {res.text}")

    def get_headers(self) -> Dict[str, str]:
        if not self.token:
            self.login()
        return {"Authorization": f"Bearer {self.token}"}


_api_client: Optional[AppApiClient] = None

def get_api_client() -> AppApiClient:
    global _api_client
    if _api_client is None:
        _api_client = AppApiClient()
    return _api_client


class AppApiInvoiceTool(BaseTool):
    @property
    def name(self) -> str:
        return "app_api_create_invoice"

    @property
    def description(self) -> str:
        return (
            "Direct REST API tool to record an invoice in AcmeOps (POST /api/invoices). "
            "Use this tool directly or as an alternative fallback when browser UI submission fails or errors out."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "vendor": {"type": "string", "description": "Vendor name"},
                "invoice_number": {"type": "string", "description": "Invoice number, e.g. INV-5501"},
                "amount": {"type": "number", "description": "Total amount due as float"},
                "due_date": {"type": "string", "description": "Due date in YYYY-MM-DD"},
                "currency": {"type": "string", "description": "Currency code, defaults to USD", "default": "USD"},
                "issue_date": {"type": "string", "description": "Issue date in YYYY-MM-DD", "default": None},
                "description": {"type": "string", "description": "Line items or description", "default": ""}
            },
            "required": ["vendor", "invoice_number", "amount", "due_date"]
        }

    def execute(
        self,
        vendor: str,
        invoice_number: str,
        amount: float,
        due_date: str,
        currency: str = "USD",
        issue_date: Optional[str] = None,
        description: str = "",
        **kwargs
    ) -> ToolResult:
        client = get_api_client()
        try:
            headers = client.get_headers()
            payload = {
                "vendor": vendor,
                "invoice_number": invoice_number,
                "amount": float(amount),
                "currency": currency,
                "due_date": due_date,
                "issue_date": issue_date,
                "description": description or "Submitted via REST API Fallback",
                "source_channel": "REST_API"
            }
            res = client.client.post("/api/invoices", json=payload, headers=headers)

            if res.status_code == 201:
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.SUCCESS,
                    output=res.json(),
                    metadata={"source_channel": "REST_API", "http_status": 201}
                )
            elif res.status_code == 400 and "Duplicate" in res.text:
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.WARNING,
                    output=res.json(),
                    error=f"Duplicate invoice: {res.text}",
                    error_type="DUPLICATE_KEY"
                )
            else:
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.ERROR,
                    output=None,
                    error=f"API returned HTTP {res.status_code}: {res.text}",
                    error_type="API_ERROR"
                )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                output=None,
                error=f"HTTP request failed: {str(e)}",
                error_type="NETWORK_ERROR"
            )


class AppApiVerifyInvoiceTool(BaseTool):
    @property
    def name(self) -> str:
        return "app_api_verify_invoice"

    @property
    def description(self) -> str:
        return (
            "Independently verify an invoice record in the AcmeOps database against expected values "
            "(vendor, invoice_number, expected_amount, expected_due_date). "
            "Returns whether the record exists and whether all fields strictly match."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "vendor": {"type": "string", "description": "Vendor name to verify"},
                "invoice_number": {"type": "string", "description": "Invoice number to verify"},
                "expected_amount": {"type": "number", "description": "Expected total amount from source doc"},
                "expected_due_date": {"type": "string", "description": "Expected due date from source doc (YYYY-MM-DD)"}
            },
            "required": ["vendor", "invoice_number"]
        }

    def execute(
        self,
        vendor: str,
        invoice_number: str,
        expected_amount: Optional[float] = None,
        expected_due_date: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        client = get_api_client()
        try:
            headers = client.get_headers()
            params = {
                "vendor": vendor,
                "invoice_number": invoice_number,
            }
            if expected_amount is not None:
                params["expected_amount"] = float(expected_amount)
            if expected_due_date is not None:
                params["expected_due_date"] = expected_due_date

            res = client.client.get("/api/verify", params=params, headers=headers)
            if res.status_code == 200:
                data = res.json()
                if data["matched"]:
                    return ToolResult(
                        tool_name=self.name,
                        status=ToolStatus.SUCCESS,
                        output=data,
                        metadata={"verified": True}
                    )
                else:
                    return ToolResult(
                        tool_name=self.name,
                        status=ToolStatus.WARNING,
                        output=data,
                        error=f"Verification discrepancies: {', '.join(data.get('discrepancies', []))}",
                        error_type="VERIFICATION_MISMATCH",
                        metadata={"verified": False}
                    )
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                output=None,
                error=f"Verification API error: HTTP {res.status_code}: {res.text}",
                error_type="API_ERROR"
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                output=None,
                error=f"Verification check failed: {str(e)}",
                error_type="NETWORK_ERROR"
            )
