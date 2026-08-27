"""Structural contracts for the maintained pytest suite."""

from __future__ import annotations

import ast
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parents[1]
TEST_AREAS = ("unit", "integration", "harbor", "eval_support")


def test_every_test_module_has_a_contract_area_and_module_description():
    paths = [path for area in TEST_AREAS for path in (TESTS_ROOT / area).glob("test_*.py")]

    assert paths
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert ast.get_docstring(tree), path


def test_every_top_level_test_has_a_behavior_oriented_name():
    paths = [path for area in TEST_AREAS for path in (TESTS_ROOT / area).glob("test_*.py")]

    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                assert len(node.name.split("_")) >= 3, path
