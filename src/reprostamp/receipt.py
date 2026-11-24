import hashlib
import json
import stat
import zipfile
from pathlib import Path

from .integrity import hash_file, hash_json
from .receipt_schema import NUMBERS, SHA256, SIDES, integer, record, string, validate_payload


VERSION = 1
METADATA_LIMIT = 8 * 1024 * 1024
PAYLOAD_FIELDS = (
    "run_id", "replay_of", "base_sha", "head_sha", "plan", "inputs", "execution_state",
    "verdict", "reason", "detail", "engine_verdicts", "attempts",
)


def matrix(payload: dict) -> dict[tuple, dict]:
    attempts = {(a["engine"], a["side"], a["number"]): a for a in payload["attempts"]}
    cells = {}
    for engine in payload["plan"]["engines"]:
        for side in SIDES:
            for number in NUMBERS:
                attempt = attempts.get((engine, side, number), {})
                observed = {case["case_id"]: case for case in attempt.get("cases", [])}
                missing = "unsupported" if attempt.get("reason") == "required_engine_unsupported" else "missing"
                for case_id in payload["plan"]["case_ids"]:
                    case = observed.get(case_id, {"status": missing, "assertion": None, "artifacts": {}})
                    if case["status"] == "missing" and missing == "unsupported":
                        case = {**case, "status": "unsupported"}
                    cells[engine, case_id, side, number] = {**case, "attempt_reason": attempt.get("reason")}
    return cells


def browser_builds(payload: dict) -> dict[str, list[tuple[str, str]]]:
    builds = {engine: set() for engine in payload["plan"]["engines"]}
    for attempt in payload["attempts"]:
        if build := attempt["browser_build"]:
            builds[attempt["engine"]].add((build["version"], build["platform"]))
    return {engine: sorted(observed) for engine, observed in builds.items()}


def render_markdown(payload: dict) -> str:
    def plain(value: object) -> str:
        text = str(value).replace("\n", " ").replace("\r", " ")
        return "".join(f"&#{ord(char)};" if char in r"\|[]<>`*_&~$" else char for char in text)

    lines = [
        "# ReproStamp Verification Receipt", "",
        f"**{payload['verdict']}** (`{payload['reason']}`) · Execution {payload['execution_state']}", "",
        plain(payload["detail"]), "",
        f"- Run `{payload['run_id']}`",
        f"- Base `{payload['base_sha'] or 'unresolved'}`",
        f"- Candidate `{payload['head_sha'] or 'unresolved'}`",
    ]
    if payload["replay_of"]:
        lines.append(f"- Replays receipt `{payload['replay_of']}`")
    if inputs := payload["inputs"]:
        settings = inputs["settings"]
        lines += [
            f"- Runner `{inputs['runner_image']}` ({inputs['runner_platform'] or 'unavailable'})",
            f"- Seed `{settings['seed']}` · {settings['viewport_width']} × {settings['viewport_height']} · "
            f"{plain(settings['locale'])} · {plain(settings['timezone'])}",
            f"- Oracle SHA-256 `{inputs['oracle_sha256']}`",
            f"- Profile SHA-256 `{inputs['profile_sha256']}`",
        ]
    builds = browser_builds(payload)
    if builds:
        verdict_label = "Functional verdict" if payload["plan"].get("review") else "Verdict"
        lines += ["", f"| Engine | Observed builds | {verdict_label} |", "| --- | --- | --- |"]
        for engine, observed in builds.items():
            versions = ", ".join(f"{plain(version)} ({plain(platform)})" for version, platform in observed)
            verdict = payload["engine_verdicts"].get(engine)
            outcome = f"{verdict['name']} ({plain(verdict['reason'])})" if verdict else "Unavailable"
            lines.append(f"| {engine} | {versions or 'Unavailable'} | {outcome} |")
        lines += [
            "", "| Engine | Case | Base 1 | Base 2 | Candidate 1 | Candidate 2 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        cells = matrix(payload)
        for engine in builds:
            for case_id in payload["plan"]["case_ids"]:
                columns = [engine, f"`{case_id}`"]
                for side in SIDES:
                    for number in NUMBERS:
                        case = cells[engine, case_id, side, number]
                        status = case["status"]
                        if assertion := case["assertion"]:
                            status += f" ({plain(assertion['actual'])} → {plain(assertion['expected'])})"
                        if case["attempt_reason"]:
                            status += f" ({plain(case['attempt_reason'])})"
                        links = " ".join(f"[{kind}]({path})" for kind, path in case["artifacts"].items())
                        columns.append(f"{status} {links}".rstrip())
                lines.append("| " + " | ".join(columns) + " |")
    if reviews := payload.get("reviews"):
        lines += ["", "## Visual and accessibility review"]
        for review in reviews:
            visual, accessibility = review["visual"], review["accessibility"]
            lines += ["", f"### {plain(review['path'])} · {review['engine']}", ""]
            for name, check in (("Visual", visual), ("Accessibility", accessibility)):
                mode = "required" if check["required"] else "advisory"
                detail = f" · {plain(check['detail'])}" if check["detail"] else ""
                lines.append(f"- {name} ({mode}) · **{check['status']}**{detail}")
            if visual["artifacts"]:
                links = " · ".join(f"[{label}]({visual['artifacts'][side]})"
                                   for side, label in (("base", "Baseline"), ("head", "Candidate"), ("diff", "Pixel diff")))
                lines.append(f"- {visual['changed_pixels']:,} changed pixels · {links}")
            if approval := visual["applied_approval"]:
                lines.append(f"- Approved by {plain(approval['accepted_by'])} on {plain(approval['accepted_at'])} "
                             f"· source receipt `{approval['receipt_sha']}`")
            if accessibility["axe_version"] is not None:
                lines.append(f"- axe-core {accessibility['axe_version']} · {len(accessibility['findings'])} newly detected findings")
            for finding in accessibility["findings"]:
                lines.append(f"  - {plain(finding['rule'])} · {plain(finding['impact'] or 'unrated')} · {plain(finding['target'])}")
    return "\n".join([*lines, "", "See [receipt.json](receipt.json) for the integrity manifest and attempt logs.", ""])


def export_receipt(out: Path, result: dict) -> dict:
    payload = {key: result[key] for key in PAYLOAD_FIELDS}
    if "reviews" in result:
        payload["reviews"] = result["reviews"]
    payload["attempts"] = [
        {**attempt, "cases": [
            {key: value for key, value in case.items() if key != "application_location" or value is not None}
            for case in attempt["cases"]
        ]}
        for attempt in payload["attempts"]
    ]
    (out / "receipt.md").write_text(render_markdown(payload), encoding="utf-8")
    artifacts = {"receipt.md"}
    for attempt in payload["attempts"]:
        artifacts.update(attempt["logs"].values())
        for case in attempt["cases"]:
            artifacts.update(case["artifacts"].values())
    for review in payload.get("reviews", []):
        artifacts.update(review["visual"]["artifacts"].values())
    return export_bundle(out, payload, artifacts, validate_payload)


def export_bundle(out: Path, payload: dict, artifacts: set[str], validate) -> dict:
    payload["artifacts"] = {}
    staging = out / ".receipt.zip.tmp"
    try:
        with zipfile.ZipFile(staging, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(artifacts):
                digest = hashlib.sha256()
                size = 0
                with (out / path).open("rb") as source, bundle.open(path, "w", force_zip64=True) as member:
                    while chunk := source.read(1024 * 1024):
                        digest.update(chunk)
                        size += member.write(chunk)
                payload["artifacts"][path] = {"sha256": digest.hexdigest(), "size": size}
            validate(payload)
            receipt = {"schema_version": VERSION, "payload_sha256": hash_json(payload), "payload": payload}
            data = (json.dumps(receipt, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            if len(data) > METADATA_LIMIT:
                raise ValueError("The receipt exceeds the metadata size limit.")
            bundle.writestr("receipt.json", data)
        (out / "receipt.json").write_bytes(data)
        staging.replace(out / "receipt.zip")
    finally:
        staging.unlink(missing_ok=True)
    return receipt


def distinct_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"Duplicate JSON property {name!r}.")
        result[name] = value
    return result


def verify_bundle(path: Path, *, validate=validate_payload) -> dict:
    with zipfile.ZipFile(path) as bundle:
        members = {}
        for member in bundle.infolist():
            name = member.orig_filename
            mode = stat.S_IFMT(member.external_attr >> 16)
            if (name != member.filename or name in members or mode not in (0, stat.S_IFREG)
                or not name.isascii() or any(part in ("", ".", "..") for part in name.split("/"))
                or any(char in name for char in "\\:\0")):
                raise ValueError(f"Unsafe or duplicate bundle member {name!r}.")
            if member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) or member.flag_bits & 1:
                raise ValueError(f"Unsupported compression or encryption for {name!r}.")
            members[name] = member
        metadata = members.get("receipt.json")
        if metadata is None or metadata.file_size > METADATA_LIMIT:
            raise ValueError("Bundle requires a readable receipt.json within the metadata size limit.")
        receipt = json.loads(bundle.read(metadata).decode("utf-8"), object_pairs_hook=distinct_object)
        record(receipt, "schema_version payload_sha256 payload", "receipt")
        integer(receipt["schema_version"], VERSION, VERSION, "receipt schema version")
        string(receipt["payload_sha256"], "receipt SHA-256", SHA256)
        payload = receipt["payload"]
        if hash_json(payload) != receipt["payload_sha256"]:
            raise ValueError("Receipt payload SHA-256 mismatch.")
        validate(payload)
        expected = payload["artifacts"]
        if missing := expected.keys() - members.keys():
            raise ValueError(f"Missing artifact {min(missing)!r}.")
        if extra := members.keys() - expected.keys() - {"receipt.json"}:
            raise ValueError(f"Unapproved bundle member {min(extra)!r}.")
        for name, data in expected.items():
            if members[name].file_size != data["size"]:
                raise ValueError(f"Artifact size mismatch for {name!r}.")
            with bundle.open(members[name]) as file:
                if hash_file(file) != data["sha256"]:
                    raise ValueError(f"Artifact SHA-256 mismatch for {name!r}.")
        return receipt
