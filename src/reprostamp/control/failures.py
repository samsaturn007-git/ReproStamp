from collections import Counter


REPLAY_ATTEMPTS = 5


def replay_summary(attempts: list[dict], fence: int) -> dict:
    results = [row["result"] for row in attempts if row["fence"] == fence and row["result"] is not None]
    outcomes = Counter(
        result["cases"][0]["status"] if result["status"] == "completed" else "infrastructure_failure"
        for result in results
    )
    passed = outcomes["passed"]
    failed = outcomes["assertion_failed"]
    infrastructure = outcomes["infrastructure_failure"]
    classification = None
    if len(results) == REPLAY_ATTEMPTS:
        if infrastructure == REPLAY_ATTEMPTS:
            classification = "infrastructure_failure"
        elif passed and failed:
            classification = "suspected_flaky"
        elif infrastructure:
            classification = "insufficient_evidence"
        elif failed:
            classification = "consistent_failure"
        else:
            classification = "passed_on_replay"
    return {"classification": classification, "sample_size": len(results), "passed": passed,
            "assertion_failed": failed, "infrastructure_failure": infrastructure}


def observations(row: dict):
    result = row["result"]
    if result is not None:
        for case in result["cases"]:
            if case["status"] == "assertion_failed":
                assertion = case["assertion"]
                # Observed values can vary across occurrences of the same assertion.
                location = case.get("application_location")
                if location:
                    location = ":".join(location.split(":")[:2])
                yield ("application_assertion", case["case_id"], " ".join(assertion["id"].split()),
                       " ".join(assertion["expected"].split()), location, None)
            elif case["status"] != "passed":
                yield ("infrastructure_failure", case["case_id"], None, None, None,
                       result["reason"] or case["status"])
        if result["reason"] and all(case["status"] in ("passed", "assertion_failed") for case in result["cases"]):
            yield ("infrastructure_failure", None, None, None, None, result["reason"])
    elif row["reason"]:
        yield ("infrastructure_failure", None, None, None, None, row["reason"])


def group_failures(rows) -> list[dict]:
    groups = {}
    for row in rows:
        for key in observations(row):
            kind, case_id, assertion, expected, location, reason = key
            observed = row["observed"]
            group = groups.setdefault(key, {
                "kind": kind, "case_id": case_id, "assertion": assertion, "expected": expected,
                "application_location": location, "reason": reason, "first_seen": observed,
                "last_seen": observed, "browsers": set(), "receipts": {}, "count": 0,
            })
            group["first_seen"] = min(group["first_seen"], observed)
            group["last_seen"] = max(group["last_seen"], observed)
            group["count"] += 1
            receipt = group["receipts"].setdefault(row["id"], {
                "run_id": row["id"], "receipt_sha": row["receipt_sha"], "expired": row["expired"],
                "browsers": set(), "count": 0, "last_seen": observed,
            })
            receipt["count"] += 1
            receipt["last_seen"] = max(receipt["last_seen"], observed)
            if row["engine"]:
                group["browsers"].add(row["engine"])
                receipt["browsers"].add(row["engine"])
    for group in groups.values():
        group["browsers"] = sorted(group["browsers"])
        receipts = sorted(group["receipts"].values(), key=lambda item: item["last_seen"], reverse=True)
        for receipt in receipts:
            receipt["browsers"] = sorted(receipt["browsers"])
        group["receipts"] = receipts
    return sorted(groups.values(), key=lambda group: group["last_seen"], reverse=True)
