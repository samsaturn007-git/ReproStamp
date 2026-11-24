"""Bounded planning, generation, review, and provider accounting."""

import time
from dataclasses import asdict, dataclass
from typing import Callable

from .app_context import RepoMap
from .app_source import PATCH_FORMAT, REVIEW_FORMAT, SEARCH_TERMS, TASK_FORMAT, TASKS, AppPatch, decode_object
from .integrity import hash_json
from .model_provider import Budget, ModelOutput, ModelProvider, OllamaProvider, OutputFormat, ProviderError, SuggestionError
from .model_provider import output_usage, review_request

SINGLE = "single"
PLAN_REVIEW = "plan-review"
ARMS = (SINGLE, PLAN_REVIEW)


@dataclass(frozen=True)
class Stage:
    name: str
    format: OutputFormat
    max_tokens: int


STAGES = {
    SINGLE: (Stage("generate", PATCH_FORMAT, 512),),
    PLAN_REVIEW: (Stage("plan", TASK_FORMAT, 128), Stage("generate", PATCH_FORMAT, 192),
                  Stage("review", REVIEW_FORMAT, 192)),
}


@dataclass(frozen=True)
class Workflow:
    arm: str
    description: str
    failure: str
    index: RepoMap
    input_budget: int
    model: str | None = None
    planner_model: str | None = None

    def provider(self, stage: Stage) -> ModelProvider:
        model = self.model if stage.name == "generate" else self.planner_model or self.model
        if model is None:
            raise ValueError("Select an installed local Ollama model.")
        return OllamaProvider(model, stage.format)

    def preview(self) -> dict:
        context, metrics = self.index.context(self.description, failure=self.failure)
        context["tasks"] = list(TASKS)
        steps = []
        for stage in STAGES[self.arm]:
            budget = Budget(self.input_budget, 4096, stage.max_tokens)
            step_context = {"requirements": self.description} if stage.name == "plan" else context
            review_request(step_context, stage.format.instructions, budget, {})
            steps.append({"stage": stage.name, "provider": self.provider(stage).identifier,
                          "budget": asdict(budget), "instructions": stage.format.instructions})
        return {"arm": self.arm, "context": context, "context_metrics": metrics, "steps": steps,
                "plan_review_context": "The planner may reorder eligible excerpts. Review includes the typed candidate."
                if self.arm == PLAN_REVIEW else None}


def parse_tasks(result: bytes) -> tuple[str, ...]:
    value = decode_object(result)
    if value.keys() != {"tasks", "search_terms"} or value["tasks"] != list(TASKS):
        raise ValueError("The planner must return the configure and present tasks in order.")
    search = value["search_terms"]
    if not isinstance(search, list) or len(search) > 5 or any(term not in SEARCH_TERMS for term in search):
        raise ValueError("The planner must choose at most five search terms from the supported symbols.")
    return tuple(search)


def run_stage(stage: Stage, context: dict, workflow: Workflow, calls: list[dict],
              mock: Callable[[str], ModelOutput] | None) -> bytes:
    budget = Budget(workflow.input_budget, 4096, stage.max_tokens)
    provider = workflow.provider(stage) if mock is None else None
    record = {"stage": stage.name, "provider": provider.identifier if provider else "deterministic",
              "status": "preparing", "invoked": False, "usage": None, "duration_ms": None}
    calls.append(record)
    started = time.monotonic()
    output = None
    try:
        encoded, binding, _ = review_request(context, stage.format.instructions, budget, {})
        record.update(binding, status="request_started", invoked=True)
        output = provider.propose(encoded, budget) if provider else mock(stage.name)
        if len(output.content) > budget.output_bytes:
            raise SuggestionError("output_budget_exceeded", "The app response exceeded the byte budget.")
        record["status"] = "received"
        return output.content
    except SuggestionError as error:
        if isinstance(error, ProviderError):
            output = error.output
        record.update(status=error.reason, detail=str(error))
        raise
    finally:
        record["duration_ms"] = round((time.monotonic() - started) * 1000)
        if output is not None:
            record["usage"] = output_usage(output)


def run_workflow(workflow: Workflow, evidence: dict, mock: Callable[[str], ModelOutput] | None = None) -> AppPatch:
    calls = evidence.setdefault("calls", [])
    stages = STAGES[workflow.arm]
    search_terms = ()
    if workflow.arm == PLAN_REVIEW:
        output = run_stage(stages[0], {"requirements": workflow.description}, workflow, calls, mock)
        try:
            search_terms = parse_tasks(output)
        except ValueError:
            calls[-1]["status"] = "invalid_plan"
            raise
    context, evidence["context_metrics"] = workflow.index.context(workflow.description, search_terms, workflow.failure)
    context["tasks"] = list(TASKS)
    gen_stage = stages[0] if workflow.arm == SINGLE else stages[1]
    output = run_stage(gen_stage, context, workflow, calls, mock)
    try:
        patch = AppPatch.decode(output)
    except ValueError:
        calls[-1]["status"] = "invalid_patch"
        raise
    evidence["candidate_sha256"] = hash_json(asdict(patch))
    if workflow.arm == PLAN_REVIEW:
        context["candidate"] = asdict(patch)
        output = run_stage(stages[2], context, workflow, calls, mock)
        try:
            patch = AppPatch.decode(output)
        except ValueError:
            calls[-1]["status"] = "invalid_review"
            raise
    evidence["final_sha256"] = hash_json(asdict(patch))
    evidence["tasks"] = list(TASKS)
    return patch
