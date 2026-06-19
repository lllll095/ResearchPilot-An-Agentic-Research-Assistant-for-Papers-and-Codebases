# src/research_pilot/graph/policy.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetryPolicy:
    """Configuration for retry behavior in multi-agent graph workflows.

    Controls how the graph workflow handles failed review checks.

    Attributes:
        max_retries: Maximum number of times to retry a specialist subagent
                     after a failed review. Default is 1.
        fallback_to_writer: Whether to route to the writer subagent when
                            max_retries is exhausted. Default is True.
        retry_on_failures: Whether to retry when the specialist itself fails
                           (not just when review fails). Default is True.
        allowed_retry_agents: Which agents can be retried. Default is all.
    """

    max_retries: int = 1
    fallback_to_writer: bool = True
    retry_on_failures: bool = True
    allowed_retry_agents: tuple[str, ...] = ("code", "paper")
