from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ContributionType(StrEnum):
    HYPOTHESIS = "hypothesis"
    MECHANISM = "mechanism"
    LITERATURE_SUMMARY = "literature_summary"
    COUNTEREXAMPLE = "counterexample"
    REFUTATION = "refutation"
    VERIFICATION_REPORT = "verification_report"
    SYNTHESIS_UPDATE = "synthesis_update"
    CONCEPT_ABSTRACTION = "concept_abstraction"


class ContributionStatus(StrEnum):
    INBOX = "inbox"
    REVIEW = "review"
    SYNTHESIZED = "synthesized"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class ResearchProblem:
    id: int
    title: str
    scope: str
    assumptions: str
    constraints: str
    created_at: str


@dataclass(frozen=True)
class Contribution:
    id: int
    problem_id: int
    kind: ContributionType
    body: str
    agent_role: str
    sources: str
    status: ContributionStatus
    created_at: str


@dataclass(frozen=True)
class Evaluation:
    id: int
    contribution_id: int
    evaluator_role: str
    relevance: float
    novelty: float
    clarity: float
    grounding: float
    compression: float
    notes: str
    created_at: str

    @property
    def immediate_score(self) -> float:
        return round(
            (
                self.relevance
                + self.novelty
                + self.clarity
                + self.grounding
                + self.compression
            )
            / 5,
            3,
        )
