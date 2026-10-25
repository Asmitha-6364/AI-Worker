"""
Master Autonomous Agent Loop.
Executes the genuine Perceive -> Plan -> Act -> Observe -> Verify loop.
Coordinates Planner, Executor, Failure Handler, Verifier, and Memory.
"""

import sys

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
from typing import Optional, Callable, Dict, Any
from rich.console import Console
from rich.markup import escape

from config import MAX_STEPS
from agent.memory import RunState, StepRecord
from agent.planner import LLMPlanner, PlanDecision
from agent.executor import ToolExecutor
from agent.failure_handler import FailureClassifier, RecoveryStrategy
from agent.verifier import Verifier, VerificationReport
from tools.base import ToolStatus
from tools.browser_tool import get_browser_session

console = Console(force_terminal=True, highlight=False)



class AutonomousAgent:
    def __init__(self):
        self.planner = LLMPlanner()
        self.executor = ToolExecutor()
        self.verifier = Verifier()

    def run(
        self,
        goal: str,
        human_input_fn: Optional[Callable[[str, list], str]] = None,
        on_step_callback: Optional[Callable[[StepRecord], None]] = None
    ) -> RunState:
        """
        Runs the autonomous perceive-plan-act-observe-verify loop to accomplish the natural language goal.
        """
        state = RunState(goal=goal, status="PLANNING")
        state.save_to_disk()

        last_observation: Optional[str] = None
        recovery_flag = False

        console.print(f"\n[bold cyan]🚀 Starting Autonomous AI Worker[/bold cyan]")
        console.print(f"[bold]Goal:[/bold] {goal}")
        console.print(f"[bold]Task Run ID:[/bold] {state.task_id}\n")

        for step_num in range(1, MAX_STEPS + 1):
            # ---------------------------------------------------------
            # 1. PERCEIVE & PLAN
            # ---------------------------------------------------------
            decision: PlanDecision = self.planner.plan_next_step(state, last_observation)

            console.print(f"[bold yellow]🤔 [Step {step_num}] Planner Thought:[/bold yellow] {escape(decision.thought)}")
            console.print(f"[bold blue]🛠️  Action / Tool Call:[/bold blue] [cyan]{decision.tool_name}[/cyan] with args: {escape(str(decision.arguments))}")

            # ---------------------------------------------------------
            # 2. HUMAN-IN-THE-LOOP CHECK
            # ---------------------------------------------------------
            if decision.tool_name == "ask_human_clarification":
                question = decision.arguments.get("question", "Clarification requested.")
                options = decision.arguments.get("options", [])
                context = decision.arguments.get("context", "")

                state.status = "AWAITING_CLARIFICATION"
                state.clarification_question = question
                state.clarification_options = options
                state.save_to_disk()

                console.print(f"\n[bold magenta]⏸️  HUMAN-IN-THE-LOOP CLARIFICATION REQUIRED[/bold magenta]")
                console.print(f"[magenta]{question}[/magenta]")
                for idx, opt in enumerate(options, 1):
                    console.print(f"  [bold]{idx}.[/bold] {opt}")

                user_answer = ""
                if human_input_fn:
                    user_answer = human_input_fn(question, options)
                else:
                    try:
                        user_answer = input("\n👉 Enter selection (number or text): ").strip()
                    except EOFError:
                        user_answer = options[1] if len(options) > 1 else options[0]

                # Map single digit choice if applicable
                if user_answer.isdigit() and 1 <= int(user_answer) <= len(options):
                    user_answer = options[int(user_answer) - 1]

                console.print(f"[green]✔ Human response received:[/green] '{user_answer}'\n")
                state.clarification_answer = user_answer
                state.status = "ACTING"

                # Record step in memory
                state.add_step(
                    thought=decision.thought,
                    tool_name=decision.tool_name,
                    arguments=decision.arguments,
                    status="SUCCESS",
                    observation=f"Clarification provided by operator: '{user_answer}'",
                )
                last_observation = f"Human answered clarification: '{user_answer}'. Proceed with chosen invoice."
                continue

            # ---------------------------------------------------------
            # 3. TASK COMPLETION & INDEPENDENT VERIFICATION
            # ---------------------------------------------------------
            if decision.is_complete or decision.tool_name == "report_task_complete":
                console.print("\n[bold cyan]🔍 Initiating Independent Outcome Verification...[/bold cyan]")
                report: VerificationReport = self.verifier.verify_invoice_record(state.extracted_facts)

                if report.is_verified:
                    console.print(f"[bold green]✅ VERIFICATION CONFIRMED:[/bold green] Record #{report.invoice_id} strictly verified in database!")
                    console.print(f"   [dim]Evidence Hash: {report.evidence_hash} | Channel: {report.source_channel}[/dim]")

                    state.status = "COMPLETED"
                    state.verification_passed = True
                    state.verification_evidence = {
                        "verified": True,
                        "invoice_id": report.invoice_id,
                        "vendor": report.vendor,
                        "invoice_number": report.invoice_number,
                        "amount": report.amount,
                        "due_date": report.due_date,
                        "source_channel": report.source_channel,
                        "evidence_hash": report.evidence_hash,
                        "audit_notes": report.audit_notes,
                    }
                    state.final_summary = decision.arguments.get("summary")

                    step_record = state.add_step(
                        thought=decision.thought,
                        tool_name=decision.tool_name,
                        arguments=decision.arguments,
                        status="SUCCESS",
                        observation=f"Task verified successfully. {report.audit_notes}",
                    )
                    if on_step_callback:
                        on_step_callback(step_record)
                    break
                else:
                    console.print(f"[bold red]❌ Verification Mismatch:[/bold red] {report.discrepancies}")
                    state.add_step(
                        thought=decision.thought,
                        tool_name="verification_check",
                        arguments={},
                        status="ERROR",
                        observation=f"Verification failed: {', '.join(report.discrepancies)}",
                        error_type="VERIFICATION_MISMATCH"
                    )
                    last_observation = f"Verification failed with discrepancies: {', '.join(report.discrepancies)}. Recheck data."
                    continue

            # ---------------------------------------------------------
            # 4. ACT: EXECUTE TOOL
            # ---------------------------------------------------------
            result = self.executor.execute_tool(decision.tool_name, decision.arguments, state)
            obs_str = result.to_observation_str()
            console.print(f"[dim]👁️  Observation:[/dim] {escape(obs_str[:220])}...")

            error_type = None
            is_recovery = recovery_flag
            recovery_flag = False

            # ---------------------------------------------------------
            # 5. FAILURE HANDLING & ADAPTIVE RECOVERY
            # ---------------------------------------------------------
            if result.status == ToolStatus.ERROR:
                error_type = FailureClassifier.classify(result, obs_str)
                state.record_failure(error_type)
                count = state.failure_counts.get(error_type, 1)

                recovery_desc, suggested_tool = RecoveryStrategy.get_recovery_plan(
                    error_type=error_type,
                    retry_count=count,
                    state_facts=state.extracted_facts
                )

                console.print(f"\n[bold red]⚠️  FAILURE DETECTED:[/bold red] {escape(str(result.error))}")
                console.print(f"[bold yellow]🛡️  CLASSIFICATION:[/bold yellow] {error_type} (Attempt {count})")
                console.print(f"[bold green]🔄 RECOVERY STRATEGY:[/bold green] {escape(recovery_desc)}\n")

                state.status = "RECOVERING"
                state.active_recovery_strategy = recovery_desc
                recovery_flag = True

            # Record step in memory & trace
            step_record = state.add_step(
                thought=decision.thought,
                tool_name=decision.tool_name,
                arguments=decision.arguments,
                status=result.status.value,
                observation=obs_str,
                screenshot_path=result.screenshot_path,
                error_type=error_type,
                recovery_attempted=is_recovery
            )
            if on_step_callback:
                on_step_callback(step_record)

            last_observation = obs_str
            time.sleep(0.1)

        # Generate visual HTML trace
        trace_path = state.generate_html_trace()
        console.print(f"\n[bold green]📁 Visual Execution Trace saved to:[/bold green] [cyan]{trace_path}[/cyan]\n")

        # Clean up browser session when task completes
        try:
            get_browser_session().close()
        except Exception:
            pass

        return state
