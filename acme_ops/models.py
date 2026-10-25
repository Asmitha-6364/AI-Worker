"""
Data models for AcmeOps.
"""

from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field


class InvoiceCreate(BaseModel):
    vendor: str = Field(..., description="Name of the vendor")
    invoice_number: str = Field(..., description="Invoice identifier, e.g. INV-9821")
    amount: float = Field(..., gt=0, description="Total amount due")
    currency: str = Field("USD", description="Currency code (USD, EUR, etc.)")
    due_date: str = Field(..., description="Due date in YYYY-MM-DD format")
    issue_date: Optional[str] = Field(None, description="Issue date in YYYY-MM-DD format")
    description: Optional[str] = Field("", description="Description of goods or services")
    source_channel: str = Field("WEB_UI", description="Channel through which invoice was recorded")


class InvoiceRecord(BaseModel):
    id: int
    vendor: str
    invoice_number: str
    amount: float
    currency: str
    due_date: str
    issue_date: Optional[str] = None
    description: Optional[str] = ""
    status: str = "PENDING"
    source_channel: str = "WEB_UI"
    created_at: str
    verified: bool = False


class User(BaseModel):
    id: int
    username: str
    role: str = "accountant"


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class VerificationResult(BaseModel):
    matched: bool
    invoice: Optional[InvoiceRecord] = None
    discrepancies: List[str] = []
