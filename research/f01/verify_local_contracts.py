"""Run bounded F01 code-reading checks using only the standard library.

This does NOT import/start either application or run its pytest suite.
Pure scoring functions and a worker coroutine are compiled from the checked-out
source without altering their bodies. Fixture verdicts and the worker's inner
operation are controlled inputs, not real LLM outputs or production jobs.
"""
from __future__ import annotations

import ast
import asyncio
import copy
import hashlib
import json
import logging
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "agent-core"
SWARM = ROOT / "jiuwenswarm"
SCORING = CORE / "openjiuwen/rsi/harness_rsi/evaluator/judger/scoring.py"
BASE = CORE / "openjiuwen/rsi/harness_rsi/evaluator/judger/base.py"
REQUIREMENTS = CORE / "openjiuwen/rsi/harness_rsi/evaluator/requirement_results.py"
GRADING = CORE / "openjiuwen/rsi/harness_rsi/data_loader/grading_contract.py"
FIXTURES = CORE / "tests/unit_tests/rsi/test_evaluator_agent.py"
WEIGHTED_FIXTURES = CORE / "tests/unit_tests/rsi/test_weighted_judge_contract.py"
WORKER = SWARM / "jiuwenswarm/agents/harness/common/rsi/worker.py"


def definitions(path, names, namespace, *, class_name=None):
    """Compile selected original definitions; never rewrite function bodies."""
    tree = ast.parse(path.read_text())
    nodes = tree.body
    if class_name:
        nodes = next(n.body for n in nodes if isinstance(n, ast.ClassDef) and n.name == class_name)
    chosen = [n for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    assert {n.name for n in chosen} == set(names)
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future] + chosen, type_ignores=[]))
    exec(compile(module, str(path), "exec"), namespace)


def scoring_checks():
    requirements = runpy.run_path(str(REQUIREMENTS))
    grading = runpy.run_path(str(GRADING))
    namespace = {
        "normalize_grading_case": grading["normalize_grading_case"],
        "requirement_results_contract": requirements["requirement_results_contract"],
    }
    definitions(BASE, ["_reference_answer"], namespace)
    tree = ast.parse(SCORING.read_text())
    # Keep every scoring definition and standard-library import; replace only
    # project imports with the original functions loaded immediately above.
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.ImportFrom) and (node.module or "").startswith("openjiuwen.")
    )]
    exec(compile(tree, str(SCORING), "exec"), namespace)
    fixture_ns = {}
    definitions(FIXTURES, ["_case", "_output"], fixture_ns)
    score_fn = namespace["score_judge_output"]
    contract_fn = namespace["scoring_contract"]
    case = fixture_ns["_case"]()
    verdict = fixture_ns["_output"]()
    score, normalized, reqs = score_fn(verdict, *contract_fn(case))
    assert score == 0.5
    assert len(reqs["items"]) == 2
    assert [x["passed"] for x in reqs["items"]] == [True, False]

    invalid = copy.deepcopy(verdict)
    invalid["behaviors"].pop()
    try:
        score_fn(invalid, *contract_fn(case))
    except ValueError as error:
        missing_id_error = str(error)
    else:
        raise AssertionError("Missing criterion was accepted")

    test_tree = ast.parse(WEIGHTED_FIXTURES.read_text())
    rubric_node = next(n for n in test_tree.body if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "RUBRIC" for t in n.targets))
    weighted_ns = {"RUBRIC": ast.literal_eval(rubric_node.value)}
    definitions(WEIGHTED_FIXTURES, ["_case", "_verdict"], weighted_ns)
    weighted_case = weighted_ns["_case"]()
    weighted_verdict = weighted_ns["_verdict"]()
    weighted_verdict["overall_score"] = 1.0
    weighted_verdict["behaviors"][0]["weight"] = 1000000
    weighted_verdict["forbidden_hits"][0]["penalty"] = 0
    sub_score, sub_norm, _ = score_fn(weighted_verdict, *contract_fn(weighted_case), penalty_mode="subtract")
    ceiling_score, _, _ = score_fn(weighted_verdict, *contract_fn(weighted_case), penalty_mode="ceiling")
    assert abs(sub_score - 0.7) < 1e-9
    assert abs(ceiling_score - 0.8) < 1e-9
    assert sub_norm["behaviors"][0]["weight"] == 0.8
    assert sub_norm["forbidden_hits"][0]["penalty"] == 0.06
    return {
        "fixture": "test_evaluator_agent._case/_output: total present, units missing; controlled verdict",
        "continuous_score": score,
        "normalized": normalized,
        "requirement_results": reqs,
        "missing_criterion_rejected": missing_id_error,
        "weighted_test_fixture": {"subtract": sub_score, "ceiling": ceiling_score,
                                  "untrusted_model_weight_ignored": True},
        "not_executed": "LlmAsJudgeJudger, CaseRunner, threshold-to-JudgeResult conversion, real LLM",
    }


async def cancellation_check():
    namespace = {"asyncio": asyncio, "logger": logging.getLogger("f01-check")}
    definitions(WORKER, ["_run_until_slot_free"], namespace, class_name="RsiWorker")
    started, release = asyncio.Event(), asyncio.Event()
    inner_tasks = []

    async def controlled_inner(task_id, *, resume, generation):
        inner_tasks.append(asyncio.current_task())
        started.set()
        await release.wait()

    worker = SimpleNamespace(_execute_task=controlled_inner, _slot_released={}, _winding_down=set())
    outer = asyncio.create_task(namespace["_run_until_slot_free"](worker, "controlled-case", generation=1))
    await asyncio.wait_for(started.wait(), timeout=1)
    outer.cancel()
    await asyncio.gather(outer, return_exceptions=True)
    observed = {
        "outer_cancelled": outer.cancelled(),
        "inner_done_after_outer_cancel": inner_tasks[0].done(),
        "inner_cancelled_after_outer_cancel": inner_tasks[0].cancelled(),
        "slot_reference_removed": not worker._slot_released,
        "inner_registered_as_winding_down": bool(worker._winding_down),
    }
    assert observed == {
        "outer_cancelled": True,
        "inner_done_after_outer_cancel": False,
        "inner_cancelled_after_outer_cancel": False,
        "slot_reference_removed": True,
        "inner_registered_as_winding_down": False,
    }
    release.set()
    await asyncio.wait_for(inner_tasks[0], timeout=1)
    observed["controlled_inner_released_and_awaited_after_check"] = True
    observed["not_executed"] = "RsiWorker.cancel/store/Provider/real engine; this checks the original outer coroutine only"
    return observed


def main():
    sources = [SCORING, BASE, REQUIREMENTS, GRADING, FIXTURES, WEIGHTED_FIXTURES, WORKER]
    result = {
        "scope": "Original pure functions and one original coroutine with controlled inputs; not project pytest or end-to-end validation",
        "python": sys.version,
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        "scoring": scoring_checks(),
        "cancellation": asyncio.run(cancellation_check()),
        "result": "pass",
    }
    output = Path(__file__).parent / "evidence/local_contract_checks.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"result": result["result"], "output": str(output),
                      "continuous_score": result["scoring"]["continuous_score"],
                      "weighted_scores": result["scoring"]["weighted_test_fixture"],
                      "cancellation": result["cancellation"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
