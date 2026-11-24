from pathlib import Path

from psycopg.types.json import Jsonb

from ..integrity import hash_file, hash_json


APPROVAL_FIELDS = "binding, run_id, receipt_sha, accepted_by, accepted_at"


class ApprovalConflict(ValueError):
    pass


class ApprovalExpired(ValueError):
    pass


def approvals_for_commit(db, repo_id: str, commit: str) -> list[dict]:
    rows = db.execute(f"""
        SELECT {APPROVAL_FIELDS} FROM visual_approvals WHERE repo_id = %s AND binding->>'commit' = %s
    """, (repo_id, commit)).fetchall()
    return [{**row, "run_id": str(row["run_id"]), "accepted_at": row["accepted_at"].isoformat()} for row in rows]


def approval_history(db, row: dict) -> list[dict]:
    if not row["reviews"]:
        return []
    return db.execute(f"""
        SELECT {APPROVAL_FIELDS} FROM visual_approvals
        WHERE repo_id = %s AND binding->>'profile_sha256' = %s
        ORDER BY accepted_at DESC
    """, (row["request"]["repo_id"], row["reviews"][0]["profile_sha256"])).fetchall()


def approve(db, run: dict, route_id: str, receipt_sha: str, screenshot_sha: str, root: Path) -> tuple[dict, bool]:
    if run["expired"]:
        raise ApprovalExpired("The evidence retention period has ended.")
    if not run["receipt_sha"] or run["receipt_sha"] != receipt_sha:
        raise ApprovalConflict("This receipt changed. Reload the comparison before approving.")
    review = next((item for item in run["reviews"] if item["route_id"] == route_id), None)
    if review is None:
        raise LookupError("Route review not found.")
    visual = review["visual"]
    binding = visual["binding"]
    if binding is None or binding["screenshot_sha256"] != screenshot_sha:
        raise ApprovalConflict("Choose the displayed candidate screenshot before approving.")
    screenshot = (root / visual["artifacts"]["head"]).resolve()
    if not screenshot.is_relative_to(root.resolve()) or not screenshot.is_file():
        raise ApprovalConflict("The candidate screenshot is unavailable.")
    with screenshot.open("rb") as content:
        if hash_file(content) != screenshot_sha:
            raise ApprovalConflict("The candidate screenshot has changed since the receipt was created.")
    repo_id = run["request"]["repo_id"]
    digest = hash_json(binding)
    approval = db.execute(f"""
        INSERT INTO visual_approvals (repo_id, binding_sha, binding, run_id, receipt_sha, accepted_by)
        VALUES (%s, %s, %s, %s, %s, 'owner') ON CONFLICT DO NOTHING RETURNING {APPROVAL_FIELDS}
    """, (repo_id, digest, Jsonb(binding), run["id"], receipt_sha)).fetchone()
    if approval is not None:
        return approval, True
    return db.execute(f"""
        SELECT {APPROVAL_FIELDS} FROM visual_approvals WHERE repo_id = %s AND binding_sha = %s
    """, (repo_id, digest)).fetchone(), False
