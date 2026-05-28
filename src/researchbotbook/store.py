from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import ContributionStatus, ContributionType, utc_now


DEFAULT_DB = "researchbotbook.sqlite3"


def db_path() -> Path:
    return Path(os.environ.get("RESEARCHBOTBOOK_DB", DEFAULT_DB))


def connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS research_problems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT '',
            assumptions TEXT NOT NULL DEFAULT '',
            constraints TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id INTEGER NOT NULL REFERENCES research_problems(id),
            kind TEXT NOT NULL,
            body TEXT NOT NULL,
            agent_role TEXT NOT NULL,
            sources TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contribution_id INTEGER NOT NULL REFERENCES contributions(id),
            evaluator_role TEXT NOT NULL,
            relevance REAL NOT NULL,
            novelty REAL NOT NULL,
            clarity REAL NOT NULL,
            grounding REAL NOT NULL,
            compression REAL NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS synthesis_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id INTEGER NOT NULL REFERENCES research_problems(id),
            version INTEGER NOT NULL,
            body TEXT NOT NULL,
            source_contribution_ids TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(problem_id, version)
        );

        CREATE TABLE IF NOT EXISTS concepts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            definition TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT '',
            objections TEXT NOT NULL DEFAULT '',
            source_contribution_id INTEGER REFERENCES contributions(id),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS citations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contribution_id INTEGER NOT NULL REFERENCES contributions(id),
            identifier TEXT NOT NULL,
            claim TEXT NOT NULL DEFAULT '',
            verification_status TEXT NOT NULL DEFAULT 'unverified',
            verifier_notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS protocol_experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            failure_mode TEXT NOT NULL,
            proposed_change TEXT NOT NULL,
            predicted_effect TEXT NOT NULL,
            evaluation_plan TEXT NOT NULL,
            rollback_criteria TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'proposed',
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def create_problem(
    conn: sqlite3.Connection,
    title: str,
    scope: str = "",
    assumptions: str = "",
    constraints: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO research_problems
            (title, scope, assumptions, constraints, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (title, scope, assumptions, constraints, utc_now()),
    )
    conn.commit()
    return int(cur.lastrowid)


def add_contribution(
    conn: sqlite3.Connection,
    problem_id: int,
    kind: ContributionType,
    body: str,
    agent_role: str = "human_seed",
    sources: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO contributions
            (problem_id, kind, body, agent_role, sources, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            problem_id,
            kind.value,
            body,
            agent_role,
            sources,
            ContributionStatus.INBOX.value,
            utc_now(),
        ),
    )
    for source in split_sources(sources):
        conn.execute(
            """
            INSERT INTO citations
                (contribution_id, identifier, created_at)
            VALUES (?, ?, ?)
            """,
            (cur.lastrowid, source, utc_now()),
        )
    conn.commit()
    return int(cur.lastrowid)


def split_sources(sources: str) -> Iterable[str]:
    return (source.strip() for source in sources.split(",") if source.strip())
