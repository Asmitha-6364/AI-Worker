"""
Structured Run-State Store and Memory for the Autonomous AI Task Worker.
Persists execution state, facts, subtasks, tool history, and audit traces.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from config import TRACES_DIR


class StepRecord(BaseModel):
    step_index: int
    timestamp: str
    thought: str
    tool_name: str
    arguments: Dict[str, Any]
    status: str
    observation: str
    screenshot_path: Optional[str] = None
    error_type: Optional[str] = None
    recovery_attempted: bool = False


class RunState(BaseModel):
    task_id: str = Field(default_factory=lambda: f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}")
    goal: str
    status: str = "INITIALIZED"  # PLANNING, ACTING, OBSERVING, AWAITING_CLARIFICATION, RECOVERING, VERIFYING, COMPLETED, FAILED
    start_time: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    end_time: Optional[str] = None

    # Structured Knowledge & Extracted Facts
    extracted_facts: Dict[str, Any] = Field(default_factory=dict)
    subtasks: List[str] = Field(default_factory=list)
    active_subtask: Optional[str] = None

    # Chronological Audit Trail
    tool_history: List[StepRecord] = Field(default_factory=list)

    # Human-in-the-loop & Clarifications
    clarification_question: Optional[str] = None
    clarification_options: List[str] = Field(default_factory=list)
    clarification_answer: Optional[str] = None

    # Failure and Recovery Tracking
    failure_counts: Dict[str, int] = Field(default_factory=dict)
    active_recovery_strategy: Optional[str] = None

    # Completion & Verification Evidence
    verification_passed: bool = False
    verification_evidence: Dict[str, Any] = Field(default_factory=dict)
    final_summary: Optional[str] = None

    def add_step(
        self,
        thought: str,
        tool_name: str,
        arguments: Dict[str, Any],
        status: str,
        observation: str,
        screenshot_path: Optional[str] = None,
        error_type: Optional[str] = None,
        recovery_attempted: bool = False
    ) -> StepRecord:
        record = StepRecord(
            step_index=len(self.tool_history) + 1,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            thought=thought,
            tool_name=tool_name,
            arguments=arguments,
            status=status,
            observation=observation,
            screenshot_path=screenshot_path,
            error_type=error_type,
            recovery_attempted=recovery_attempted,
        )
        self.tool_history.append(record)
        self.save_to_disk()
        return record

    def update_fact(self, key: str, value: Any):
        self.extracted_facts[key] = value
        self.save_to_disk()

    def record_failure(self, error_type: str):
        self.failure_counts[error_type] = self.failure_counts.get(error_type, 0) + 1
        self.save_to_disk()

    def save_to_disk(self):
        TRACES_DIR.mkdir(parents=True, exist_ok=True)
        trace_file = TRACES_DIR / f"{self.task_id}.json"
        with open(trace_file, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))

    def generate_html_trace(self) -> Path:
        """Generates a standalone, visual HTML audit report of the entire task execution."""
        html_file = TRACES_DIR / f"{self.task_id}_trace.html"

        steps_html = []
        for s in self.tool_history:
            badge_color = "#16a34a" if s.status == "SUCCESS" else ("#dc2626" if s.status == "ERROR" else "#d97706")
            screenshot_tag = ""
            if s.screenshot_path and Path(s.screenshot_path).exists():
                # Relative link or embedded
                screenshot_tag = f"""
                <div style="margin-top: 10px;">
                  <strong>Screenshot Observation:</strong><br>
                  <a href="{s.screenshot_path}" target="_blank">
                    <img src="{s.screenshot_path}" style="max-width: 100%; max-height: 350px; border: 1px solid #ccc; border-radius: 6px; margin-top: 4px;" alt="Step Screenshot">
                  </a>
                </div>
                """

            recovery_badge = '<span style="background: #fef08a; color: #854d0e; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-left: 8px;">RECOVERY ACTION</span>' if s.recovery_attempted else ''

            steps_html.append(f"""
            <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
              <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #f1f5f9; padding-bottom: 8px; margin-bottom: 12px;">
                <div>
                  <strong style="color: #1e293b; font-size: 15px;">Step {s.step_index}: <code>{s.tool_name}</code></strong>
                  {recovery_badge}
                </div>
                <div>
                  <span style="background: {badge_color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">{s.status}</span>
                  <span style="color: #64748b; font-size: 12px; margin-left: 8px;">{s.timestamp}</span>
                </div>
              </div>

              <div style="margin-bottom: 10px;">
                <div style="color: #475569; font-size: 12px; font-weight: bold; text-transform: uppercase;">Agent Thought / Reasoning:</div>
                <div style="background: #f8fafc; border-left: 3px solid #3b82f6; padding: 8px 12px; font-size: 13px; color: #1e293b; margin-top: 4px; white-space: pre-wrap;">{s.thought}</div>
              </div>

              <div style="margin-bottom: 10px;">
                <div style="color: #475569; font-size: 12px; font-weight: bold; text-transform: uppercase;">Tool Arguments:</div>
                <pre style="background: #f1f5f9; padding: 8px 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; margin-top: 4px;">{json.dumps(s.arguments, indent=2)}</pre>
              </div>

              <div style="margin-bottom: 10px;">
                <div style="color: #475569; font-size: 12px; font-weight: bold; text-transform: uppercase;">Observation Output:</div>
                <pre style="background: #f8fafc; padding: 8px 12px; border-radius: 6px; font-size: 12px; max-height: 200px; overflow-y: auto; margin-top: 4px; border: 1px solid #e2e8f0;">{s.observation}</pre>
              </div>

              {screenshot_tag}
            </div>
            """)

        facts_json = json.dumps(self.extracted_facts, indent=2)
        evidence_json = json.dumps(self.verification_evidence, indent=2)

        content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Autonomous Task Worker Run Trace - {self.task_id}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 24px; }}
    .container {{ max-width: 1000px; margin: 0 auto; }}
    .header {{ background: #1e293b; color: white; padding: 24px; border-radius: 8px; margin-bottom: 24px; }}
    .badge-status {{ display: inline-block; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: bold; text-transform: uppercase; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <h1 style="margin: 0; font-size: 22px;">Autonomous AI Task Worker Audit Trace</h1>
        <span class="badge-status" style="background: {'#16a34a' if self.status == 'COMPLETED' else '#dc2626'}; color: white;">{self.status}</span>
      </div>
      <p style="margin: 8px 0 0; color: #94a3b8; font-size: 14px;"><strong>Goal:</strong> "{self.goal}"</p>
      <div style="margin-top: 12px; display: flex; gap: 24px; font-size: 13px; color: #cbd5e1;">
        <div>Run ID: <code>{self.task_id}</code></div>
        <div>Total Steps: <strong>{len(self.tool_history)}</strong></div>
        <div>Verified: <strong>{'YES (Database match)' if self.verification_passed else 'NO'}</strong></div>
      </div>
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px;">
      <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;">
        <h3 style="margin-top: 0; font-size: 14px; color: #475569; text-transform: uppercase;">Extracted Facts Memory</h3>
        <pre style="background: #f8fafc; padding: 10px; border-radius: 6px; font-size: 12px; margin: 0; overflow-x: auto;">{facts_json}</pre>
      </div>
      <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;">
        <h3 style="margin-top: 0; font-size: 14px; color: #475569; text-transform: uppercase;">Independent Verification Evidence</h3>
        <pre style="background: #f8fafc; padding: 10px; border-radius: 6px; font-size: 12px; margin: 0; overflow-x: auto;">{evidence_json}</pre>
      </div>
    </div>

    <h2 style="font-size: 18px; color: #1e293b; margin-bottom: 16px;">Perceive-Plan-Act Execution Timeline</h2>
    {''.join(steps_html)}
  </div>
</body>
</html>"""

        with open(html_file, "w", encoding="utf-8") as f:
            f.write(content)

        return html_file
