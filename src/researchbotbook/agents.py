from __future__ import annotations

import sqlite3
from typing import Any

from .models import ContributionStatus, utc_now
from .llm import LLMClient, clamp_score, parse_json_object


PROMOTION_THRESHOLD = 0.68


def evaluate_inbox(conn: sqlite3.Connection, llm: LLMClient | None = None) -> int:
    rows = conn.execute(
        """
        SELECT c.id, c.kind, c.body, c.sources, p.title, p.scope, p.constraints
        FROM contributions c
        JOIN research_problems p ON p.id = c.problem_id
        WHERE c.status = ?
        ORDER BY c.id
        """,
        (ContributionStatus.INBOX.value,),
    ).fetchall()

    for row in rows:
        scores = (
            evaluate_contribution_with_llm(row, llm)
            if llm is not None
            else score_text(row["body"], row["sources"])
        )
        conn.execute(
            """
            INSERT INTO evaluations
                (
                    contribution_id, evaluator_role, relevance, novelty,
                    clarity, grounding, compression, notes, created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                str(scores["evaluator_role"]),
                scores["relevance"],
                scores["novelty"],
                scores["clarity"],
                scores["grounding"],
                scores["compression"],
                scores["notes"],
                utc_now(),
            ),
        )
        status = (
            ContributionStatus.REVIEW.value
            if scores["mean"] >= PROMOTION_THRESHOLD
            else ContributionStatus.ARCHIVED.value
        )
        conn.execute(
            "UPDATE contributions SET status = ? WHERE id = ?",
            (status, row["id"]),
        )

    conn.commit()
    return len(rows)


def score_text(body: str, sources: str) -> dict[str, float | str]:
    words = body.split()
    has_constraint_language = any(
        term in body.lower()
        for term in ["because", "therefore", "predict", "constraint", "refute"]
    )
    has_sources = bool(sources.strip())
    word_count = len(words)

    relevance = 0.75 if word_count >= 8 else 0.45
    novelty = 0.7 if has_constraint_language else 0.55
    clarity = 0.8 if 8 <= word_count <= 120 else 0.55
    grounding = 0.8 if has_sources else 0.35
    compression = 0.78 if word_count <= 80 else 0.55
    mean = (relevance + novelty + clarity + grounding + compression) / 5

    return {
        "relevance": relevance,
        "novelty": novelty,
        "clarity": clarity,
        "grounding": grounding,
        "compression": compression,
        "mean": mean,
        "notes": "Deterministic baseline score; replace with role-specific LLM evaluators.",
        "evaluator_role": "deterministic_reviewer",
    }


def evaluate_contribution_with_llm(
    row: sqlite3.Row, llm: LLMClient
) -> dict[str, float | str]:
    instructions = (
        "You are ResearchBotBook's critic-verifier agent. Evaluate one typed "
        "research contribution for downstream usefulness, not popularity. "
        "Return only JSON with keys: relevance, novelty, clarity, grounding, "
        "compression, notes. Scores must be numbers from 0 to 1. Notes must be "
        "one concise sentence that names the strongest reason for the score."
    )
    prompt = f"""Research problem: {row['title']}
Scope: {row['scope']}
Known constraints: {row['constraints']}

Contribution type: {row['kind']}
Contribution body:
{row['body']}

Sources: {row['sources'] or 'none supplied'}
"""
    parsed = parse_json_object(llm.complete(instructions, prompt))
    scores = {
        "relevance": clamp_score(parsed.get("relevance")),
        "novelty": clamp_score(parsed.get("novelty")),
        "clarity": clamp_score(parsed.get("clarity")),
        "grounding": clamp_score(parsed.get("grounding")),
        "compression": clamp_score(parsed.get("compression")),
        "notes": str(parsed.get("notes", "LLM evaluator returned no notes.")),
        "evaluator_role": "llm_critic_verifier",
    }
    scores["mean"] = mean_score(scores)
    return scores


def mean_score(scores: dict[str, Any]) -> float:
    return (
        float(scores["relevance"])
        + float(scores["novelty"])
        + float(scores["clarity"])
        + float(scores["grounding"])
        + float(scores["compression"])
    ) / 5


def synthesize_problem(
    conn: sqlite3.Connection, problem_id: int, llm: LLMClient | None = None
) -> int:
    problem = conn.execute(
        "SELECT * FROM research_problems WHERE id = ?", (problem_id,)
    ).fetchone()
    if problem is None:
        raise ValueError(f"Problem {problem_id} does not exist")

    contributions = conn.execute(
        """
        SELECT c.id, c.kind, c.body
        FROM contributions c
        WHERE c.problem_id = ? AND c.status = ?
        ORDER BY c.id
        """,
        (problem_id, ContributionStatus.REVIEW.value),
    ).fetchall()
    if not contributions:
        raise ValueError("No reviewed contributions are available for synthesis")

    latest = conn.execute(
        """
        SELECT MAX(version) AS version
        FROM synthesis_versions
        WHERE problem_id = ?
        """,
        (problem_id,),
    ).fetchone()
    version = int(latest["version"] or 0) + 1
    body = (
        build_synthesis_with_llm(problem, contributions, llm)
        if llm is not None
        else build_synthesis(problem["title"], contributions)
    )
    source_ids = ",".join(str(row["id"]) for row in contributions)

    cur = conn.execute(
        """
        INSERT INTO synthesis_versions
            (problem_id, version, body, source_contribution_ids, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (problem_id, version, body, source_ids, utc_now()),
    )
    conn.execute(
        """
        UPDATE contributions
        SET status = ?
        WHERE problem_id = ? AND status = ?
        """,
        (
            ContributionStatus.SYNTHESIZED.value,
            problem_id,
            ContributionStatus.REVIEW.value,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def build_synthesis(title: str, contributions: list[sqlite3.Row]) -> str:
    lines = [
        f"# {title}",
        "",
        "## Current Synthesis",
        "",
        "This synthesis was generated from reviewed contributions.",
        "",
        "## Integrated Contributions",
    ]
    for row in contributions:
        lines.append(f"- [{row['kind']}] {row['body']}")
    lines.extend(
        [
            "",
            "## Open Questions",
            "",
            "- Which claims have source-level verification?",
            "- Which negative results should become explicit constraints?",
            "- Which concepts are reusable across adjacent problems?",
        ]
    )
    return "\n".join(lines)


def build_synthesis_with_llm(
    problem: sqlite3.Row, contributions: list[sqlite3.Row], llm: LLMClient
) -> str:
    instructions = (
        "You are ResearchBotBook's synthesizer agent. Produce a concise, "
        "versioned canonical synthesis from reviewed contributions. Preserve "
        "uncertainty, distinguish evidence from speculation, elevate useful "
        "negative results, and end with concrete open questions. Return "
        "Markdown only."
    )
    items = "\n".join(
        f"- Contribution {row['id']} [{row['kind']}]: {row['body']}"
        for row in contributions
    )
    prompt = f"""Research problem: {problem['title']}
Scope: {problem['scope']}
Assumptions: {problem['assumptions']}
Known constraints: {problem['constraints']}

Reviewed contributions:
{items}

Write the canonical synthesis with these sections:
# {problem['title']}
## Current Best Understanding
## Evidence and Constraints
## Useful Refutations or Negative Results
## Reusable Concepts
## Open Questions
"""
    return llm.complete(instructions, prompt).strip()
