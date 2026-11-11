import ast
import json
import os
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "main.py"
SOURCE_TEXT = SOURCE.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE_TEXT)


def load_persistence_helpers():
    """Load the three pure persistence helpers without importing Kivy."""
    wanted = {"empty_stats", "load_stats", "write_stats_safely"}
    nodes = [node for node in TREE.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name in wanted]
    namespace = {"json": json, "os": os}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.helpers = load_persistence_helpers()
        self.temp = tempfile.TemporaryDirectory()
        self.app = type("AppStub", (), {"data_dir": self.temp.name})()

    def tearDown(self):
        self.temp.cleanup()

    def test_defaults_are_complete(self):
        stats = self.helpers["empty_stats"]()
        self.assertEqual(stats["games"], 0)
        self.assertEqual(stats["wins"], [0, 0, 0, 0])
        self.assertEqual(stats["captures"], [0, 0, 0, 0])
        self.assertEqual(stats["players"], {})

    def test_corrupt_file_returns_defaults(self):
        path = Path(self.temp.name) / "stats.json"
        path.write_text("{broken", encoding="utf-8")
        stats = self.helpers["load_stats"](self.app)
        self.assertEqual(stats["games"], 0)

    def test_load_repairs_bad_numeric_values(self):
        path = Path(self.temp.name) / "stats.json"
        path.write_text(json.dumps({"games": -8, "sixes": True,
                                    "wins": [2, "bad", -1, 4],
                                    "captures": [1, 2, 3, 4]}), encoding="utf-8")
        stats = self.helpers["load_stats"](self.app)
        self.assertEqual(stats["games"], 0)
        self.assertEqual(stats["sixes"], 0)
        self.assertEqual(stats["wins"], [2, 0, 0, 4])
        self.assertEqual(stats["captures"], [1, 2, 3, 4])

    def test_atomic_save_round_trip(self):
        data = self.helpers["empty_stats"]()
        data["games"] = 3
        self.assertTrue(self.helpers["write_stats_safely"](self.app, data))
        loaded = self.helpers["load_stats"](self.app)
        self.assertEqual(loaded["games"], 3)
        self.assertFalse((Path(self.temp.name) / "stats.json.tmp").exists())


class SourceReleaseInvariantTests(unittest.TestCase):
    def test_main_guard_is_after_app_class(self):
        self.assertGreater(SOURCE_TEXT.rfind('if __name__ == "__main__"'),
                           SOURCE_TEXT.find("class LudoApp"))
        self.assertEqual(SOURCE_TEXT.count('if __name__ == "__main__"'), 1)

    def test_remote_roll_does_not_execute_remote_move(self):
        game = next(n for n in ast.walk(TREE)
                    if isinstance(n, ast.ClassDef) and n.name == "LudoGame")
        method = next(n for n in game.body
                      if isinstance(n, ast.FunctionDef) and n.name == "on_remote_roll")
        calls = [n.func.attr for n in ast.walk(method)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
        self.assertNotIn("start_move", calls)
        self.assertNotIn("end_turn", calls)

    def test_remote_state_has_consistency_guards(self):
        game = next(n for n in ast.walk(TREE)
                    if isinstance(n, ast.ClassDef) and n.name == "LudoGame")
        method = next(n for n in game.body
                      if isinstance(n, ast.FunctionDef) and n.name == "load_state")
        text = ast.unparse(method)
        self.assertIn("self.kinds[current] == 'off'", text)
        self.assertIn("not all((pos == FINISH_POSITION for pos in tokens[winner]))", text)

    def test_host_listener_can_accept_rejoin(self):
        network = next(n for n in ast.walk(TREE)
                       if isinstance(n, ast.ClassDef) and n.name == "Network")
        method = next(n for n in network.body
                      if isinstance(n, ast.FunctionDef) and n.name == "_accept")
        text = ast.unparse(method)
        self.assertIn("self._read_loop(conn, gen)", text)
        self.assertIn("if gen != self.gen or not self.running", text)


if __name__ == "__main__":
    unittest.main()
