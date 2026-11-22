from dataclasses import dataclass

from .profile import Profile
from .runner import Attempt


@dataclass(frozen=True)
class Verdict:
    name: str
    reason: str
    detail: str


EXIT_CODES = {"VERIFIED": 0, "FAILED": 1, "INCONCLUSIVE": 3, "POLICY_BLOCKED": 4}


def classify_engine(profile: Profile, engine: str, attempts: list[Attempt], platform: str | None) -> Verdict:
    if {(attempt.side, attempt.number) for attempt in attempts} != {
        (side, number) for side in ("base", "head") for number in (1, 2)
    }:
        return Verdict("INCONCLUSIVE", "required_cell_missing", f"Required {engine} attempts are missing.")
    for attempt in attempts:
        if attempt.reason:
            return Verdict(
                "INCONCLUSIVE", attempt.reason,
                f"{engine} {attempt.side} attempt {attempt.number}: {attempt.detail}",
            )
    builds = {attempt.browser_build for attempt in attempts}
    if None in builds:
        return Verdict("INCONCLUSIVE", "browser_build_missing", f"Required {engine} build evidence is missing.")
    if len(builds) != 1 or any(build.platform != platform for build in builds):
        return Verdict("INCONCLUSIVE", "browser_build_changed", f"The {engine} build or runner platform changed.")

    results = {
        (attempt.side, attempt.number): {case.case_id: case for case in attempt.cases}
        for attempt in attempts
    }
    if any(cases.keys() != profile.case_ids for cases in results.values()):
        return Verdict("INCONCLUSIVE", "required_cell_missing", f"Required {engine} cases are missing.")
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


def classify(profile: Profile, attempts: list[Attempt], platform: str | None) -> tuple[Verdict, dict[str, Verdict]]:
    engine_verdicts = {
        engine: classify_engine(profile, engine, [item for item in attempts if item.engine == engine], platform)
        for engine in profile.engines
    }
    for name in ("INCONCLUSIVE", "FAILED"):
        for engine, verdict in engine_verdicts.items():
            if verdict.name == name:
                return Verdict(name, verdict.reason, f"[{engine}] {verdict.detail}"), engine_verdicts
    return Verdict(
        "VERIFIED", "expected_fix_confirmed",
        "On every required engine, the expected assertion failed twice on the base, then passed twice on the candidate alongside all required regressions.",
    ), engine_verdicts
