"""Plan schema and validation.

The plan comes from an LLM, so it is checked before anything runs. A duplicate
id, a dependency on a task that does not exist, or a cycle would leave the
scheduler waiting forever for a task that can never become ready.
"""
import json

ROLES = ("researcher", "analyst", "engineer", "writer")
TASK_FIELDS = ("id", "title", "role", "instructions", "depends_on")

# JSON schema for structured output. Strict mode needs every property listed in
# "required" and additionalProperties set to false.
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "role": {"type": "string", "enum": list(ROLES)},
                    "instructions": {"type": "string"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                },
                "required": list(TASK_FIELDS),
                "additionalProperties": False,
            },
        }
    },
    "required": ["tasks"],
    "additionalProperties": False,
}


class PlanError(ValueError):
    pass


def parse_plan(text: str, max_tasks: int) -> list:
    """Turn the planner's JSON reply into a validated list of tasks."""
    try:
        tasks = json.loads(text)["tasks"]
    except (ValueError, KeyError, TypeError):
        raise PlanError("planner did not return a JSON object with a tasks list")
    return validate_plan(tasks, max_tasks)


def validate_plan(tasks: list, max_tasks: int) -> list:
    if not isinstance(tasks, list) or not tasks:
        raise PlanError("plan has no tasks")
    if len(tasks) > max_tasks:
        raise PlanError(f"plan has {len(tasks)} tasks, the maximum is {max_tasks}")

    for task in tasks:
        if not isinstance(task, dict) or any(field not in task for field in TASK_FIELDS):
            raise PlanError("every task needs id, title, role, instructions and depends_on")
        if task["role"] not in ROLES:
            raise PlanError(f"unknown role: {task['role']}")

    ids = [task["id"] for task in tasks]
    if len(set(ids)) != len(ids):
        raise PlanError("task ids are not unique")
    for task in tasks:
        for dependency in task["depends_on"]:
            if dependency not in ids:
                raise PlanError(f"task {task['id']} depends on unknown task {dependency}")

    # Cycle check: keep resolving tasks whose dependencies are all resolved.
    # If a pass resolves nothing while tasks remain, those tasks form a cycle.
    resolved = set()
    while len(resolved) < len(tasks):
        ready = [
            task["id"] for task in tasks
            if task["id"] not in resolved and all(d in resolved for d in task["depends_on"])
        ]
        if not ready:
            raise PlanError("plan has a dependency cycle")
        resolved.update(ready)

    return [{field: task[field] for field in TASK_FIELDS} for task in tasks]
