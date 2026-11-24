import argparse
import hashlib
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from .integrity import hash_json
from .model_provider import (
    INSTRUCTIONS, Budget, DeterministicProvider, ModelOutput, ModelProvider, OllamaProvider, OpenAIProvider,
    ProviderError, SuggestionError, output_usage, review_request,
)
from .profile import Profile, load_profile
from .receipt import distinct_object, matrix, verify_bundle
from .receipt_schema import NUMBERS
from .repository import Entry, Repository, RepositoryError
from .run_inputs import run_plan


WORKFLOW_PATHS = {".github", ".gitlab", ".circleci", ".buildkite", ".gitlab-ci.yml", "azure-pipelines.yml"}


def add_suggestion_command(commands) -> None:
    command = commands.add_parser("suggest", help="review context and export a bounded repair suggestion")
    command.add_argument("--repo", required=True, help="approved local Git checkout")
    command.add_argument("--profile", required=True, help="owner-managed profile outside the application")
    command.add_argument("--receipt", required=True, help="intact receipt ZIP with the reproduced baseline assertion")
    command.add_argument("--issue-file", type=Path, required=True, help="plain-text issue summary")
    command.add_argument("--file", action="append", required=True, help="approved source file at the base (repeatable)")
    command.add_argument("--out", type=Path, required=True, help="new directory for proposal metadata and patch")
    command.add_argument("--approve", metavar="SHA256", help="approval digest from a reviewed preview")
    provider = command.add_mutually_exclusive_group(required=True)
    provider.add_argument("--response-file", type=Path, help="local deterministic provider response JSON")
    provider.add_argument("--openai-model", help="opt in to the OpenAI Responses API with this model")
    provider.add_argument("--ollama-model", help="use an installed model on the local Ollama server")
    command.add_argument("--max-input-bytes", type=int, default=24_576)
    command.add_argument("--max-output-bytes", type=int, default=12_288)
    command.add_argument("--max-output-tokens", type=int, default=2048)
    command.set_defaults(handler=suggest)


def baseline_evidence(receipt: dict, repo: Repository, profile: Profile) -> list[dict]:
    payload = receipt["payload"]
    base = payload["base_sha"]
    if base is None or payload["inputs"] is None or payload["plan"] != run_plan(profile):
        raise SuggestionError("evidence_mismatch", "The receipt needs a base commit and the approved case and browser plan.")
    roots = repo.git("rev-list", "--max-parents=0", repo.resolve(base)).decode().split()
    if hash_json(sorted(roots)) != payload["inputs"]["repository_sha256"]:
        raise SuggestionError("evidence_mismatch", "The receipt does not match the approved Git history.")

    expected = profile.expected_failure
    evidence = []
    cells = matrix(payload)
    for engine in profile.engines:
        for number in NUMBERS:
            case = cells[engine, expected.case_id, "base", number]
            assertion = case.get("assertion")
            if (case["status"] != "assertion_failed" or case.get("attempt_reason") is not None
                    or assertion is None or assertion["id"] != expected.assertion_id
                    or assertion["actual"] != expected.baseline_actual):
                raise SuggestionError("baseline_not_reproduced", "The approved assertion must reproduce on every base attempt.")
            evidence.append({"engine": engine, "attempt": number, "case_id": expected.case_id, **assertion})
    return evidence


def source_context(repo: Repository, tree: dict[str, Entry], profile: Profile,
                   issue_file: Path, paths: list[str], limit: int) -> dict:
    budget_error = SuggestionError("input_budget_exceeded", "The context exceeded the configured input byte budget.")
    with issue_file.open("rb") as issue:
        raw_issue = issue.read(limit + 1)
    remaining = limit - len(raw_issue)
    if remaining < 0:
        raise budget_error
    summary = raw_issue.decode("utf-8")
    if not summary.strip():
        raise SuggestionError("invalid_context", "Provide a nonempty issue summary.")
    if len(set(paths)) != len(paths):
        raise SuggestionError("invalid_context", "Select each application file once.")
    files = {}
    for path in paths:
        if path not in tree or not profile.allows(path) or WORKFLOW_PATHS.intersection(PurePosixPath(path.lower()).parts):
            raise SuggestionError("out_of_scope", f"Select an existing, editable application file: {path!r}.")
        blob = tree[path].blob
        if int(repo.git("cat-file", "-s", blob)) > remaining:
            raise budget_error
        raw = repo.git("cat-file", "blob", blob)
        if b"\0" in raw:
            raise SuggestionError("invalid_context", f"The selected file is binary: {path!r}.")
        files[path] = raw.decode("utf-8")
        remaining -= len(raw)
    return {"issue_summary": summary, "application_files": files}


def validate_patch(repo: Repository, base: str, allowed: set[str], diff: str) -> bytes:
    if any(ord(char) < 32 and char not in "\t\n\r" or ord(char) == 127 for char in diff):
        raise SuggestionError("malformed_output", "The diff contains unsupported control characters.")
    patch = diff.encode("utf-8")
    git_apply = ("-c", "apply.ignoreWhitespace=no", "apply", "-p1", "--whitespace=nowarn")
    try:
        stats = repo.git(*git_apply, "--numstat", "-z", "-", input=patch)
        summary = repo.git(*git_apply, "--summary", "-", input=patch)
    except RepositoryError as error:
        raise SuggestionError("invalid_patch", "Git could not parse the unified diff.") from error
    if summary:
        raise SuggestionError("out_of_scope", "A proposal may only modify existing source text.")
    touched = set()
    for line in stats.decode("utf-8").split("\0")[:-1]:
        added, removed, path = line.split("\t", 2)
        if path not in allowed or not added.isdecimal() or not removed.isdecimal():
            raise SuggestionError("out_of_scope", "The diff changes an unselected path or contains binary edits.")
        if path in touched or int(added) + int(removed) == 0:
            raise SuggestionError("invalid_patch", "Submit a single nonempty text change per file.")
        touched.add(path)
    if not touched:
        raise SuggestionError("invalid_patch", "The diff contains no source changes.")
    with tempfile.TemporaryDirectory(prefix="reprostamp-suggestion-") as scratch:
        # Read the base objects from the approved repo and keep the applied index and new blobs disposable.
        objects = Path(scratch) / "objects"
        alternates = objects / "info" / "alternates"
        alternates.parent.mkdir(parents=True)
        repo_objects = repo.git("rev-parse", "--path-format=absolute", "--git-path", "objects").decode().removesuffix("\n")
        alternates.write_text(json.dumps(repo_objects, ensure_ascii=False) + "\n", encoding="utf-8")
        env = {"GIT_INDEX_FILE": str(Path(scratch) / "index"), "GIT_OBJECT_DIRECTORY": str(objects)}
        repo.git("read-tree", base, env_overrides=env)
        try:
            repo.git(*git_apply, "--cached", "-", input=patch, env_overrides=env)
        except RepositoryError as error:
            raise SuggestionError("patch_does_not_apply", "The diff does not apply to the approved base commit.") from error

        compare = ("diff", "--cached", "--no-renames", "--no-ext-diff", "--no-textconv", base)
        changes = repo.git(*compare, "--raw", "-z", "--", env_overrides=env).split(b"\0")[:-1]
        actual_paths = set()
        for change, path in zip(changes[::2], changes[1::2], strict=True):
            old_mode, mode, _, _, status = change.split()
            filename = path.decode("utf-8")
            if status != b"M" or old_mode[1:] != mode or filename not in allowed:
                raise SuggestionError("out_of_scope", "The applied diff changes an unselected path or file type.")
            actual_paths.add(filename)
        if actual_paths != touched:
            raise SuggestionError("invalid_patch", "Every file named in the diff must have a resulting text change.")
        return repo.git(*compare, "--patch", "--text", "--no-color", "--unified=3", "--full-index",
                        "--src-prefix=a/", "--dst-prefix=b/", "--", env_overrides=env)


def proposal(output: ModelOutput, budget: Budget) -> dict:
    if len(output.content) > budget.output_bytes:
        raise SuggestionError("output_budget_exceeded", "The proposal exceeded the configured output byte budget.")
    try:
        data = json.loads(output.content.decode("utf-8"), object_pairs_hook=distinct_object)
        if (not isinstance(data, dict) or data.keys() != {"explanation", "diff"}
                or any(not isinstance(value, str) or not value.strip() for value in data.values())):
            raise ValueError("Expected exactly one explanation and diff.")
        for value in data.values():
            value.encode("utf-8")
    except (ValueError, RecursionError) as error:
        raise SuggestionError("malformed_output", "The provider must return one JSON object with an explanation and diff.") from error
    return data


def save_metadata(out: Path, metadata: dict, *, filename: str = "suggestion.json") -> None:
    pending = out / f".{filename}.tmp"
    pending.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    pending.replace(out / filename)


def suggest(args: argparse.Namespace) -> int:
    try:
        return run_suggestion(args)
    except SuggestionError as error:
        print(f"reprostamp suggest [{error.reason}]: {error}", file=sys.stderr)
        return 2


def run_suggestion(args: argparse.Namespace) -> int:
    budget = Budget(args.max_input_bytes, args.max_output_bytes, args.max_output_tokens)
    provider: ModelProvider
    if args.response_file is not None:
        provider = DeterministicProvider(args.response_file.resolve())
    elif args.ollama_model is not None:
        provider = OllamaProvider(args.ollama_model)
    else:
        if not args.openai_model.strip():
            raise SuggestionError("invalid_provider", "Specify a model for the OpenAI provider.")
        provider = OpenAIProvider(args.openai_model)
    repo = Repository(Path(args.repo).resolve(strict=True))
    profile = load_profile(Path(args.profile).resolve(), repo.path)
    out = args.out.resolve()
    if any(out.is_relative_to(path) for path in (repo.path, profile.harness, profile.npm_cache)):
        raise SuggestionError("out_of_scope", "Keep --out outside the repository, harness, and dependency cache.")
    if out.exists():
        raise SuggestionError("request_already_exists", "Choose a new --out for each suggestion request.")

    receipt = verify_bundle(Path(args.receipt))
    evidence = baseline_evidence(receipt, repo, profile)
    base = receipt["payload"]["base_sha"]
    context = source_context(repo, repo.tree(base), profile, args.issue_file, args.file, budget.input_bytes)
    context["assertion_evidence"] = evidence
    encoded, request, approval = review_request(context, INSTRUCTIONS, budget, {
        "schema_version": 1, "provider": provider.identifier,
        "base_sha": base, "receipt_sha256": receipt["payload_sha256"], "output_directory": str(out),
        "selected_files": sorted(context["application_files"]),
    })
    if args.approve is None:
        print(json.dumps({**request, "instructions": INSTRUCTIONS, "context": context, "approval_sha256": approval}, indent=2))
        return 0
    if args.approve != approval:
        raise SuggestionError("approval_mismatch", "Review the current preview and approve its exact SHA-256.")

    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    metadata = {
        **request, "approval_sha256": approval, "requested_at": datetime.now(UTC).isoformat(),
        "status": "request_started", "usage": None,
    }
    save_metadata(out, metadata)
    output = None
    try:
        output = provider.propose(encoded, budget)
        result = proposal(output, budget)
        patch = validate_patch(repo, base, set(context["application_files"]), result["diff"])
        (out / "candidate.patch").write_bytes(patch)
        metadata.update(status="suggested", explanation=result["explanation"], patch="candidate.patch",
                        patch_sha256=hashlib.sha256(patch).hexdigest())
    except SuggestionError as error:
        if isinstance(error, ProviderError):
            output = error.output
        metadata.update(status="rejected", reason=error.reason)
        raise
    finally:
        if output is not None:
            metadata["usage"] = output_usage(output)
        save_metadata(out, metadata)
    print(f"Review {out / 'candidate.patch'} and {out / 'suggestion.json'} before applying the suggestion.")
    return 0
