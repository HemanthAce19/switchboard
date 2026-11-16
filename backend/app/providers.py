"""LLM providers. Both expose the same coroutine:

    complete(agent, system, prompt, json_schema=None) -> (text, tokens)

`agent` is a task role or one of planner / synthesizer / critic. When
json_schema is given, the returned text is JSON matching that schema.
"""
import asyncio
import json
import random
import re

from openai import AsyncOpenAI


def make_provider(settings):
    """OpenAI when a key is configured, otherwise the offline demo provider."""
    if settings.openai_api_key:
        return OpenAIProvider(settings.openai_api_key, settings.openai_model)
    return DemoProvider(settings.demo_delay_s)


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, client=None):
        self.model = model
        # max_retries=0: the orchestrator does its own retries, and stacking the
        # SDK's retries on top would multiply the attempts.
        self.client = client or AsyncOpenAI(api_key=api_key, max_retries=0)

    async def complete(self, agent, system, prompt, json_schema=None):
        options = {}
        if json_schema is not None:
            # Structured Outputs on the Responses API: the reply is guaranteed
            # to be JSON that matches the schema.
            options["text"] = {
                "format": {"type": "json_schema", "name": agent, "schema": json_schema, "strict": True}
            }
        response = await self.client.responses.create(
            model=self.model, instructions=system, input=prompt, **options
        )
        return response.output_text, response.usage.total_tokens


DEMO_PLAN = [
    ("t1", "Research background and context", "researcher", [],
     "Gather the key facts, definitions and context needed for: {goal}"),
    ("t2", "Survey existing approaches", "researcher", [],
     "Find how others have approached this and what worked: {goal}"),
    ("t3", "Compare options and trade-offs", "analyst", ["t1", "t2"],
     "Using the research, compare the main options and their trade-offs for: {goal}"),
    ("t4", "Identify constraints and risks", "engineer", [],
     "List the practical constraints and risks that apply to: {goal}"),
    ("t5", "Draft an action plan", "engineer", ["t3", "t4"],
     "Turn the analysis and constraints into concrete steps for: {goal}"),
    ("t6", "Write the recommendation", "writer", ["t3"],
     "Write a short, clear recommendation based on the analysis for: {goal}"),
]

DEMO_TASK_BODY = {
    "researcher": (
        "**Findings**\n\n"
        "- The topic breaks down into a few well understood parts and one or two open questions.\n"
        "- Public sources agree on the fundamentals and differ mostly on emphasis.\n"
        "- The most useful material is recent, practical and written by people who did the work.\n\n"
        "**Gaps**\n\n"
        "- Hard numbers are scarce, so later steps should treat estimates as ranges."
    ),
    "analyst": (
        "| Option | Strength | Weakness |\n"
        "|--------|----------|----------|\n"
        "| Simple and direct | Fast to start, easy to explain | May not scale |\n"
        "| Thorough | Covers edge cases | Slower, costs more |\n"
        "| Hybrid | Balanced | Needs clear priorities |\n\n"
        "**Assessment:** the hybrid option fits best. Start simple, then add depth where the "
        "research shows real risk."
    ),
    "engineer": (
        "1. Define what done looks like and how it will be measured.\n"
        "2. Build the smallest version that proves the core idea.\n"
        "3. Test it against the main risks before adding anything else.\n"
        "4. Iterate in short cycles and review after each one.\n\n"
        "**Constraints:** limited time, limited budget, and dependencies on outside parties."
    ),
    "writer": (
        "Start with the simplest approach that works, check it against the biggest risks early, "
        "and only then invest in depth.\n\n"
        "> In short: start small, measure, then expand."
    ),
}

DEMO_FEEDBACK = (
    "The draft is clear but does not state its risks or open questions. "
    "Add a short section covering them."
)


class DemoProvider:
    """Offline stand-in for an LLM: canned, deterministic, goal-aware text."""

    name = "demo"
    model = None

    def __init__(self, delay_s: float):
        self.delay_s = delay_s

    async def complete(self, agent, system, prompt, json_schema=None):
        # Jittered pause so the UI shows tasks starting and finishing over time.
        await asyncio.sleep(self.delay_s * random.uniform(0.5, 1.5))
        goal = _labelled_line(prompt, "Goal")
        if agent == "planner":
            text = json.dumps({"tasks": [
                {"id": id, "title": title, "role": role,
                 "instructions": instructions.format(goal=goal), "depends_on": depends_on}
                for id, title, role, depends_on, instructions in DEMO_PLAN
            ]})
        elif agent == "critic":
            # The orchestrator reviews only the first draft, so always rejecting
            # shows the revision loop exactly once per run.
            text = json.dumps({"approved": False, "feedback": DEMO_FEEDBACK})
        elif agent == "synthesizer":
            text = _demo_answer(goal, prompt)
        else:
            title = _labelled_line(prompt, "Task")
            text = f"## {title}\n\n*Goal: {goal}*\n\n{DEMO_TASK_BODY[agent]}"
        return text, (len(prompt) + len(text)) // 4  # rough estimate: 4 characters per token


def _labelled_line(prompt: str, label: str) -> str:
    """Read a 'Label: value' line from a prompt built by the orchestrator."""
    match = re.search(rf"^{label}: (.*)$", prompt, re.MULTILINE)
    return match.group(1) if match else ""


def _demo_answer(goal: str, prompt: str) -> str:
    titles = re.findall(r"^\[Output of: (.*)\]$", prompt, re.MULTILINE)
    answer = (
        f"# {goal}\n\n"
        "*Demo mode: this answer is canned text, no model was called.*\n\n"
        "## Recommendation\n\n"
        "Start with the simplest approach that works, test it against the main risks early, "
        "and add depth only where the analysis shows it is needed.\n\n"
        "## What the agents contributed\n\n"
        + "\n".join(f"- {title}" for title in titles)
        + "\n\n## Next steps\n\n"
        "1. Agree on what success looks like.\n"
        "2. Build the smallest useful version.\n"
        "3. Review the results and decide what to deepen."
    )
    if "Reviewer feedback:" in prompt:
        answer += (
            "\n\n## Risks and open questions\n\n"
            "- Estimates are ranges, not measurements, until the first version is tested.\n"
            "- Outside dependencies can shift the timeline.\n"
            "- The preferred option should be revisited if the constraints change."
        )
    return answer
