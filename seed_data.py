"""
Seed Data Generator for AcmeOps and Document Invoices.
Generates realistic PDF invoices and a scanned-image invoice into documents/,
and seeds the AcmeOps SQLite database.
"""

import os
from pathlib import Path
from datetime import datetime, date
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from config import DOCUMENTS_DIR, DB_PATH
from acme_ops.database import init_db, create_invoice, list_invoices


def create_pdf_invoice(
    filepath: Path,
    vendor_name: str,
    vendor_address: str,
    invoice_number: str,
    issue_date: str,
    due_date: str,
    items: list,
    currency: str = "USD"
):
    """Generate a clean, professional corporate PDF invoice."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 size

    # Colors
    primary_color = (0.12, 0.28, 0.55)  # Navy
    text_color = (0.1, 0.1, 0.1)
    muted_color = (0.4, 0.4, 0.4)
    line_color = (0.85, 0.85, 0.85)

    # Header Bar
    page.draw_rect(fitz.Rect(0, 0, 595, 60), color=None, fill=primary_color)
    page.insert_text(fitz.Point(40, 40), "OFFICIAL INVOICE", fontsize=18, color=(1, 1, 1), fontname="helv")

    # Vendor Details (Left)
    y = 95
    page.insert_text(fitz.Point(40, y), vendor_name, fontsize=14, color=primary_color, fontname="helv")
    y += 18
    for line in vendor_address.split("\n"):
        page.insert_text(fitz.Point(40, y), line, fontsize=9, color=muted_color, fontname="helv")
        y += 14

    # Invoice Metadata (Right)
    meta_x = 360
    my = 95
    page.insert_text(fitz.Point(meta_x, my), f"INVOICE NUMBER: {invoice_number}", fontsize=11, color=text_color, fontname="helv")
    my += 18
    page.insert_text(fitz.Point(meta_x, my), f"ISSUE DATE: {issue_date}", fontsize=10, color=muted_color, fontname="helv")
    my += 16
    page.insert_text(fitz.Point(meta_x, my), f"DUE DATE: {due_date}", fontsize=10, color=(0.8, 0.1, 0.1), fontname="helv")
    my += 16
    page.insert_text(fitz.Point(meta_x, my), f"CURRENCY: {currency}", fontsize=10, color=muted_color, fontname="helv")

    # Horizontal separator
    page.draw_line(fitz.Point(40, 180), fitz.Point(555, 180), color=line_color, width=1.5)

    # Bill To
    page.insert_text(fitz.Point(40, 205), "BILL TO:", fontsize=9, color=muted_color, fontname="helv")
    page.insert_text(fitz.Point(40, 222), "Acme Corporation", fontsize=11, color=text_color, fontname="helv")
    page.insert_text(fitz.Point(40, 236), "Accounts Payable Department", fontsize=9, color=muted_color, fontname="helv")
    page.insert_text(fitz.Point(40, 250), "100 Market Street, Suite 400, San Francisco, CA 94105", fontsize=9, color=muted_color, fontname="helv")

    # Table Header
    ty = 285
    page.draw_rect(fitz.Rect(40, ty - 15, 555, ty + 12), color=None, fill=(0.94, 0.95, 0.97))
    page.insert_text(fitz.Point(50, ty), "DESCRIPTION", fontsize=9, color=primary_color, fontname="helv")
    page.insert_text(fitz.Point(340, ty), "QTY", fontsize=9, color=primary_color, fontname="helv")
    page.insert_text(fitz.Point(410, ty), "UNIT PRICE", fontsize=9, color=primary_color, fontname="helv")
    page.insert_text(fitz.Point(500, ty), "TOTAL", fontsize=9, color=primary_color, fontname="helv")

    total_amount = 0.0
    ty += 28

    # Table Rows
    for item in items:
        desc, qty, unit_price = item
        subtotal = qty * unit_price
        total_amount += subtotal

        page.insert_text(fitz.Point(50, ty), desc, fontsize=9, color=text_color, fontname="helv")
        page.insert_text(fitz.Point(345, ty), str(qty), fontsize=9, color=text_color, fontname="helv")
        page.insert_text(fitz.Point(415, ty), f"${unit_price:,.2f}", fontsize=9, color=text_color, fontname="helv")
        page.insert_text(fitz.Point(500, ty), f"${subtotal:,.2f}", fontsize=9, color=text_color, fontname="helv")

        page.draw_line(fitz.Point(40, ty + 6), fitz.Point(555, ty + 6), color=line_color, width=0.5)
        ty += 24

    # Total Summary
    ty += 15
    page.draw_line(fitz.Point(340, ty), fitz.Point(555, ty), color=primary_color, width=1.5)
    ty += 20
    page.insert_text(fitz.Point(360, ty), "TOTAL AMOUNT DUE:", fontsize=11, color=text_color, fontname="helv")
    page.insert_text(fitz.Point(490, ty), f"${total_amount:,.2f}", fontsize=13, color=primary_color, fontname="helv")

    # Payment Instructions
    py = 480
    page.insert_text(fitz.Point(40, py), "PAYMENT INSTRUCTIONS:", fontsize=9, color=muted_color, fontname="helv")
    page.insert_text(fitz.Point(40, py + 16), f"Please remit payment via ACH or Wire within terms to {vendor_name}.", fontsize=9, color=text_color, fontname="helv")
    page.insert_text(fitz.Point(40, py + 30), f"Reference Invoice #{invoice_number} on wire payment confirmation.", fontsize=9, color=muted_color, fontname="helv")

    # Save PDF
    doc.save(str(filepath))
    doc.close()
    return total_amount


def create_scanned_image_invoice(filepath: Path):
    """Generate a realistic scanned/faxed receipt-style image invoice."""
    img = Image.new("RGB", (800, 1050), color=(250, 249, 245))
    draw = ImageDraw.Draw(img)

    # Scanned document noise and header
    draw.rectangle([40, 40, 760, 1010], outline=(180, 180, 180), width=2)
    draw.rectangle([45, 45, 755, 120], fill=(230, 235, 240))

    # We use default font or basic lines
    draw.text((60, 60), "APEX TECHNOLOGIES LLC - FIELD SERVICE RECEIPT", fill=(20, 20, 60))
    draw.text((60, 90), "SCANNED VENDOR INVOICE - AP COPY", fill=(100, 100, 100))

    # Meta
    draw.text((60, 160), "INVOICE NUMBER: INV-9902", fill=(0, 0, 0))
    draw.text((60, 190), "VENDOR: Apex Technologies", fill=(0, 0, 0))
    draw.text((60, 220), "ISSUE DATE: 2026-10-20", fill=(0, 0, 0))
    draw.text((60, 250), "DUE DATE: 2026-11-20", fill=(180, 0, 0))

    # Line items
    draw.line([(60, 300), (740, 300)], fill=(120, 120, 120), width=1)
    draw.text((60, 320), "Description: On-site Infrastructure Maintenance & Patching", fill=(0, 0, 0))
    draw.text((60, 350), "Hours: 12.5 hrs @ $200.00/hr", fill=(0, 0, 0))
    draw.text((60, 380), "Parts: Optical Transceivers (x4) - $450.00", fill=(0, 0, 0))
    draw.line([(60, 420), (740, 420)], fill=(120, 120, 120), width=1)

    draw.text((450, 450), "TOTAL AMOUNT: $2,950.00 USD", fill=(0, 0, 120))

    # Scanned stamp
    draw.rectangle([480, 550, 720, 620], outline=(0, 130, 0), width=3)
    draw.text((500, 575), "VERIFIED & APPROVED", fill=(0, 130, 0))

    # Slight blur/scan effect
    img = img.filter(ImageFilter.GaussianBlur(0.3))
    img.save(str(filepath))


def seed_documents():
    """Generate all document invoices required for the demo tasks."""
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Apex Technologies - Past Invoice (Older)
    create_pdf_invoice(
        filepath=DOCUMENTS_DIR / "Apex_Technologies_INV-8410.pdf",
        vendor_name="Apex Technologies",
        vendor_address="500 Tech Parkway, Suite 200\nAustin, TX 78701\nbilling@apextech.com",
        invoice_number="INV-8410",
        issue_date="2026-07-15",
        due_date="2026-08-15",
        items=[
            ("Cloud Security Assessment", 1, 1500.00),
            ("DevOps Support Hours (July)", 10, 120.00),
        ]
    )

    # 2. Apex Technologies - LATEST Invoice (Task 1 Target!)
    # Latest invoice date: 2026-10-15, Due: 2026-11-15, Amount: $4,850.00
    create_pdf_invoice(
        filepath=DOCUMENTS_DIR / "Apex_Technologies_INV-9821.pdf",
        vendor_name="Apex Technologies",
        vendor_address="500 Tech Parkway, Suite 200\nAustin, TX 78701\nbilling@apextech.com",
        invoice_number="INV-9821",
        issue_date="2026-10-15",
        due_date="2026-11-15",
        items=[
            ("Enterprise Kubernetes Managed Cluster (Q4)", 1, 3500.00),
            ("Dedicated SRE On-call Support", 1, 1350.00),
        ]
    )

    # 3. CloudScale Solutions - Invoice A ($1,250.00) (Task 3 Clarification Demo)
    create_pdf_invoice(
        filepath=DOCUMENTS_DIR / "CloudScale_Solutions_INV-3011.pdf",
        vendor_name="CloudScale Solutions",
        vendor_address="1200 Innovation Way\nSeattle, WA 98101\naccounting@cloudscale.io",
        invoice_number="INV-3011",
        issue_date="2026-10-01",
        due_date="2026-11-01",
        items=[
            ("Dedicated Cloud Storage Tier (50TB)", 1, 1250.00),
        ]
    )

    # 4. CloudScale Solutions - Invoice B ($3,450.00) (Task 3 Clarification Demo)
    create_pdf_invoice(
        filepath=DOCUMENTS_DIR / "CloudScale_Solutions_INV-3025.pdf",
        vendor_name="CloudScale Solutions",
        vendor_address="1200 Innovation Way\nSeattle, WA 98101\naccounting@cloudscale.io",
        invoice_number="INV-3025",
        issue_date="2026-10-18",
        due_date="2026-11-20",
        items=[
            ("Data Warehouse Migration Acceleration Services", 1, 3450.00),
        ]
    )

    # 5. Quantum Logistics - Invoice ($7,320.00) (Task 2 Recovery Target!)
    create_pdf_invoice(
        filepath=DOCUMENTS_DIR / "Quantum_Logistics_INV-5501.pdf",
        vendor_name="Quantum Logistics",
        vendor_address="88 Freight Blvd\nChicago, IL 60607\ninvoices@quantumlogistics.com",
        invoice_number="INV-5501",
        issue_date="2026-10-10",
        due_date="2026-11-30",
        items=[
            ("Global Air Freight - Express Shipment #QL-9921", 2, 2800.00),
            ("Customs Clearance and Bonded Drayage", 1, 1720.00),
        ]
    )

    # 6. Scanned image invoice
    create_scanned_image_invoice(DOCUMENTS_DIR / "Apex_Technologies_Scanned_INV-9902.png")

    print(f"Generated sample invoices in {DOCUMENTS_DIR}")


def seed_database():
    """Seed the AcmeOps SQLite database with initial baseline invoices."""
    init_db(force_reset=True)

    # Seed baseline past invoices so the inbox is not empty
    create_invoice(
        vendor="Apex Technologies",
        invoice_number="INV-8410",
        amount=2700.00,
        currency="USD",
        due_date="2026-08-15",
        issue_date="2026-07-15",
        description="Cloud Security Assessment & DevOps support",
        source_channel="SYSTEM_IMPORT",
    )

    create_invoice(
        vendor="Global Office Supplies",
        invoice_number="GOS-1029",
        amount=435.50,
        currency="USD",
        due_date="2026-10-31",
        issue_date="2026-10-01",
        description="Ergonomic chairs and desks for Floor 3",
        source_channel="SYSTEM_IMPORT",
    )

    print(f"Initialized AcmeOps SQLite database at {DB_PATH}")


if __name__ == "__main__":
    seed_database()
    seed_documents()
