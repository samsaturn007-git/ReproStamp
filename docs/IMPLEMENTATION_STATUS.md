# ReproStamp implementation status

## Pre-PRD setup

Complete on 22 November 2026. The local `main` branch contains the setup tools, active product plan, all eight numbered PRDs, and the original reference pack. [Start PRD-01](prds/PRD-01-verification-cli.md).

| Command | Observed result |
| --- | --- |
| `./scripts/setup.sh` | Created `.venv` with Python 3.14.5 and pip 26.1.1. Detected Git 2.54.0, Node.js 26.13.1, npm 11.20.0, and Docker Engine 29.8.2. Installed the locked Playwright 1.65.1 dependencies and passed 1 Chromium smoke test. |
| `/Users/samueldsouza/Desktop/DEVPROJ/scripts/setup.sh` from the parent directory | Reused `.venv` and the cached image, reinstalled the locked smoke dependencies, and passed 1 Chromium smoke test. |
| `docker buildx imagetools inspect mcr.microsoft.com/playwright:v1.65.1-noble` | Confirmed that the digest pinned in [`image.txt`](../tools/runner-smoke/image.txt) is the OCI index with Linux ARM64 and AMD64 images. |
| `shasum -a 256 -c CONTENTS_SHA256.txt` from [`docs/reference/original_prd_pack`](reference/original_prd_pack/README.md) | All 10 files matched the archived checksums after moving the pack. The standalone master PRD also matched byte for byte during initial setup, and the combined PRD contained all 10 documents. |

Both smoke runs used Chromium `159.0.8154.6` on Linux ARM64 in the local OrbStack Docker context. The test checked that the process ran as a non-root user, the network interfaces were loopback-only, and Chromium could load the local test page. [Playwright Docker documentation](https://playwright.dev/docs/docker) · [Docker none network driver](https://docs.docker.com/engine/network/drivers/none/)

## PRD-01

Complete on 22 November 2026 and rechecked after the ReproStamp rename on 23 November 2026. The Python CLI, owned checkout fixture, independent Playwright harness, and Docker runner passed the exit gate in Chromium `159.0.8154.6` on Linux ARM64. [PRD-01 requirements](prds/PRD-01-verification-cli.md)

| Command | Observed result |
| --- | --- |
| `./scripts/setup.sh` from a clean project copy | Created a fresh venv, installed the CLI, and passed the Chromium smoke test. |
| `.venv/bin/python scripts/prepare-checkout.py` | Created the registered repo and prewarmed its npm cache in the pinned Linux image. A repeat run returned the same two SHAs. |
| `.venv/bin/reprostamp compare --repo .reprostamp/checkout/repo --base checkout-base --head checkout-fixed --profile profiles/checkout.json --out .reprostamp/prd01-renamed` | `VERIFIED`, exit `0`. The base charged `$110.00` instead of `$90.00` twice, the candidate passed the discount test twice, and the ordinary checkout test passed in all four attempts. |
| `npm run typecheck` and `npm run build` in the pinned image with offline dependencies | TypeScript passed and Vite produced the production bundle. |
| `docker inspect` on a live app/harness pair | Confirmed separate read-only roots, non-root users, a loopback-only app network shared by the harness, and a writable evidence bind mounted in the harness alone. |
| `.venv/bin/python tests/prd01_exit_gate.py` | All 10 scenarios matched their expected verdict, exit code, and reason. Verified failure trace ZIPs and PNG screenshots. The known-good run ignored uncommitted files in the app checkout. |

The regenerated fixture tags resolve to `d3e8d0413daf4064085e7713206c3fa937d95b15` (`checkout-base`) and `51a49a82f83c56b84547a01ba80d883abb5f0943` (`checkout-fixed`). The retained demonstration is in `.reprostamp/prd01-renamed/` and the exit-gate results are in `.reprostamp/prd01-gates-osv8sys0/`. Earlier evidence is preserved in its original local output directory.

| Scenario | Verdict | Exit | Reason |
| --- | --- | --- | --- |
| Known-good fix | `VERIFIED` | `0` | `expected_fix_confirmed` |
| Ineffective edit | `FAILED` | `1` | `candidate_assertion_failed` |
| New ordinary-checkout regression | `FAILED` | `1` | `candidate_regression` |
| Baseline already passes | `INCONCLUSIVE` | `3` | `baseline_not_reproduced` |
| Missing runner image | `INCONCLUSIVE` | `3` | `runner_startup_failed` |
| Timeout | `INCONCLUSIVE` | `3` | `attempt_timeout` |
| Dependency lock edit | `POLICY_BLOCKED` | `4` | `disallowed_change` |
| Protected test edit | `POLICY_BLOCKED` | `4` | `disallowed_change` |
| Tracked symlink | `POLICY_BLOCKED` | `4` | `unsupported_repository_entry` |
| Tracked submodule entry | `POLICY_BLOCKED` | `4` | `unsupported_repository_entry` |

The four timeout attempts reached app readiness and then hit the 8-second deadline. Docker reported no remaining attempt containers and the host had no remaining comparison workspace. All policy-blocked runs recorded zero attempts.

No PRD-01 exit checks remain open. [PRD-02](prds/PRD-02-receipt-and-replay.md) is ready to start.

## PRD-02 readiness

Setup verified on 22–23 November 2026. PRD-01 is checkpointed locally at `bd538dd`. [PRD-02 requirements](prds/PRD-02-receipt-and-replay.md)

| Command | Observed result |
| --- | --- |
| `.venv/bin/python tests/prd01_exit_gate.py` | All 10 scenarios passed on repeat with the renamed CLI, including cleanup after four timed-out workloads. |
| `./scripts/setup.sh --all-browsers` | All three engines loaded a loopback page as a non-root user in the pinned Linux ARM64 image. The observed versions were Chromium `159.0.8154.6`, Firefox `159.0`, and WebKit `27.2`. Firefox launched after the smoke container used a writable temporary home, matching the comparison runner. |
| `.venv/bin/python scripts/prepare-checkout.py` | Confirmed the existing checkout SHAs and refreshed its npm cache. |
| `.venv/bin/python scripts/prepare_fixture.py shipping` | Prepared the second owned Git repo and its isolated harness and npm cache. The current `shipping-base` is `bda72ba90371027698de5c60c8f0818c1451e02f` and `shipping-fixed` is `07dd85e3a1c7cca7fd7691dac20212dced8a0bb1`. |
| `.venv/bin/reprostamp compare --repo .reprostamp/shipping/repo --base shipping-base --head shipping-fixed --profile profiles/shipping.json --out .reprostamp/prd02-shipping-renamed` | `VERIFIED`, exit `0`. Shipping at `$50.00` failed twice on the base and passed twice on the candidate. The `$49.99` regression passed four times. |

Both fixtures were also provisioned and compared successfully from a fresh project copy with a new venv and empty fixture caches. No comparison containers remained after the checks.

The shipping comparison is a Chromium onboarding check. The PRD-02 exit gate requires the three-engine comparison, receipt export and integrity checks, replay, and a run on both fixtures. There are no open prerequisites to start that work. [Receipt canonicalization standard](https://www.rfc-editor.org/rfc/rfc8785)
