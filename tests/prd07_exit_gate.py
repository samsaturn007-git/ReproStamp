"""Exercise screenshot, axe, approval, and receipt behavior through the local pilot."""

import hashlib
import http.cookiejar
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import uuid
import zipfile
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

import psycopg
from PIL import Image
from psycopg import sql
from psycopg.conninfo import make_conninfo

from prd03_exit_gate import CONTROL, ROOT, available_port, call, containers, git, listening, start, until
from reprostamp.control.database import connect, migrate
from reprostamp.control.settings import Settings
from reprostamp.integrity import hash_json
from reprostamp.receipt import verify_bundle


LEGACY_ICON = ('<img id="legacy-icon" width="10" height="10" '
               'src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" />')


def commit(repo, tag):
    git("-C", str(repo), "add", "src")
    git("-C", str(repo), "-c", "user.name=ReproStamp", "-c", "user.email=fixture@example.invalid",
        "commit", "--quiet", "-m", tag)
    git("-C", str(repo), "tag", tag)


def prepare(output):
    profile = ROOT / "profiles/checkout-review.json"
    template = json.loads(profile.read_text())
    repo, harness = output / "registered-repo", output / "registered-harness"
    git("clone", "--quiet", "--no-local", str((profile.parent / template["repository"]).resolve()), str(repo))
    shutil.copytree((profile.parent / template["harness"]).resolve(strict=True), harness)
    shutil.copyfile(ROOT / "harness/prd07/keyboard.spec.cjs", harness / "keyboard.spec.cjs")
    template.update(repository=str(repo), harness=str(harness), engines=["chromium"],
                    npm_cache=str((profile.parent / template["npm_cache"]).resolve()),
                    required_regressions=[*template["required_regressions"], "checkout.keyboard"])

    git("-C", str(repo), "switch", "--quiet", "--detach", "checkout-base")
    main = repo / "src/main.tsx"
    main.write_text(main.read_text().replace("<main>", '<main data-review={location.pathname === "/review" ? "preview" : undefined}>')
                    .replace("<h1>Checkout</h1>", '<h1>Checkout</h1>\n      {location.pathname === "/review" && ' + LEGACY_ICON + '}'))
    commit(repo, "prd07-base")
    git("-C", str(repo), "apply", str(ROOT / "fixtures/checkout/fix.patch"))
    styles = repo / "src/style.css"
    styles.write_text(styles.read_text() + '\nmain[data-review="preview"] { transform: translateX(48px); }\n')
    commit(repo, "prd07-intentional")
    main.write_text(main.read_text().replace('htmlFor="promo"', 'htmlFor={location.pathname === "/review" ? undefined : "promo"}'))
    commit(repo, "prd07-accessibility")
    git("-C", str(repo), "switch", "--quiet", "--detach", "prd07-intentional")
    styles.write_text(styles.read_text().replace("translateX(48px)", "translateX(96px)"))
    commit(repo, "prd07-later")

    profiles = {}
    for label, required, ready in (
        ("advisory", {}, "main h1"), ("visual", {"visual_required": True}, "main h1"),
        ("accessibility", {"accessibility_required": True}, "main h1"),
        ("advisory-missing", {}, "#missing-content"),
        ("required-missing", {"visual_required": True}, "#missing-content"),
    ):
        path = output / f"{label}.json"
        routes = [*template["review"]["routes"], {"id": "preview", "path": "/review", "ready": ready, **required}]
        path.write_text(json.dumps({**template, "review": {"engine": "chromium", "routes": routes}}))
        profiles[label] = {"label": label, "path": str(path), "repo_id": "checkout", "base": "prd07-base",
                           "head": "prd07-intentional"}
    registry = output / "registry.json"
    registry.write_text(json.dumps({"profiles": profiles, "repositories": {"checkout": {"label": "Checkout review", "path": str(repo)}}}))
    return registry, repo


def inspect_pixels(output, row, bundle, review):
    with zipfile.ZipFile(bundle) as archive:
        for role, path in review["visual"]["artifacts"].items():
            data = archive.read(path)
            artifact = next(item for item in row["artifacts"] if item["path"] == path)
            assert artifact["sha256"] == hashlib.sha256(data).hexdigest()
            with Image.open(io.BytesIO(data)) as image:
                assert image.size == (1100, 800)
                if role == "diff":
                    colors = image.getcolors(image.width * image.height)
                    assert colors is not None
                    assert {color: count for count, color in colors}[(214, 34, 86)] == review["visual"]["changed_pixels"]
            (output / f"seeded-{role}.png").write_bytes(data)


def check_tampering(source, output):
    target = output / "tampered-review.zip"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w") as modified:
        manifest = json.loads(original.read("receipt.json"))
        visual = manifest["payload"]["reviews"][1]["visual"]
        visual["binding"]["screenshot_sha256"] = "0" * 64
        manifest["payload_sha256"] = hash_json(manifest["payload"])
        for item in original.namelist():
            modified.writestr(item, json.dumps(manifest) if item == "receipt.json" else original.read(item))
    try:
        verify_bundle(target)
    except ValueError as error:
        assert "binding" in str(error), error
    else:
        raise AssertionError("Receipt accepted a replacement screenshot binding.")


def exercise(stack, output, settings, port, registry_path, repo):
    migrate(settings)
    origin = f"http://127.0.0.1:{port}"
    environment = {**os.environ, "REPROSTAMP_ORIGIN": settings.origin, "REPROSTAMP_API_PORT": str(port),
                   "REPROSTAMP_DATA": str(settings.data), "REPROSTAMP_DATABASE_URL": settings.dsn,
                   "REPROSTAMP_REGISTRY": str(registry_path)}
    start(stack, output, "api", environment, [*CONTROL, "serve", "--port", str(port)])
    start(stack, output, "worker", environment, [*CONTROL, "worker"])
    dashboard_port = settings.origin.rsplit(":", 1)[1]
    start(stack, output, "dashboard", environment, ["npm", "--prefix", "dashboard", "run", "dev", "--", "--port", dashboard_port])
    until(lambda: listening(origin, "/api/v1/openapi.json"))
    until(lambda: listening(settings.origin, "/"), seconds=60)
    anonymous = urllib.request.build_opener()
    owner = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    session = call(owner, origin, "/session", body={"password": settings.owner_password()}, headers={"Origin": settings.origin})[0]
    headers = {"Origin": settings.origin, "X-CSRF-Token": session["csrf_token"]}

    def submit(profile, head):
        return call(owner, origin, "/runs", body={"repo_id": "checkout", "profile_id": profile,
                    "base_ref": "prd07-base", "head_ref": f"prd07-{head}"},
                    headers={**headers, "Idempotency-Key": str(uuid.uuid4())}, code=201)[0]["id"]

    def detail(run):
        return call(owner, origin, f"/runs/{run}")[0]

    def finish(run, verdict, reason, label):
        def terminal():
            row = detail(run)
            return row if row["finished_at"] else None
        row = until(terminal, seconds=180)
        assert (row["state"], row["verdict"], row["reason"]) == ("completed", verdict, reason), row
        assert row["engine_verdicts"]["chromium"]["name"] == "VERIFIED"
        assert all(any(case["case_id"] == "checkout.keyboard" and case["status"] == "passed"
                       for case in attempt["result"]["cases"]) for attempt in row["attempts"])
        assert not containers(uuid.UUID(run), row["fence"])
        bundle = output / f"{label}.zip"
        bundle.write_bytes(call(owner, origin, f"/runs/{run}/receipt")[0])
        receipt = verify_bundle(bundle)
        assert row["receipt_sha"] == receipt["payload_sha256"]
        review = row["reviews"][1]
        assert row["reviews"][0]["visual"]["status"] == "unchanged"
        print(f"PASS {label}: {verdict} [{reason}], visual {review['visual']['status']}, axe {review['accessibility']['status']}", flush=True)
        return row, bundle, review

    def browser(action, run):
        process = start(stack, output, action, environment, ["node", "tests/prd07_browser.cjs", settings.origin,
                        str(output), str(settings.data / "owner-password"), action, run])
        assert process.wait(timeout=85) == 0, (output / f"{action}.log").read_text()
        print((output / f"{action}.log").read_text(), end="", flush=True)

    intentional_id = submit("visual", "intentional")
    advisory_id = submit("advisory", "accessibility")
    required_axe_id = submit("accessibility", "accessibility")
    row, original, intentional = finish(intentional_id, "FAILED", "required_visual_change", "intentional")
    assert intentional["accessibility"]["status"] == "passed"
    binding = intentional["visual"]["binding"]
    assert binding["profile_sha256"] == intentional["profile_sha256"]
    assert binding["commit"] == row["head_sha"] and binding["browser_build"] == intentional["browser_build"]
    approve_path = f"/runs/{intentional_id}/visual-reviews/preview/approval"
    body = {"receipt_sha": row["receipt_sha"], "screenshot_sha256": binding["screenshot_sha256"]}
    call(anonymous, origin, approve_path, body=body, headers=headers, code=401)
    call(owner, origin, approve_path, body=body, headers={**headers, "X-CSRF-Token": "wrong"}, code=403)
    call(owner, origin, approve_path, body={**body, "receipt_sha": "0" * 64}, headers=headers, code=409)
    call(owner, origin, approve_path, body={**body, "screenshot_sha256": "0" * 64}, headers=headers, code=409)
    candidate = next(item for item in row["artifacts"] if item["path"] == intentional["visual"]["artifacts"]["head"])
    path = f"/runs/{intentional_id}/artifacts/{candidate['id']}"
    call(anonymous, origin, path, code=401)
    data, response = call(owner, origin, path)
    assert response.get_content_type() == "image/png" and hashlib.sha256(data).hexdigest() == binding["screenshot_sha256"]
    browser("approve", intentional_id)
    approval = call(owner, origin, approve_path, body=body, headers=headers)[0]
    assert approval["accepted_by"] == "owner" and approval["binding"] == binding
    assert detail(intentional_id)["visual_approvals"] == [approval]
    assert call(owner, origin, f"/runs/{intentional_id}/receipt")[0] == original.read_bytes()

    approved_id = submit("visual", "intentional")
    later_id = submit("visual", "later")
    same_pixels_id = submit("visual", "accessibility")
    missing_id = submit("advisory-missing", "intentional")
    required_missing_id = submit("required-missing", "intentional")
    advisory, bundle, regression = finish(advisory_id, "VERIFIED", "expected_fix_confirmed", "advisory")
    assert regression["visual"]["changed_pixels"] > 0 and regression["visual"]["status"] == "changed"
    assert not regression["visual"]["required"] and not regression["accessibility"]["required"]
    assert regression["accessibility"]["findings"] == [{"rule": "label", "impact": "critical", "target": "#promo"}]
    inspect_pixels(output, advisory, bundle, regression)
    check_tampering(bundle, output)
    browser("regression", advisory_id)
    _, _, required_axe = finish(required_axe_id, "FAILED", "required_accessibility_regression", "required-axe")
    assert required_axe["accessibility"]["required"] and required_axe["accessibility"]["findings"] == regression["accessibility"]["findings"]
    _, approved_bundle, approved = finish(approved_id, "VERIFIED", "expected_fix_confirmed", "approved")
    assert approved["visual"]["applied_approval"] == approval
    assert verify_bundle(approved_bundle)["payload"]["reviews"][1]["visual"]["applied_approval"]["binding"] == binding
    _, _, later = finish(later_id, "FAILED", "required_visual_change", "later")
    assert later["visual"]["binding"]["screenshot_sha256"] != binding["screenshot_sha256"]
    assert later["visual"]["applied_approval"] is None and detail(later_id)["visual_approvals"] == [approval]
    call(owner, origin, f"/runs/{later_id}/visual-reviews/preview/approval",
         body={**body, "receipt_sha": detail(later_id)["receipt_sha"]}, headers=headers, code=409)
    browser("later", later_id)
    _, _, same = finish(same_pixels_id, "FAILED", "required_visual_change", "same-pixels-new-commit")
    assert same["visual"]["binding"]["screenshot_sha256"] == binding["screenshot_sha256"]
    assert same["visual"]["binding"]["commit"] != binding["commit"] and same["visual"]["applied_approval"] is None
    _, _, missing = finish(missing_id, "VERIFIED", "expected_fix_confirmed", "missing-advisory")
    assert missing["visual"]["status"] == missing["accessibility"]["status"] == "unavailable"
    _, _, required_missing = finish(required_missing_id, "INCONCLUSIVE", "required_visual_unavailable", "missing-required")
    assert required_missing["visual"]["status"] == "unavailable" and required_missing["visual"]["required"]

    replay = output / "offline-replay"
    with (output / "offline-replay.log").open("wb") as log:
        subprocess.run([sys.executable, "-m", "reprostamp.cli", "replay", str(approved_bundle), "--repo", str(repo),
                        "--profile", str(output / "visual.json"), "--out", str(replay)], stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=120)
    replayed = verify_bundle(replay / "receipt.zip")["payload"]
    assert replayed["verdict"] == "VERIFIED" and replayed["reviews"][1]["visual"]["binding"] == binding
    assert replayed["replay_of"] == verify_bundle(approved_bundle)["payload_sha256"]
    with connect(settings) as db:
        db.execute("UPDATE runs SET expires_at = clock_timestamp() - interval '1 second' WHERE id = %s", (intentional_id,))
    call(owner, origin, approve_path, body=body, headers=headers, code=410)
    assert detail(later_id)["visual_approvals"] == [approval]
    print("PASS exact binding, authenticated image downloads, idempotent approval, retained history, and offline replay", flush=True)


def main():
    local = Settings.local()
    output = Path(tempfile.mkdtemp(prefix="prd07-gates-", dir=ROOT / ".reprostamp"))
    print(f"Evidence directory: {output}", flush=True)
    registry, repo = prepare(output)
    database = f"reprostamp_gate_{uuid.uuid4().hex}"
    port, dashboard = available_port(), available_port()
    while port == dashboard:
        dashboard = available_port()
    settings = replace(local, data=output / "data", dsn=make_conninfo(local.dsn, dbname=database),
                       origin=f"http://127.0.0.1:{dashboard}")
    with psycopg.connect(local.dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        try:
            with ExitStack() as stack:
                exercise(stack, output, settings, port, registry, repo)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
    print(f"PRD-07 exit gates passed. Evidence: {output}", flush=True)


if __name__ == "__main__":
    main()
