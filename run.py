"""
Main CLI Entrypoint for the Autonomous AI Task Worker.
Allows running arbitrary natural language goals or the 3 core evaluation demo flows.
Automatically starts the AcmeOps local server if not already running.
"""

import sys
import io

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
import threading
import argparse
import httpx
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import ACME_HOST, ACME_PORT, ACME_BASE_URL
from acme_ops.app import app
from seed_data import seed_database, seed_documents
from agent.loop import AutonomousAgent
from agent.memory import RunState

console = Console(force_terminal=True, highlight=False)



def is_server_running() -> bool:
    """Check if AcmeOps server is responsive."""
    try:
        r = httpx.get(f"{ACME_BASE_URL}/api/health", timeout=1.0)
        return r.status_code == 200
    except Exception:
        return False


def start_server_background():
    """Start AcmeOps in a background thread if not already running."""
    if is_server_running():
        return

    console.print(f"[dim]Starting AcmeOps background server at {ACME_BASE_URL}...[/dim]")
    config = uvicorn.Config(app=app, host=ACME_HOST, port=ACME_PORT, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    # Wait for server to become responsive
    for _ in range(30):
        if is_server_running():
            console.print(f"[green]✔ AcmeOps server online at {ACME_BASE_URL}[/green]\n")
            return
        time.sleep(0.2)
    raise RuntimeError("AcmeOps server failed to start within timeout.")


DEMO_TASKS = {
    "standard": "Find the latest invoice from Apex Technologies, extract the amount and due date, enter it into AcmeOps, and tell me when done.",
    "recovery": "Record the invoice for Quantum Logistics in AcmeOps and verify it.",
    "clarification": "Find the invoice from CloudScale Solutions and record it into AcmeOps."
}


def print_completion_panel(state: RunState):
    """Render a clean terminal executive summary and evidence card."""
    evidence = state.verification_evidence

    table = Table(title="[bold green]TASK VERIFICATION & EVIDENCE CERTIFICATE[/bold green]", show_header=True, header_style="bold cyan")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Task Status", f"[bold green]{state.status}[/bold green]")
    table.add_row("Vendor", str(evidence.get("vendor", "N/A")))
    table.add_row("Invoice #", str(evidence.get("invoice_number", "N/A")))
    table.add_row("Amount Verified", f"${float(evidence.get('amount', 0)):,.2f} USD")
    table.add_row("Due Date Verified", str(evidence.get("due_date", "N/A")))
    table.add_row("Channel Recorded", str(evidence.get("source_channel", "N/A")))
    table.add_row("Audit Hash", f"[dim]{evidence.get('evidence_hash', 'N/A')}[/dim]")
    table.add_row("Audit Status", str(evidence.get("audit_notes", "Verified in database")))
    table.add_row("Total Steps Executed", str(len(state.tool_history)))
    table.add_row("Injected Failures Recovered", str(sum(state.failure_counts.values())))

    console.print("\n")
    console.print(Panel(table, border_style="green", title="[bold]Autonomous AI Task Worker Outcome[/bold]"))
    console.print(f"[bold cyan]Summary:[/bold cyan] {state.final_summary or 'Task completed successfully.'}\n")


def main():
    parser = argparse.ArgumentParser(description="Autonomous AI Task Worker - Operate browser, files, and ERP apps.")
    parser.add_argument("goal", nargs="?", default=None, help="Natural language task goal for the agent to execute.")
    parser.add_argument("--demo", choices=["standard", "recovery", "clarification"], help="Run one of the predefined demo tasks.")
    parser.add_argument("--server", action="store_true", help="Run the AcmeOps web application in standalone mode.")
    parser.add_argument("--seed", action="store_true", help="Re-seed sample documents and database.")
    args = parser.parse_args()

    # Re-seed if requested
    if args.seed:
        console.print("[bold yellow]Seeding AcmeOps database and invoices folder...[/bold yellow]")
        seed_database()
        seed_documents()
        return

    # Run standalone server if requested
    if args.server:
        console.print(f"[bold green]Starting AcmeOps standalone server on http://{ACME_HOST}:{ACME_PORT}...[/bold green]")
        uvicorn.run("acme_ops.app:app", host=ACME_HOST, port=ACME_PORT, reload=False)
        return

    # Determine goal
    if args.demo:
        goal = DEMO_TASKS[args.demo]
    elif args.goal:
        goal = args.goal
    else:
        # Default to standard demo
        console.print("[yellow]No goal specified. Defaulting to standard demo task:[/yellow]")
        goal = DEMO_TASKS["standard"]

    # Ensure background server is running
    start_server_background()

    # Create and run autonomous agent
    agent = AutonomousAgent()
    state = agent.run(goal=goal)

    # Print summary
    if state.status == "COMPLETED":
        print_completion_panel(state)
    else:
        console.print(f"[bold red]Task did not reach verified completion. Final status: {state.status}[/bold red]")


if __name__ == "__main__":
    main()
