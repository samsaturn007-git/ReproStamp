from dataclasses import dataclass

from .profile import Profile
from .runner import Attempt


@dataclass(frozen=True)
class Verdict:
    name: str
    reason: str
    detail: str


EXIT_CODES = {"VERIFIED": 0, "FAILED": 1, "INCONCLUSIVE": 3, "POLICY_BLOCKED": 4}


def classify(profile: Profile, attempts: list[Attempt]) -> Verdict:
    for attempt in attempts:
        if attempt.reason:
            return Verdict(
                "INCONCLUSIVE", attempt.reason,
                f"{attempt.side} attempt {attempt.number}: {attempt.detail}",
            )

    results = {
        (attempt.side, attempt.number): {case.case_id: case for case in attempt.cases}
        for attempt in attempts
    }
    for side in ("base", "head"):
        for case_id in sorted(profile.case_ids):
            first, second = results[side, 1][case_id], results[side, 2][case_id]
            if (first.status, first.assertion) != (second.status, second.assertion):
                return Verdict("INCONCLUSIVE", "mixed_outcomes", f"{case_id} changed outcome between {side} attempts.")

    expected = profile.expected_failure
    observed = results["base", 1][expected.case_id].assertion
    if observed is None or (observed.id, observed.actual) != (expected.assertion_id, expected.baseline_actual):
        return Verdict(
            "INCONCLUSIVE", "baseline_not_reproduced",
            f"The base did not reproduce {expected.case_id}/{expected.assertion_id} with {expected.baseline_actual!r}.",
        )

    for case_id in profile.required_regressions:
        if results["base", 1][case_id].status != "passed":
            return Verdict("INCONCLUSIVE", "baseline_regression_failing", f"{case_id} failed on the base.")
    for case_id in profile.required_regressions:
        if results["head", 1][case_id].status != "passed":
            return Verdict("FAILED", "candidate_regression", f"{case_id} failed on both candidate attempts.")
    if results["head", 1][expected.case_id].status != "passed":
        return Verdict("FAILED", "candidate_assertion_failed", f"{expected.case_id} failed on both candidate attempts.")

    return Verdict(
        "VERIFIED", "expected_fix_confirmed",
        "The expected assertion failed twice on the base, then passed twice on the candidate alongside all required regressions.",
    )
