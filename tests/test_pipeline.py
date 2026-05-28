from __future__ import annotations

import tempfile
import unittest

from researchbotbook.agents import evaluate_inbox, synthesize_problem
from researchbotbook.models import ContributionType
from researchbotbook.store import add_contribution, connect, create_problem, init_db


class FakeLLM:
    def complete(self, instructions: str, prompt: str) -> str:
        if "critic-verifier" in instructions:
            return (
                '{"relevance": 0.9, "novelty": 0.8, "clarity": 0.9, '
                '"grounding": 0.8, "compression": 0.85, '
                '"notes": "The contribution is sourced and constrains search."}'
            )
        return "# Synthesized Problem\n\n## Current Best Understanding\n\nUseful result."


class PipelineTest(unittest.TestCase):
    def test_contribution_can_be_evaluated_and_synthesized(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = f"{tmp}/test.sqlite3"
            with connect(db) as conn:
                init_db(conn)
                problem_id = create_problem(
                    conn,
                    "How should negative results be preserved?",
                    constraints="Refutations must remain searchable.",
                )
                add_contribution(
                    conn,
                    problem_id,
                    ContributionType.HYPOTHESIS,
                    "Negative results should be promoted because they constrain future searches.",
                    sources="doi:10.0000/example",
                )

                self.assertEqual(evaluate_inbox(conn), 1)
                synthesis_id = synthesize_problem(conn, problem_id)

                synthesis = conn.execute(
                    "SELECT * FROM synthesis_versions WHERE id = ?", (synthesis_id,)
                ).fetchone()
                self.assertEqual(synthesis["version"], 1)
                self.assertIn("Negative results should be promoted", synthesis["body"])

    def test_llm_agents_can_evaluate_and_synthesize(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = f"{tmp}/test.sqlite3"
            with connect(db) as conn:
                init_db(conn)
                problem_id = create_problem(conn, "How should agents synthesize?")
                add_contribution(
                    conn,
                    problem_id,
                    ContributionType.HYPOTHESIS,
                    "Agents should separate critique from synthesis because it reduces premature convergence.",
                    sources="arxiv:0000.00000",
                )

                llm = FakeLLM()
                self.assertEqual(evaluate_inbox(conn, llm=llm), 1)
                synthesis_id = synthesize_problem(conn, problem_id, llm=llm)

                synthesis = conn.execute(
                    "SELECT * FROM synthesis_versions WHERE id = ?", (synthesis_id,)
                ).fetchone()
                self.assertIn("Current Best Understanding", synthesis["body"])


if __name__ == "__main__":
    unittest.main()
