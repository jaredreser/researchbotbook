from __future__ import annotations

import argparse
import sqlite3
import sys

from .agents import evaluate_inbox, synthesize_problem
from .llm import OpenAIResponsesClient
from .models import ContributionType
from .store import add_contribution, connect, create_problem, init_db


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        with connect() as conn:
            if args.command == "init":
                init_db(conn)
                print("Initialized ResearchBotBook database.")
            elif args.command == "problem":
                handle_problem(conn, args)
            elif args.command == "contribution":
                handle_contribution(conn, args)
            elif args.command == "evaluate":
                init_db(conn)
                count = evaluate_inbox(conn, llm=build_llm(args))
                print(f"Evaluated {count} inbox contribution(s).")
            elif args.command == "synthesize":
                init_db(conn)
                synthesis_id = synthesize_problem(
                    conn, args.problem_id, llm=build_llm(args)
                )
                print(f"Created synthesis version record {synthesis_id}.")
            else:
                parser.print_help()
                return 2
    except (sqlite3.Error, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="researchbotbook")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize the local SQLite database.")

    problem = sub.add_parser("problem", help="Manage research problems.")
    problem_sub = problem.add_subparsers(dest="problem_command", required=True)
    create = problem_sub.add_parser("create", help="Create a research problem.")
    create.add_argument("title")
    create.add_argument("--scope", default="")
    create.add_argument("--assumptions", default="")
    create.add_argument("--constraints", default="")
    show = problem_sub.add_parser("show", help="Show a research problem.")
    show.add_argument("problem_id", type=int)
    problem_sub.add_parser("list", help="List research problems.")

    contribution = sub.add_parser("contribution", help="Manage contributions.")
    contribution_sub = contribution.add_subparsers(
        dest="contribution_command", required=True
    )
    add = contribution_sub.add_parser("add", help="Add a typed contribution.")
    add.add_argument("problem_id", type=int)
    add.add_argument("kind", choices=[kind.value for kind in ContributionType])
    add.add_argument("body")
    add.add_argument("--agent-role", default="human_seed")
    add.add_argument("--sources", default="")

    evaluate = sub.add_parser("evaluate", help="Evaluate inbox contributions.")
    add_llm_flags(evaluate)
    synthesize = sub.add_parser("synthesize", help="Create a synthesis version.")
    synthesize.add_argument("problem_id", type=int)
    add_llm_flags(synthesize)
    return parser


def add_llm_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Use the OpenAI Responses API instead of the deterministic baseline.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="OpenAI model to use with --llm. Defaults to OPENAI_MODEL or gpt-4.1-mini.",
    )


def build_llm(args: argparse.Namespace) -> OpenAIResponsesClient | None:
    if not getattr(args, "llm", False):
        return None
    return OpenAIResponsesClient.from_env(model=args.model)


def handle_problem(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    init_db(conn)
    if args.problem_command == "create":
        problem_id = create_problem(
            conn,
            args.title,
            scope=args.scope,
            assumptions=args.assumptions,
            constraints=args.constraints,
        )
        print(f"Created research problem {problem_id}.")
    elif args.problem_command == "list":
        rows = conn.execute(
            "SELECT id, title, created_at FROM research_problems ORDER BY id"
        ).fetchall()
        for row in rows:
            print(f"{row['id']}: {row['title']} ({row['created_at']})")
    elif args.problem_command == "show":
        show_problem(conn, args.problem_id)


def handle_contribution(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    init_db(conn)
    if args.contribution_command == "add":
        contribution_id = add_contribution(
            conn,
            args.problem_id,
            ContributionType(args.kind),
            args.body,
            agent_role=args.agent_role,
            sources=args.sources,
        )
        print(f"Created contribution {contribution_id}.")


def show_problem(conn: sqlite3.Connection, problem_id: int) -> None:
    problem = conn.execute(
        "SELECT * FROM research_problems WHERE id = ?", (problem_id,)
    ).fetchone()
    if problem is None:
        raise ValueError(f"Problem {problem_id} does not exist")

    print(f"# {problem['title']}")
    if problem["scope"]:
        print(f"Scope: {problem['scope']}")
    if problem["assumptions"]:
        print(f"Assumptions: {problem['assumptions']}")
    if problem["constraints"]:
        print(f"Constraints: {problem['constraints']}")

    contributions = conn.execute(
        """
        SELECT id, kind, status, body
        FROM contributions
        WHERE problem_id = ?
        ORDER BY id
        """,
        (problem_id,),
    ).fetchall()
    if contributions:
        print("\nContributions")
        for row in contributions:
            print(f"- {row['id']} [{row['kind']}/{row['status']}]: {row['body']}")

    synthesis = conn.execute(
        """
        SELECT version, body, created_at
        FROM synthesis_versions
        WHERE problem_id = ?
        ORDER BY version DESC
        LIMIT 1
        """,
        (problem_id,),
    ).fetchone()
    if synthesis:
        print(f"\nLatest Synthesis v{synthesis['version']} ({synthesis['created_at']})")
        print(synthesis["body"])


if __name__ == "__main__":
    raise SystemExit(main())
