#!/usr/bin/env python3
"""
Lightweight eval runner for the PartSelect agent.

Runs:
- 3 required case-study prompts
- 10 edge prompts

Outputs:
- backend_fastapi/reports/eval_report.md
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Tuple

import requests


BACKEND_URL = "http://127.0.0.1:8000"
CHAT_ENDPOINT = "/chat"
TIMEOUT_SECONDS = 45


@dataclass
class EvalCase:
    name: str
    prompt: str
    accepted_types: Tuple[str, ...]
    required_fields: Tuple[str, ...] = ()


REQUIRED_CASES: List[EvalCase] = [
    EvalCase(
        name="Install by Part ID",
        prompt="How can I install part number PS11752778?",
        accepted_types=("part_lookup",),
        required_fields=("part",),
    ),
    EvalCase(
        name="Compatibility Check",
        prompt="Is this part compatible with my WDT780SAEM1 model?",
        accepted_types=("compatibility", "clarification_needed"),
        required_fields=("model_id",),
    ),
    EvalCase(
        name="Symptom Troubleshooting",
        prompt="The ice maker on my Whirlpool fridge is not working. How can I fix it?",
        accepted_types=("symptom_solution", "model_required", "clarification_needed"),
        required_fields=(),
    ),
]


EDGE_CASES: List[EvalCase] = [
    EvalCase("Out of Scope Oven", "My oven does not heat up. Can you help?", ("clarification_needed",)),
    EvalCase("Noisy Dishwasher", "My dishwasher makes grinding noise.", ("symptom_solution", "model_required")),
    EvalCase("Model Only", "WDT780SAEM1", ("issue_required", "clarification_needed")),
    EvalCase("Part Only", "PS11752778", ("part_lookup",)),
    EvalCase("Garbage Input", "@@@ ???", ("clarification_needed",)),
    EvalCase("Broken Fridge Water", "Fridge water dispenser stopped working", ("symptom_solution", "model_required")),
    EvalCase("Follow-up Language", "Walk me through diagnostic checks step by step", ("symptom_solution", "model_required")),
    EvalCase("Compatibility Unknown Model", "Does PS11752778 fit model ABC123XYZ?", ("compatibility", "clarification_needed")),
    EvalCase("Short Symptom", "leaking", ("symptom_solution", "model_required", "clarification_needed")),
    EvalCase("Washer Out of Scope", "My washing machine won't spin", ("clarification_needed",)),
]


def run_case(session: requests.Session, case: EvalCase, conversation_id: str) -> Dict[str, Any]:
    started = time.perf_counter()
    response = session.post(
        f"{BACKEND_URL}{CHAT_ENDPOINT}",
        json={"conversation_id": conversation_id, "message": case.prompt},
        timeout=TIMEOUT_SECONDS,
    )
    latency_ms = (time.perf_counter() - started) * 1000

    if response.status_code != 200:
        return {
            "name": case.name,
            "prompt": case.prompt,
            "ok": False,
            "latency_ms": round(latency_ms, 2),
            "status_code": response.status_code,
            "response_type": "http_error",
            "notes": f"HTTP {response.status_code}",
        }

    payload = response.json()
    agent = payload.get("response", {})
    response_type = agent.get("type")

    type_ok = response_type in case.accepted_types
    # Clarification responses should not be penalized for missing structured fields
    # that are only expected on fully-resolved answer types.
    if response_type == "clarification_needed":
        fields_ok = True
    else:
        fields_ok = all(agent.get(field) is not None for field in case.required_fields)
    ok = type_ok and fields_ok

    notes = []
    if not type_ok:
        notes.append(f"type={response_type} not in {case.accepted_types}")
    if not fields_ok and case.required_fields:
        notes.append(f"missing required fields {case.required_fields}")

    return {
        "name": case.name,
        "prompt": case.prompt,
        "ok": ok,
        "latency_ms": round(latency_ms, 2),
        "status_code": 200,
        "response_type": response_type,
        "notes": "; ".join(notes) if notes else "ok",
    }


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    latencies = [row["latency_ms"] for row in results]
    success_count = sum(1 for row in results if row["ok"])

    sorted_lat = sorted(latencies)
    p95_index = max(0, int(round(0.95 * len(sorted_lat))) - 1)
    p95 = sorted_lat[p95_index]

    return {
        "total": len(results),
        "passed": success_count,
        "failed": len(results) - success_count,
        "pass_rate_pct": round((success_count / len(results)) * 100, 1) if results else 0.0,
        "latency_p50_ms": round(median(latencies), 2) if latencies else 0.0,
        "latency_p95_ms": round(p95, 2) if latencies else 0.0,
    }


def write_report(required_results: List[Dict[str, Any]], edge_results: List[Dict[str, Any]]) -> Path:
    reports_dir = Path(__file__).resolve().parents[1] / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "eval_report.md"

    required_summary = summarize(required_results)
    edge_summary = summarize(edge_results)

    generated = datetime.now(timezone.utc).isoformat()

    def format_rows(rows: List[Dict[str, Any]]) -> str:
        lines = ["| Case | Type | Latency (ms) | Pass | Notes |", "|---|---:|---:|---:|---|"]
        for row in rows:
            lines.append(
                f"| {row['name']} | `{row['response_type']}` | {row['latency_ms']} | "
                f"{'yes' if row['ok'] else 'no'} | {row['notes']} |"
            )
        return "\n".join(lines)

    content = f"""# Evaluation Report

Generated: `{generated}`  
Backend: `{BACKEND_URL}`

## Required Prompt Results

- Total: **{required_summary['total']}**
- Passed: **{required_summary['passed']}**
- Pass rate: **{required_summary['pass_rate_pct']}%**
- Latency p50: **{required_summary['latency_p50_ms']} ms**
- Latency p95: **{required_summary['latency_p95_ms']} ms**

{format_rows(required_results)}

## Edge Prompt Results

- Total: **{edge_summary['total']}**
- Passed: **{edge_summary['passed']}**
- Pass rate: **{edge_summary['pass_rate_pct']}%**
- Latency p50: **{edge_summary['latency_p50_ms']} ms**
- Latency p95: **{edge_summary['latency_p95_ms']} ms**

{format_rows(edge_results)}
"""

    report_path.write_text(content)
    return report_path


def main() -> None:
    session = requests.Session()
    required_results: List[Dict[str, Any]] = []
    edge_results: List[Dict[str, Any]] = []

    for idx, case in enumerate(REQUIRED_CASES, start=1):
        required_results.append(run_case(session, case, conversation_id=f"eval-required-{idx}"))

    for idx, case in enumerate(EDGE_CASES, start=1):
        edge_results.append(run_case(session, case, conversation_id=f"eval-edge-{idx}"))

    report_path = write_report(required_results, edge_results)
    print(json.dumps({"report": str(report_path)}, indent=2))


if __name__ == "__main__":
    main()
