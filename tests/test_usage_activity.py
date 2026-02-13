#!/usr/bin/env python3
"""Tests for UsageTracker and ActivityLog."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = "\033[92m✅ PASS\033[0m"
FAIL = "\033[91m❌ FAIL\033[0m"
results = {"pass": 0, "fail": 0}


def report(name, ok, detail=""):
    tag = PASS if ok else FAIL
    extra = f" — {detail}" if detail else ""
    print(f"  {tag} {name}{extra}")
    results["pass" if ok else "fail"] += 1


# ═══════════════════════════════════════════════════════════════════
# TEST: UsageTracker
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("TEST: UsageTracker")
print("=" * 60)

from agents.common.usage_tracker import UsageTracker

with tempfile.TemporaryDirectory() as tmpdir:
    db_path = os.path.join(tmpdir, "usage.db")
    tracker = UsageTracker(db_path=db_path)

    # Log some calls
    tracker.log_call("brain", "claude-sonnet-4", "anthropic", 1000, 500)
    tracker.log_call("builder", "deepseek-chat", "deepseek", 2000, 1000)
    tracker.log_call("brain", "claude-sonnet-4", "anthropic", 500, 200, duration_ms=1500)
    tracker.log_call("researcher", "qwen-max", "qwen", 800, 400, success=False, error_message="timeout")

    report("Log calls without error", True)

    # Daily summary
    summary = tracker.get_daily_summary()
    report("Daily summary has calls", summary["total_calls"] == 4)
    report("Daily summary has tokens", summary["total_tokens"] > 0)
    report("Daily summary per-agent", "brain" in summary["per_agent"])
    report("Brain has 2 calls", summary["per_agent"]["brain"]["calls"] == 2)

    # Agent summary
    brain_sum = tracker.get_agent_summary("brain")
    report("Agent summary calls", brain_sum["calls"] == 2)
    report("Agent summary tokens", brain_sum["total_tokens"] == 2200)

    # Model summary
    model_sum = tracker.get_model_summary()
    report("Model summary has models", len(model_sum["models"]) >= 2)

    # Total cost
    cost = tracker.get_total_cost()
    report("Total cost > 0", cost > 0, f"${cost:.6f}")

    # Cost estimation
    est = UsageTracker.estimate_cost("claude-sonnet-4", "anthropic", 1000000, 1000000)
    report("Claude Sonnet cost estimate", abs(est - 18.0) < 0.01, f"${est}")

    est_ds = UsageTracker.estimate_cost("deepseek-chat", "deepseek", 1000000, 1000000)
    report("DeepSeek cost estimate", abs(est_ds - 0.42) < 0.01, f"${est_ds}")

    # Cost report
    report_str = tracker.get_cost_report()
    report("Cost report is string", isinstance(report_str, str) and "Cost Report" in report_str)

    # Persistence: new instance reads same data
    tracker2 = UsageTracker(db_path=db_path)
    summary2 = tracker2.get_daily_summary()
    report("Data persists across instances", summary2["total_calls"] == 4)


# ═══════════════════════════════════════════════════════════════════
# TEST: ActivityLog
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("TEST: ActivityLog")
print("=" * 60)

from agents.common.activity_log import ActivityLog

with tempfile.TemporaryDirectory() as tmpdir:
    db_path = os.path.join(tmpdir, "activity.db")
    log = ActivityLog(db_path=db_path)

    # Log actions
    log.log("brain", "delegate", "Delegated build to builder", task_id="t1", project_id="p1")
    log.log("builder", "build", "Built feature X", task_id="t1", project_id="p1", feature_id="f1")
    log.log("brain", "memory_store", "Stored 3 memories")
    log.log("verifier", "verify", "Verified claims", metadata={"claims": 5})
    log.log("guardian", "security_scan", "Scanned output", success=False)

    report("Log actions without error", True)

    # Get recent
    recent = log.get_recent(limit=10)
    report("Get recent returns all", len(recent) == 5)
    report("Most recent first", recent[0]["agent"] == "guardian")

    # Get recent filtered
    brain_recent = log.get_recent(limit=10, agent="brain")
    report("Filtered by agent", len(brain_recent) == 2)

    # Get project activity
    proj = log.get_project_activity("p1")
    report("Project activity", len(proj) == 2)

    # Get timeline
    timeline = log.get_timeline(hours=1)
    report("Timeline returns entries", len(timeline) == 5)

    # Get summary
    summary = log.get_summary(days=7)
    report("Summary has agents", "brain" in summary["per_agent"])
    report("Summary action counts", summary["per_agent"]["brain"]["delegate"] == 1)

    # Metadata preserved
    verifier_entry = [e for e in recent if e["agent"] == "verifier"][0]
    report("Metadata preserved", verifier_entry["metadata"] == {"claims": 5})

    # Persistence
    log2 = ActivityLog(db_path=db_path)
    recent2 = log2.get_recent()
    report("Data persists across instances", len(recent2) == 5)


# ═══════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
total = results["pass"] + results["fail"]
print(f"RESULTS: {results['pass']}/{total} passed, {results['fail']} failed")
print("=" * 60)

if results["fail"] > 0:
    print("\n⚠️  Some tests failed!")
    sys.exit(1)
else:
    print("\n🎉 All tests passed!")
    sys.exit(0)
