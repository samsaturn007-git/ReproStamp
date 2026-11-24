"""Run labeled failure fixtures, replay their cases, and check dashboard evidence."""

import hashlib
import http.cookiejar
import io
import json
import os
import shutil
import tempfile
import urllib.request
import uuid
import zipfile
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from prd03_exit_gate import (
    CONTROL, ROOT, available_port, call, containers, git, listening, prepare_registry, start, until,
)
from reprostamp.control.database import connect, migrate
from reprostamp.control.settings import Settings
from reprostamp.receipt import verify_bundle


FIXTURES = ROOT / "harness/prd06"
ORDINARY_CHECK = """
export function reviewOrdinaryTotal() {
  const actual = checkoutTotal(subtotal, false);
  if (actual !== subtotal) throw new Error(`Ordinary total was ${actual}`);
  return actual;
}
"""


def prepare(output):
    registry_path, repo, original = prepare_registry(output)
    registry = json.loads(registry_path.read_text())
    template = json.loads((output / "registered-profile.json").read_text())
    shutil.copyfile(ROOT / "harness/checkout/reporter.cjs", original / "reporter.cjs")
    checkout = original / "checkout.spec.cjs"

    def profile(name, harness, engines, regressions, base="checkout-base", head="checkout-fixed"):
        file = output / f"{name}-profile.json"
        file.write_text(json.dumps({**template, "harness": str(harness), "engines": engines,
                                    "required_regressions": regressions}))
        registry["profiles"][name] = {"label": name.title(), "path": str(file), "repo_id": "checkout",
                                      "base": base, "head": head}

    consistent, mixed, broken = (output / f"{name}-harness" for name in ("consistent", "mixed", "runner"))
    for harness in (consistent, mixed, broken):
        shutil.copytree(original, harness)
    (consistent / checkout.name).write_text(checkout.read_text().split("test('checkout.full-price',", 1)[0])
    shutil.copyfile(FIXTURES / "consistent.spec.cjs", consistent / "consistent.spec.cjs")
    shutil.copyfile(FIXTURES / "mixed.spec.cjs", mixed / "mixed.spec.cjs")
    shutil.copyfile(FIXTURES / "order.spec.cjs", mixed / "order.spec.cjs")
    (broken / "wait-for-app.cjs").write_text("throw new Error('PRD-06 controlled runner startup failure');\n")

    git("-C", str(repo), "switch", "--quiet", "--detach", "checkout-base")
    source = repo / "src/checkout.ts"
    source.write_text(source.read_text() + ORDINARY_CHECK)
    for tag, message in (("prd06-base", "Add an observed ordinary-price check"),
                         ("prd06-regression", "Fix promo and regress ordinary checkout")):
        if tag == "prd06-regression":
            source.write_text(source.read_text().replace("+ promoDiscount : subtotalInCents;",
                                                         "- promoDiscount : subtotalInCents + 500;"))
        git("-C", str(repo), "add", "src/checkout.ts")
        git("-C", str(repo), "-c", "user.name=ReproStamp", "-c", "user.email=fixture@example.invalid",
            "commit", "--quiet", "-m", message)
        git("-C", str(repo), "tag", tag)

    profile("consistent", consistent, ["chromium", "firefox"], ["checkout.full-price"], "prd06-base", "prd06-regression")
    profile("mixed", mixed, ["chromium"],
            ["checkout.full-price", "checkout.mixed", "checkout.primer", "checkout.order-dependent"])
    profile("runner", broken, ["chromium"], ["checkout.full-price"])
    registry_path.write_text(json.dumps(registry))
    return registry_path, registry["profiles"], repo, consistent


def exercise(stack, output, settings, api_port, registry_path, profiles, repo, consistent):
    migrate(settings)
    environment = {
        **os.environ, "REPROSTAMP_ORIGIN": settings.origin, "REPROSTAMP_API_PORT": str(api_port),
        "REPROSTAMP_DATA": str(settings.data), "REPROSTAMP_DATABASE_URL": settings.dsn,
        "REPROSTAMP_REGISTRY": str(registry_path),
    }
    origin = f"http://127.0.0.1:{api_port}"
    start(stack, output, "api", environment, [*CONTROL, "serve", "--port", str(api_port)])
    start(stack, output, "worker", environment, [*CONTROL, "worker"])
    until(lambda: listening(origin, "/api/v1/openapi.json"))
    anonymous = urllib.request.build_opener()
    owner = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    session, _ = call(owner, origin, "/session", body={"password": settings.owner_password()},
                      headers={"Origin": settings.origin})
    write = {"Origin": settings.origin, "X-CSRF-Token": session["csrf_token"]}

    def headers():
        return {**write, "Idempotency-Key": str(uuid.uuid4())}

    def detail(run_id):
        return call(owner, origin, f"/runs/{run_id}")[0]

    def completed(run_id):
        def terminal():
            row = detail(run_id)
            return row if row["finished_at"] else None
        row = until(terminal, seconds=100)
        assert not containers(uuid.UUID(run_id), row["fence"])
        return row

    def submit(profile):
        data = profiles[profile]
        row, _ = call(owner, origin, "/runs", headers=headers(), code=201,
                      body={"repo_id": "checkout", "profile_id": profile,
                            "base_ref": data["base"], "head_ref": data["head"]})
        return row["id"]

    def receipt(row, label):
        bundle, _ = call(owner, origin, f"/runs/{row['id']}/receipt")
        file = output / f"{label}.zip"
        file.write_bytes(bundle)
        assert verify_bundle(file)["payload_sha256"] == row["receipt_sha"]
        return bundle

    def replay(source, selection, key=None, code=201):
        return call(owner, origin, f"/runs/{source['id']}/case-replays", body=selection,
                    headers=key or headers(), code=code)[0]

    def check_replay(row, source, classification, *, traces):
        assert row["source_run_id"] == source["id"] and row["replay"]["receipt_sha"] == source["receipt_sha"]
        assert row["verdict"] is None and row["receipt_sha"] is None
        assert row["replay_summary"]["classification"] == classification, row["replay_summary"]
        assert row["replay_summary"]["sample_size"] == 5
        assert [attempt["number"] for attempt in row["attempts"]] == list(range(1, 6))
        for attempt in row["attempts"]:
            result = attempt["result"]
            assert attempt["engine"] == row["replay"]["engine"] and attempt["side"] == row["replay"]["side"]
            assert result["duration_ms"] > 0
            if traces:
                assert [case["case_id"] for case in result["cases"]] == [row["replay"]["case_id"]]
        artifacts = [item for item in row["artifacts"] if item["kind"] == "trace"]
        assert len(artifacts) == traces
        for artifact in artifacts:
            path = f"/runs/{row['id']}/artifacts/{artifact['id']}"
            call(anonymous, origin, path, code=401)
            trace, response = call(owner, origin, path)
            assert response.get_content_type() == "application/zip" and zipfile.is_zipfile(io.BytesIO(trace))
            assert hashlib.sha256(trace).hexdigest() == artifact["sha256"]

    first_id, second_id, broken_id, mixed_id = (submit(profile) for profile in ("consistent", "consistent", "runner", "mixed"))
    first = completed(first_id)
    assert first["verdict"] == "FAILED" and first["reason"] == "candidate_regression", first
    original = receipt(first, "consistent-receipt")
    selection = {"engine": "chromium", "side": "head", "number": 1, "case_id": "checkout.full-price"}
    replay_path = f"/runs/{first_id}/case-replays"
    call(anonymous, origin, replay_path, body=selection, headers=headers(), code=401)
    call(owner, origin, replay_path, body=selection, headers={**headers(), "X-CSRF-Token": "wrong"}, code=403)
    replay(first, {**selection, "case_id": "checkout.discount"}, code=422)
    replay(first, {**selection, "engine": "webkit"}, code=422)
    replay(first, {**selection, "commit": first["base_sha"]}, code=422)

    # Change the owner registry inputs after comparison. Replay uses its independent frozen copy.
    git("-C", str(repo), "tag", "-f", "prd06-regression", "prd06-base")
    (consistent / "consistent.spec.cjs").write_text("throw new Error('live harness changed');\n")
    key = headers()
    consistent_run = replay(first, selection, key=key)
    assert replay(first, selection, key=key, code=200)["id"] == consistent_run["id"]
    replay(first, {**selection, "number": 2}, key=key, code=409)

    second = completed(second_id)
    assert second["verdict"] == "FAILED"
    receipt(second, "second-regression-receipt")
    broken = completed(broken_id)
    assert broken["verdict"] == "INCONCLUSIVE" and broken["reason"] == "runner_startup_failed", broken
    receipt(broken, "runner-receipt")
    runner_run = replay(broken, {**selection, "case_id": "checkout.discount"})

    mixed = completed(mixed_id)
    for sample in range(4):
        failure = next((attempt for attempt in mixed["attempts"] if any(
            case["case_id"] == "checkout.mixed" and case["status"] == "assertion_failed"
            for case in attempt["result"]["cases"]
        )), None)
        if failure:
            break
        if sample < 3:
            mixed = completed(submit("mixed"))
    assert failure, "The intermittent fixture did not produce a source failure."
    mixed_original = receipt(mixed, "mixed-receipt")
    mixed_selection = {**selection, "case_id": "checkout.mixed", "side": failure["side"], "number": failure["number"]}
    for _ in range(4):
        mixed_run = completed(replay(mixed, mixed_selection)["id"])
        if mixed_run["replay_summary"]["classification"] == "suspected_flaky":
            break
    check_replay(mixed_run, mixed, "suspected_flaky", traces=5)
    assert mixed_run["replay_summary"]["passed"] > 0 and mixed_run["replay_summary"]["assertion_failed"] > 0
    order_selection = {**selection, "case_id": "checkout.order-dependent"}
    original_attempt = next(attempt for attempt in mixed["attempts"]
                            if attempt["side"] == "head" and attempt["number"] == 1)
    assert any(case["case_id"] == order_selection["case_id"] and case["status"] == "assertion_failed"
               for case in original_attempt["result"]["cases"])
    recovered = completed(replay(mixed, order_selection)["id"])
    check_replay(recovered, mixed, "passed_on_replay", traces=5)
    assert recovered["replay_summary"]["passed"] == 5
    mixed_after = detail(mixed["id"])
    assert mixed_after["attempts"] == mixed["attempts"] and mixed_after["verdict"] == mixed["verdict"]
    assert any(link["id"] == mixed_run["id"] for link in mixed_after["case_replays"])
    assert call(owner, origin, f"/runs/{mixed['id']}/receipt")[0] == mixed_original

    repeat = completed(consistent_run["id"])
    check_replay(repeat, first, "consistent_failure", traces=5)
    assert repeat["replay"]["commit"] == first["head_sha"] != git("-C", str(repo), "rev-parse", "prd06-regression")
    assert repeat["replay_summary"]["assertion_failed"] == 5
    assert call(owner, origin, f"/runs/{first_id}/receipt")[0] == original
    runner = completed(runner_run["id"])
    check_replay(runner, broken, "infrastructure_failure", traces=0)
    assert all(attempt["result"]["reason"] == "runner_startup_failed" for attempt in runner["attempts"])

    failures = "/repositories/checkout/failures"
    call(anonymous, origin, failures, code=401)
    groups, _ = call(owner, origin, failures)
    regression = next(group for group in groups if group["assertion"] == "ordinary_total")
    assert regression["kind"] == "application_assertion" and regression["case_id"] == "checkout.full-price"
    assert regression["application_location"].startswith("src/checkout.ts:"), regression
    assert regression["first_seen"] < regression["last_seen"]
    assert regression["browsers"] == ["chromium", "firefox"] and regression["count"] == 8
    assert {entry["run_id"] for entry in regression["receipts"]} == {first_id, second_id}
    assert any(group["kind"] == "infrastructure_failure" and group["reason"] == "runner_startup_failed"
               and [item["run_id"] for item in group["receipts"]] == [broken_id] for group in groups)
    (output / "failure-groups.json").write_text(json.dumps(groups, indent=2) + "\n")
    results = {
        label: {"run_id": row["id"], "source_run_id": row["source_run_id"], **row["replay_summary"]}
        for label, row in [("consistent regression", repeat), ("mixed assertion", mixed_run), ("runner failure", runner),
                           ("order-dependent assertion", recovered)]
    }
    (output / "classifications.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2), flush=True)
    print("PASS source receipt integrity, idempotency, owner authorization, isolated fresh attempts, and grouped history", flush=True)

    dashboard_port = settings.origin.rsplit(":", 1)[1]
    start(stack, output, "dashboard", environment, ["npm", "--prefix", "dashboard", "run", "dev", "--", "--port", dashboard_port])
    until(lambda: listening(settings.origin, "/"), seconds=60)
    browser = start(stack, output, "browser", environment, [
        "node", "tests/prd06_browser.cjs", settings.origin, str(output), str(settings.data / "owner-password"),
        first_id, mixed_run["id"],
    ])
    assert browser.wait(timeout=100) == 0, (output / "browser.log").read_text()
    print((output / "browser.log").read_text(), end="", flush=True)

    with connect(settings) as db:
        db.execute("UPDATE runs SET expires_at = clock_timestamp() - interval '1 second' WHERE id = %s", (first_id,))
    replay(first, selection, code=422)
    assert detail(repeat["id"])["replay"]["receipt_sha"] == first["receipt_sha"]
    assert next(group for group in call(owner, origin, failures)[0] if group["assertion"] == "ordinary_total")["count"] == 8
    print("PASS source expiry blocks new replays and preserves linked analysis", flush=True)


def main():
    local = Settings.local()
    output = Path(tempfile.mkdtemp(prefix="prd06-gates-", dir=ROOT / ".reprostamp"))
    print(f"Evidence directory: {output}", flush=True)
    registry, profiles, repo, harness = prepare(output)
    database = f"reprostamp_case_gate_{uuid.uuid4().hex}"
    api_port, dashboard_port = available_port(), available_port()
    while api_port == dashboard_port:
        dashboard_port = available_port()
    settings = replace(local, data=output / "data", dsn=make_conninfo(local.dsn, dbname=database),
                       origin=f"http://127.0.0.1:{dashboard_port}")
    with psycopg.connect(local.dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        try:
            with ExitStack() as stack:
                exercise(stack, output, settings, api_port, registry, profiles, repo, harness)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
    print(f"PRD-06 exit gates passed. Evidence: {output}", flush=True)


if __name__ == "__main__":
    main()
