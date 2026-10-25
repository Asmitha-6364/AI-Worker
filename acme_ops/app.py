"""
AcmeOps FastAPI Web Application & REST API.
Simulates an internal company enterprise resource planning (ERP) system.
"""

from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, Request, Response, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from acme_ops.database import (
    init_db,
    create_invoice,
    list_invoices,
    get_invoice_by_id,
    get_invoice_by_vendor_and_number,
    mark_invoice_verified,
    authenticate_user,
    get_flag,
    set_flag,
)
from acme_ops.models import (
    InvoiceCreate,
    InvoiceRecord,
    LoginRequest,
    TokenResponse,
    VerificationResult,
)
from acme_ops.auth import (
    create_session,
    delete_session,
    get_current_user_optional,
    require_auth_api,
)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="AcmeOps ERP",
    description="Simulated internal company operations portal for AI task worker.",
    version="1.0.0",
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def render_template(request: Request, name: str, context: dict, status_code: int = 200) -> HTMLResponse:
    """Helper to render templates compatible with Starlette 1.0+."""
    ctx = dict(context)
    ctx["request"] = request
    return templates.TemplateResponse(request=request, name=name, context=ctx, status_code=status_code)


@app.on_event("startup")
def on_startup():
    init_db()


# ---------------------------------------------------------
# Web UI Routes (HTML + Session Cookie)
# ---------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user = await get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/invoices", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    user = await get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/invoices", status_code=status.HTTP_302_FOUND)
    return render_template(
        request=request,
        name="login.html",
        context={"user": None, "error": error}
    )


@app.post("/login", response_class=HTMLResponse)
async def login_action(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
):
    user = authenticate_user(username.strip(), password.strip())
    if not user:
        return render_template(
            request=request,
            name="login.html",
            context={"user": None, "error": "Invalid username or password."}
        )

    session_id = create_session(user)
    redirect = RedirectResponse(url="/invoices", status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(
        key="acme_session",
        value=session_id,
        httponly=True,
        max_age=3600 * 8,
        samesite="lax",
    )
    return redirect


@app.get("/logout")
async def logout(request: Request):
    session_id = request.cookies.get("acme_session")
    if session_id:
        delete_session(session_id)
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("acme_session")
    return response


@app.get("/invoices", response_class=HTMLResponse)
async def invoices_inbox(request: Request, search: Optional[str] = None, message: Optional[str] = None):
    user = await get_current_user_optional(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    invoices = list_invoices(search=search)
    return render_template(
        request=request,
        name="invoices.html",
        context={
            "user": user,
            "invoices": invoices,
            "search": search,
            "message": message,
            "active_tab": "invoices",
        }
    )


@app.get("/invoices/new", response_class=HTMLResponse)
async def new_invoice_page(request: Request, error: Optional[str] = None):
    user = await get_current_user_optional(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    return render_template(
        request=request,
        name="record_invoice.html",
        context={
            "user": user,
            "error": error,
            "form_data": None,
            "active_tab": "new_invoice",
        }
    )


@app.post("/invoices/new", response_class=HTMLResponse)
async def create_invoice_form(
    request: Request,
    vendor: str = Form(...),
    invoice_number: str = Form(...),
    amount: float = Form(...),
    currency: str = Form("USD"),
    due_date: str = Form(...),
    issue_date: Optional[str] = Form(None),
    description: Optional[str] = Form(""),
    flaky: Optional[str] = None,
):
    user = await get_current_user_optional(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    vendor = vendor.strip()
    invoice_number = invoice_number.strip()

    # DELIBERATE INJECTED FAILURE MODE
    # If system flag is active or vendor is "Quantum Logistics" or ?flaky=1, fail with HTTP 500
    is_flaky_active = get_flag("flaky_ui_submit") == "1"
    is_quantum = "quantum logistics" in vendor.lower()
    if is_flaky_active or is_quantum or flaky == "1":
        # Render a realistic 500 error page with status 500
        return render_template(
            request=request,
            name="error.html",
            context={
                "user": user,
                "error_message": "500 Internal Server Error: Database lock timeout on web form worker (WorkerThread-84). Connection closed.",
            },
            status_code=500,
        )

    # Check for duplicate
    existing = get_invoice_by_vendor_and_number(vendor, invoice_number)
    if existing:
        return render_template(
            request=request,
            name="record_invoice.html",
            context={
                "user": user,
                "error": f"Duplicate invoice detected: '{invoice_number}' already exists for vendor '{vendor}'.",
                "form_data": {
                    "vendor": vendor,
                    "invoice_number": invoice_number,
                    "amount": amount,
                    "due_date": due_date,
                    "issue_date": issue_date,
                    "description": description,
                },
                "active_tab": "new_invoice",
            },
            status_code=400,
        )

    try:
        inv = create_invoice(
            vendor=vendor,
            invoice_number=invoice_number,
            amount=amount,
            currency=currency,
            due_date=due_date,
            issue_date=issue_date,
            description=description or "",
            source_channel="WEB_UI",
        )
        return RedirectResponse(
            url=f"/invoices/{inv['id']}?recorded=true",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return render_template(
            request=request,
            name="record_invoice.html",
            context={
                "user": user,
                "error": f"Failed to record invoice: {str(e)}",
                "form_data": None,
                "active_tab": "new_invoice",
            },
            status_code=500,
        )


@app.get("/invoices/{invoice_id}", response_class=HTMLResponse)
async def invoice_detail(request: Request, invoice_id: int):
    user = await get_current_user_optional(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    inv = get_invoice_by_id(invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return render_template(
        request=request,
        name="invoice_detail.html",
        context={"user": user, "invoice": inv, "active_tab": "invoices"}
    )



@app.post("/invoices/{invoice_id}/verify")
async def verify_invoice_action(request: Request, invoice_id: int):
    user = await get_current_user_optional(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    mark_invoice_verified(invoice_id)
    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------
# REST API Endpoints (JSON + Bearer/Cookie Auth)
# ---------------------------------------------------------

@app.get("/api/health")
async def api_health():
    return {"status": "ok", "app": "AcmeOps", "version": "1.0.0"}


@app.post("/api/auth/token", response_model=TokenResponse)
async def api_login(req: LoginRequest):
    user = authenticate_user(req.username.strip(), req.password.strip())
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_session(user)
    return TokenResponse(access_token=token, username=user["username"])


@app.get("/api/invoices", response_model=List[InvoiceRecord])
async def api_list_invoices(
    vendor: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(require_auth_api),
):
    invoices = list_invoices(vendor_filter=vendor, search=search)
    return [InvoiceRecord(**inv) for inv in invoices]


@app.get("/api/invoices/{invoice_id}", response_model=InvoiceRecord)
async def api_get_invoice(
    invoice_id: int,
    user: dict = Depends(require_auth_api),
):
    inv = get_invoice_by_id(invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return InvoiceRecord(**inv)


@app.post("/api/invoices", response_model=InvoiceRecord, status_code=status.HTTP_201_CREATED)
async def api_create_invoice(
    payload: InvoiceCreate,
    user: dict = Depends(require_auth_api),
):
    """
    Robust REST API invoice creation.
    Unlike the web UI form worker, this endpoint bypasses UI worker deadlocks
    and serves as the official recovery fallback path for programmatic automation.
    """
    vendor = payload.vendor.strip()
    invoice_number = payload.invoice_number.strip()

    # Duplicate check
    existing = get_invoice_by_vendor_and_number(vendor, invoice_number)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Duplicate invoice detected: '{invoice_number}' already exists for vendor '{vendor}'.",
        )

    try:
        inv = create_invoice(
            vendor=vendor,
            invoice_number=invoice_number,
            amount=payload.amount,
            currency=payload.currency,
            due_date=payload.due_date,
            issue_date=payload.issue_date,
            description=payload.description or "",
            source_channel="REST_API",
        )
        return InvoiceRecord(**inv)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/verify", response_model=VerificationResult)
async def api_verify_invoice(
    vendor: str,
    invoice_number: str,
    expected_amount: Optional[float] = None,
    expected_due_date: Optional[str] = None,
    user: dict = Depends(require_auth_api),
):
    """
    Independent verification endpoint used by the agent to confirm
    that the recorded invoice matches the source document.
    """
    inv = get_invoice_by_vendor_and_number(vendor, invoice_number)
    if not inv:
        return VerificationResult(
            matched=False,
            invoice=None,
            discrepancies=[f"Invoice '{invoice_number}' for vendor '{vendor}' was not found in AcmeOps database."],
        )

    discrepancies = []
    if expected_amount is not None:
        if abs(float(inv["amount"]) - float(expected_amount)) > 0.01:
            discrepancies.append(f"Amount mismatch: DB has ${inv['amount']}, expected ${expected_amount}")

    if expected_due_date is not None:
        if inv["due_date"].strip() != expected_due_date.strip():
            discrepancies.append(f"Due date mismatch: DB has '{inv['due_date']}', expected '{expected_due_date}'")

    matched = len(discrepancies) == 0
    if matched:
        mark_invoice_verified(inv["id"])
        inv["verified"] = 1

    return VerificationResult(
        matched=matched,
        invoice=InvoiceRecord(**inv),
        discrepancies=discrepancies,
    )


# ---------------------------------------------------------
# Admin & Demo Helper Endpoints
# ---------------------------------------------------------

@app.post("/api/admin/toggle-failure")
async def toggle_failure(enable: bool):
    """Enable or disable deliberate failure mode on UI form."""
    set_flag("flaky_ui_submit", "1" if enable else "0")
    return {"flaky_ui_submit": enable}


@app.post("/api/admin/reset")
async def reset_database():
    """Reset the database to clean initial state."""
    init_db(force_reset=True)
    return {"status": "database_reset_complete"}
