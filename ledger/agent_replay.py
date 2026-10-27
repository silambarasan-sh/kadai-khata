"""Offline Replay Engine for Kadai Khata Collections Agent.

Audits cryptographic hash chains and re-runs the verifier on recorded plans
without any model invocation or external network calls.
"""

from typing import Any, Dict, List, Tuple
from ledger.agent_verifier import verify_plan
from ledger.models import AgentRun, AgentStep, compute_step_hash


def verify_run_replay(run_id: int) -> Dict[str, Any]:
    """Recompute the hash chain and verify recorded plan offline."""
    try:
        run = AgentRun.objects.get(id=run_id)
    except AgentRun.DoesNotExist:
        return {
            "run_id": run_id,
            "error": f"AgentRun #{run_id} does not exist",
            "chain_valid": False,
            "verifier_verdicts_identical": False,
            "steps_count": 0,
        }

    steps: List[AgentStep] = list(run.steps.all().order_by("index"))
    if not steps:
        return {
            "run_id": run_id,
            "chain_valid": (run.final_hash == ""),
            "verifier_verdicts_identical": True,
            "steps_count": 0,
        }

    chain_valid = True
    expected_prev = ""

    for step in steps:
        if step.prev_hash != expected_prev:
            chain_valid = False
            break

        computed_hash = compute_step_hash(
            prev_hash=expected_prev,
            index=step.index,
            kind=step.kind,
            name=step.name,
            args_json=step.args_json,
            result_json=step.result_json,
            latency_ms=step.latency_ms,
            tokens=step.tokens,
        )

        if step.step_hash != computed_hash:
            chain_valid = False
            break

        expected_prev = step.step_hash

    if chain_valid:
        if run.final_hash != steps[-1].step_hash:
            chain_valid = False

    # Offline re-verification using recorded submit_plan or plan_json actions
    # Find submit_plan tool execution step
    submit_step = None
    for step in steps:
        if step.kind == "tool" and step.name == "submit_plan":
            submit_step = step
            break

    actions_to_verify = []
    if submit_step and submit_step.args_json.get("actions"):
        actions_to_verify = submit_step.args_json.get("actions", [])
    elif run.plan_json and "actions" in run.plan_json:
        # Fallback or recorded plan
        actions_to_verify = [
            {
                "customer_id": a.get("customer_id"),
                "action": a.get("action"),
                "tone": a.get("tone"),
                "claimed_balance": a.get("claimed_balance"),
                "claimed_days_overdue": a.get("claimed_days_overdue"),
                "reason": a.get("reason"),
                "evidence_entry_ids": a.get("evidence_entry_ids", []),
            }
            for a in run.plan_json.get("actions", [])
        ]

    replayed_verified = verify_plan(actions_to_verify)
    replayed_verdicts = [a["verified"] for a in replayed_verified.get("actions", [])]

    stored_actions = run.plan_json.get("actions", []) if run.plan_json else []
    stored_verdicts = [a.get("verified", False) for a in stored_actions]

    verdicts_identical = (replayed_verdicts == stored_verdicts)

    return {
        "run_id": run_id,
        "chain_valid": chain_valid,
        "verifier_verdicts_identical": verdicts_identical,
        "steps_count": len(steps),
        "actions_count": len(actions_to_verify),
        "source_label": run.source_label,
        "status": run.status,
    }
