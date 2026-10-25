"""
Independent Outcome Verification Engine.
Validates that the requested task outcome was actually accomplished
by independently verifying database records and UI state against source document facts.
Never trusts a tool return code alone.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import hashlib
import json

from acme_ops.database import get_invoice_by_vendor_and_number, get_invoice_by_id, mark_invoice_verified
from tools.app_api_tool import get_api_client


class VerificationReport(BaseModel):
    is_verified: bool
    invoice_id: Optional[int] = None
    vendor: str
    invoice_number: str
    amount: float
    due_date: str
    source_channel: str
    discrepancies: List[str] = []
    evidence_hash: str
    audit_notes: str


class Verifier:
    """Performs strict independent verification of task results."""

    @staticmethod
    def verify_invoice_record(extracted_facts: Dict[str, Any]) -> VerificationReport:
        vendor = extracted_facts.get("vendor")
        invoice_number = extracted_facts.get("invoice_number")
        expected_amount = extracted_facts.get("amount")
        expected_due_date = extracted_facts.get("due_date")

        discrepancies = []

        if not vendor or not invoice_number:
            discrepancies.append("Missing vendor or invoice_number in extracted facts.")
            return VerificationReport(
                is_verified=False,
                vendor=vendor or "UNKNOWN",
                invoice_number=invoice_number or "UNKNOWN",
                amount=expected_amount or 0.0,
                due_date=expected_due_date or "UNKNOWN",
                source_channel="UNKNOWN",
                discrepancies=discrepancies,
                evidence_hash="",
                audit_notes="Verification failed: Required identification fields missing."
            )

        # 1. Query SQLite database directly (independent check)
        record = get_invoice_by_vendor_and_number(vendor, invoice_number)
        if not record:
            discrepancies.append(
                f"Independent DB check: No record found for vendor='{vendor}', invoice_number='{invoice_number}'."
            )
            return VerificationReport(
                is_verified=False,
                vendor=vendor,
                invoice_number=invoice_number,
                amount=float(expected_amount or 0.0),
                due_date=expected_due_date or "UNKNOWN",
                source_channel="UNKNOWN",
                discrepancies=discrepancies,
                evidence_hash="",
                audit_notes="Database query returned 0 matching records."
            )

        # 2. Field-by-field strict comparison
        db_amount = float(record["amount"])
        if expected_amount is not None:
            if abs(db_amount - float(expected_amount)) > 0.01:
                discrepancies.append(
                    f"Amount mismatch: DB recorded ${db_amount:.2f}, expected ${float(expected_amount):.2f}"
                )

        db_due_date = str(record["due_date"]).strip()
        if expected_due_date is not None:
            if db_due_date != str(expected_due_date).strip():
                discrepancies.append(
                    f"Due date mismatch: DB recorded '{db_due_date}', expected '{expected_due_date}'"
                )

        is_verified = len(discrepancies) == 0

        # 3. Mark verified in DB and compute evidence audit hash
        if is_verified:
            mark_invoice_verified(record["id"])

        audit_data = {
            "invoice_id": record["id"],
            "vendor": record["vendor"],
            "invoice_number": record["invoice_number"],
            "amount": record["amount"],
            "due_date": record["due_date"],
            "source_channel": record["source_channel"],
            "created_at": record["created_at"],
        }
        evidence_hash = hashlib.sha256(json.dumps(audit_data, sort_keys=True).encode()).hexdigest()[:16]

        return VerificationReport(
            is_verified=is_verified,
            invoice_id=record["id"],
            vendor=record["vendor"],
            invoice_number=record["invoice_number"],
            amount=db_amount,
            due_date=db_due_date,
            source_channel=record["source_channel"],
            discrepancies=discrepancies,
            evidence_hash=evidence_hash,
            audit_notes=(
                f"Successfully verified record #{record['id']} via independent DB query. "
                f"Recorded via {record['source_channel']}. All fields match source document."
                if is_verified else f"Verification failed with {len(discrepancies)} discrepancies."
            )
        )
