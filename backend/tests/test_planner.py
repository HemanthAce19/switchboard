import json

import pytest

from app.planner import PlanError, parse_plan, validate_plan
from conftest import task


def test_valid_plan_is_returned_with_only_the_contract_fields():
    plan = [task("t1"), {**task("t2", ["t1"]), "extra": "dropped"}]
    assert validate_plan(plan, 8) == [task("t1"), task("t2", ["t1"])]


def test_duplicate_ids_rejected():
    with pytest.raises(PlanError, match="not unique"):
        validate_plan([task("t1"), task("t1")], 8)


def test_unknown_dependency_rejected():
    with pytest.raises(PlanError, match="unknown task t9"):
        validate_plan([task("t1"), task("t2", ["t9"])], 8)


def test_cycle_rejected():
    with pytest.raises(PlanError, match="cycle"):
        validate_plan([task("t1", ["t3"]), task("t2", ["t1"]), task("t3", ["t2"])], 8)


def test_self_dependency_is_a_cycle():
    with pytest.raises(PlanError, match="cycle"):
        validate_plan([task("t1", ["t1"]), task("t2")], 8)


def test_too_many_tasks_rejected():
    with pytest.raises(PlanError, match="maximum is 3"):
        validate_plan([task(f"t{n}") for n in range(4)], 3)


def test_empty_plan_rejected():
    with pytest.raises(PlanError, match="no tasks"):
        validate_plan([], 8)


def test_unknown_role_and_missing_field_rejected():
    with pytest.raises(PlanError, match="unknown role"):
        validate_plan([task("t1", role="wizard")], 8)
    with pytest.raises(PlanError, match="every task needs"):
        validate_plan([{"id": "t1"}], 8)


def test_parse_plan_reads_json_and_rejects_garbage():
    assert parse_plan(json.dumps({"tasks": [task("t1")]}), 8) == [task("t1")]
    for bad in ("not json", "[]", '{"jobs": []}'):
        with pytest.raises(PlanError):
            parse_plan(bad, 8)
