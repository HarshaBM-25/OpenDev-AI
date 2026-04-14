"""
reward.py — Reward calculator for the RL Q-learning agent.

Maps PR / execution outcomes to scalar rewards so the agent can learn
which fix strategies produce the best real-world results.

Reward schedule
---------------
+30  secret removed (secret_removed flag)
+25  issue closed   (pr_status.issue_closed)
+20  PR merged      (pr_status.merged)
+15  fix confirmed  (re-scan shows vulnerability gone)
+10  tests passed
 -5  no change produced
-10  tests failed
-25  build failed
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reward / penalty constants
# ---------------------------------------------------------------------------
REWARD_SECRET_REMOVED: float = 30.0
REWARD_ISSUE_CLOSED: float = 25.0
REWARD_PR_MERGED: float = 20.0
REWARD_FIX_CONFIRMED: float = 15.0
REWARD_TESTS_PASSED: float = 10.0
PENALTY_NO_CHANGE: float = -5.0
PENALTY_TESTS_FAILED: float = -10.0
PENALTY_BUILD_FAILED: float = -25.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_reward(
    result: dict[str, Any],
    pr_status: dict[str, Any] | None = None,
) -> tuple[float, dict[str, Any]]:
    """
    Calculate the total scalar reward for one fix episode.

    Parameters
    ----------
    result :
        Dict produced by executor with boolean flags:
        ``tests_passed``, ``tests_failed``, ``build_failed``,
        ``issue_fixed``, ``secret_removed``, ``no_change``.
    pr_status :
        Optional dict from ``github_service.get_pr_status()`` with keys:
        ``merged`` (bool), ``state`` ("open"|"closed"), ``issue_closed`` (bool).

    Returns
    -------
    (total_reward, breakdown_dict)
        *breakdown_dict* contains:
        ``total``, ``breakdown`` (component → value),
        ``positive`` (sum of gains), ``negative`` (sum of penalties).
    """
    breakdown: dict[str, float] = {}

    # ---- Execution-time signals ---------------------------------------- #
    if result.get("tests_passed"):
        breakdown["tests_passed"] = REWARD_TESTS_PASSED

    if result.get("tests_failed"):
        breakdown["tests_failed"] = PENALTY_TESTS_FAILED

    if result.get("build_failed"):
        breakdown["build_failed"] = PENALTY_BUILD_FAILED

    if result.get("issue_fixed"):
        breakdown["fix_confirmed"] = REWARD_FIX_CONFIRMED

    if result.get("secret_removed"):
        breakdown["secret_removed"] = REWARD_SECRET_REMOVED

    if result.get("no_change"):
        breakdown["no_change"] = PENALTY_NO_CHANGE

    # ---- PR / remote signals ------------------------------------------- #
    if pr_status:
        if pr_status.get("merged"):
            breakdown["pr_merged"] = REWARD_PR_MERGED

        if pr_status.get("issue_closed") or pr_status.get("state") == "closed":
            breakdown["issue_closed"] = REWARD_ISSUE_CLOSED

    total = round(sum(breakdown.values()), 2)
    positive = round(sum(v for v in breakdown.values() if v > 0), 2)
    negative = round(sum(v for v in breakdown.values() if v < 0), 2)

    reward_info = {
        "total": total,
        "breakdown": breakdown,
        "positive": positive,
        "negative": negative,
    }

    logger.info(
        "reward: total=%.1f  positive=%.1f  negative=%.1f  breakdown=%s",
        total, positive, negative, breakdown,
    )
    return total, reward_info


def estimate_immediate_reward(result: dict[str, Any]) -> float:
    """
    Quick reward estimate using only execution-time signals (no PR required).
    Useful for updating the RL agent immediately after applying a fix,
    before waiting for the PR to be reviewed.
    """
    total, _ = calculate_reward(result, pr_status=None)
    return total


def describe_reward(reward_info: dict[str, Any]) -> str:
    """Return a human-readable reward summary for logging / PR descriptions."""
    lines = [f"RL reward: {reward_info['total']:+.1f}"]
    for component, value in reward_info.get("breakdown", {}).items():
        sign = "+" if value >= 0 else ""
        lines.append(f"  {component}: {sign}{value:.1f}")
    return "\n".join(lines)
