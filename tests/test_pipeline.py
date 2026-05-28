from __future__ import annotations

import tempfile
import unittest

from researchbotbook.agents import evaluate_inbox, synthesize_problem
from researchbotbook.models import ContributionType
from researchbotbook.store import add_contribution, connect, create_problem, init_db


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


if __name__ == "__main__":
    unittest.main()
