"""
rl_agent.py — Q-learning reinforcement-learning agent.

State schema
------------
{
    "type":     str   # vuln/issue type  e.g. "sql_injection", "bug"
    "severity": str   # "high" | "medium" | "low"
    "source":   str   # "code" | "issue"
    "language": str   # "python" | "javascript" | "typescript" | "unknown" | …
}

Action space
------------
sanitize_input | prepared_statement | move_to_env | refactor_code | fix_issue_logic

Q-table is persisted to q_table.json in the same directory as this file.
"""
from __future__ import annotations

import json
import logging
import math
import random
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default hyper-parameters
# ---------------------------------------------------------------------------
DEFAULT_ALPHA: float = 0.2           # Learning rate
DEFAULT_GAMMA: float = 0.9           # Discount factor
DEFAULT_EPSILON: float = 0.35        # Initial exploration rate
DEFAULT_EPSILON_DECAY: float = 0.99  # Multiplied after every update
DEFAULT_EPSILON_MIN: float = 0.05    # Floor for exploration

Q_TABLE_PATH = Path(__file__).resolve().parent / "q_table.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_key(state: dict[str, str]) -> str:
    """Canonical string key for a state dict (order-independent)."""
    return "|".join([
        state.get("type", "unknown"),
        state.get("severity", "medium"),
        state.get("source", "code"),
        state.get("language", "unknown"),
    ])


def _softmax_max_prob(q_values: list[float]) -> float:
    """Softmax probability of the highest Q-value entry."""
    if not q_values:
        return 1.0
    if all(q == q_values[0] for q in q_values):
        return 1.0 / len(q_values)

    temperature = max(abs(v) for v in q_values if v != 0) or 1.0
    exp_vals = [math.exp(v / temperature) for v in q_values]
    total = sum(exp_vals)
    if total == 0:
        return 1.0 / len(q_values)
    return max(exp_vals) / total


# ---------------------------------------------------------------------------
# RLAgent
# ---------------------------------------------------------------------------

class RLAgent:
    """
    Tabular Q-learning agent.

    The Q-table maps ``state_key → {action → Q-value}``.
    Updates are persisted to *q_table_path* after every call to ``update()``.
    """

    def __init__(
        self,
        alpha: float = DEFAULT_ALPHA,
        gamma: float = DEFAULT_GAMMA,
        epsilon: float = DEFAULT_EPSILON,
        epsilon_decay: float = DEFAULT_EPSILON_DECAY,
        epsilon_min: float = DEFAULT_EPSILON_MIN,
        q_table_path: Path = Q_TABLE_PATH,
    ) -> None:
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.epsilon_min = epsilon_min
        self.q_table_path = q_table_path

        # Internal state
        self.q_table: dict[str, dict[str, float]] = {}
        self.episode_count: int = 0
        self.total_reward: float = 0.0

        self.load()

    # ------------------------------------------------------------------
    # Core RL methods
    # ------------------------------------------------------------------

    def choose_action(
        self, state: dict[str, str], actions: list[str]
    ) -> tuple[str, float]:
        """
        Epsilon-greedy action selection.

        Returns ``(chosen_action, confidence)`` where *confidence* is a
        softmax-derived probability of the chosen action being optimal.
        """
        if not actions:
            raise ValueError("RLAgent.choose_action: actions list must not be empty.")

        key = _state_key(state)

        # Explore
        if random.random() < self.epsilon:
            chosen = random.choice(actions)
            confidence = round(1.0 / len(actions), 4)
            logger.debug("RL [explore] state=%s action=%s conf=%.3f", key, chosen, confidence)
            return chosen, confidence

        # Exploit: highest Q-value among valid actions
        q_row: dict[str, float] = self.q_table.get(key, {})
        q_values = [q_row.get(a, 0.0) for a in actions]
        best_idx = q_values.index(max(q_values))
        chosen = actions[best_idx]
        confidence = round(_softmax_max_prob(q_values), 4)

        logger.debug(
            "RL [exploit] state=%s action=%s q=%.3f conf=%.3f",
            key, chosen, q_values[best_idx], confidence,
        )
        return chosen, confidence

    def update(
        self,
        state: dict[str, str],
        action: str,
        reward: float,
        next_state: dict[str, str] | None = None,
    ) -> None:
        """
        Apply the Q-learning update rule and persist the Q-table.

        Q(s, a) ← Q(s, a) + α · [r + γ · max_a′ Q(s′, a′) - Q(s, a)]
        """
        key = _state_key(state)
        if key not in self.q_table:
            self.q_table[key] = {}

        current_q = self.q_table[key].get(action, 0.0)

        # Estimate future value
        future_q = 0.0
        if next_state is not None:
            next_key = _state_key(next_state)
            next_row = self.q_table.get(next_key, {})
            if next_row:
                future_q = max(next_row.values())

        new_q = current_q + self.alpha * (reward + self.gamma * future_q - current_q)
        self.q_table[key][action] = round(new_q, 6)

        # Decay exploration
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        self.episode_count += 1
        self.total_reward += reward

        logger.info(
            "RL update | state=%s action=%s reward=%.1f q: %.4f→%.4f ε=%.4f",
            key, action, reward, current_q, new_q, self.epsilon,
        )
        self.save()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_q_values(self, state: dict[str, str]) -> dict[str, float]:
        """Return the action→Q-value mapping for *state* (empty dict if unseen)."""
        return dict(self.q_table.get(_state_key(state), {}))

    def best_action_for(self, state: dict[str, str], actions: list[str]) -> str | None:
        """Return the greedy-best action without exploration (for reporting)."""
        if not actions:
            return None
        q_row = self.q_table.get(_state_key(state), {})
        return max(actions, key=lambda a: q_row.get(a, 0.0))

    def get_stats(self) -> dict[str, Any]:
        """Return a statistics snapshot of the agent."""
        total_qa_pairs = sum(len(v) for v in self.q_table.values())
        return {
            "states_explored": len(self.q_table),
            "total_qa_pairs": total_qa_pairs,
            "episode_count": self.episode_count,
            "total_reward": round(self.total_reward, 2),
            "current_epsilon": round(self.epsilon, 6),
            "alpha": self.alpha,
            "gamma": self.gamma,
            "q_table_path": str(self.q_table_path),
        }

    def get_policy_table(self) -> dict[str, dict[str, Any]]:
        """
        Return a human-readable policy summary:
        state_key → { best_action, q_values }
        """
        policy: dict[str, dict[str, Any]] = {}
        for key, actions_q in self.q_table.items():
            if not actions_q:
                continue
            best = max(actions_q, key=lambda a: actions_q[a])
            policy[key] = {
                "best_action": best,
                "q_values": {a: round(q, 4) for a, q in actions_q.items()},
            }
        return policy

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Persist Q-table and metadata to *q_table_path*."""
        payload = {
            "q_table": self.q_table,
            "epsilon": self.epsilon,
            "episode_count": self.episode_count,
            "total_reward": self.total_reward,
            "alpha": self.alpha,
            "gamma": self.gamma,
        }
        try:
            self.q_table_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            logger.debug("RL Q-table saved (%d states)", len(self.q_table))
        except OSError as exc:
            logger.warning("RL: could not save Q-table to %s — %s", self.q_table_path, exc)

    def load(self) -> None:
        """Load Q-table and metadata from *q_table_path* if it exists."""
        if not self.q_table_path.exists():
            logger.info("RL: no Q-table at %s — starting fresh", self.q_table_path)
            return
        try:
            raw = json.loads(self.q_table_path.read_text(encoding="utf-8"))
            self.q_table = raw.get("q_table", {})
            self.epsilon = float(raw.get("epsilon", self.epsilon))
            self.episode_count = int(raw.get("episode_count", 0))
            self.total_reward = float(raw.get("total_reward", 0.0))
            logger.info(
                "RL: loaded Q-table — %d states, %d episodes, ε=%.4f",
                len(self.q_table), self.episode_count, self.epsilon,
            )
        except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
            logger.warning("RL: could not load Q-table — %s — starting fresh", exc)
            self.q_table = {}
            self.episode_count = 0
