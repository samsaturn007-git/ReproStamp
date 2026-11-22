# BuildVerify AI implementation status

## Pre-PRD setup

Complete on 22 November 2026. The local `main` branch contains the setup tools, active product plan, all eight numbered PRDs, and the original reference pack. [Start PRD-01](prds/PRD-01-verification-cli.md).

| Command | Observed result |
| --- | --- |
| `./scripts/setup.sh` | Created `.venv` with Python 3.14.5 and pip 26.1.1. Detected Git 2.54.0, Node.js 26.13.1, npm 11.20.0, and Docker Engine 29.8.2. Installed the locked Playwright 1.65.1 dependencies and passed 1 Chromium smoke test. |
| `/Users/samueldsouza/Desktop/DEVPROJ/scripts/setup.sh` from the parent directory | Reused `.venv` and the cached image, reinstalled the locked smoke dependencies, and passed 1 Chromium smoke test. |
| `docker buildx imagetools inspect mcr.microsoft.com/playwright:v1.65.1-noble` | Confirmed that the digest pinned in [`image.txt`](../tools/runner-smoke/image.txt) is the OCI index with Linux ARM64 and AMD64 images. |
| `shasum -a 256 -c CONTENTS_SHA256.txt` from [`docs/reference/buildverify_prd_pack`](reference/buildverify_prd_pack/README.md) | All 10 files matched the archived checksums. The standalone master PRD also matched byte for byte, and the combined PRD contained all 10 documents. |

Both smoke runs used Chromium `159.0.8154.6` on Linux ARM64 in the local OrbStack Docker context. The test checked that the process ran as a non-root user, the network interfaces were loopback-only, and Chromium could load the local test page. [Playwright Docker documentation](https://playwright.dev/docs/docker) · [Docker none network driver](https://docs.docker.com/engine/network/drivers/none/)

## PRD-01

Complete on 22 November 2026. The Python CLI, owned checkout fixture, independent Playwright harness, and Docker runner passed the exit gate in Chromium `159.0.8154.6` on Linux ARM64. [PRD-01 requirements](prds/PRD-01-verification-cli.md)

| Command | Observed result |
| --- | --- |
| `./scripts/setup.sh` from a clean project copy | Created a fresh venv, installed `bverify`, and passed the Chromium smoke test. |
| `.venv/bin/python scripts/prepare-checkout.py` | Created the registered repo and prewarmed its npm cache in the pinned Linux image. A repeat run returned the same two SHAs. |
| `.venv/bin/bverify compare --repo .buildverify/checkout/repo --base checkout-base --head checkout-fixed --profile profiles/checkout.json --out .buildverify/prd01-final` | `VERIFIED`, exit `0`. The base charged `$110.00` instead of `$90.00` twice, the candidate passed the discount test twice, and the ordinary checkout test passed in all four attempts. |
| `npm run typecheck` and `npm run build` in the pinned image with offline dependencies | TypeScript passed and Vite produced the production bundle. |
| `docker inspect` on a live app/harness pair | Confirmed separate read-only roots, non-root users, a loopback-only app network shared by the harness, and a writable evidence bind mounted in the harness alone. |
| `.venv/bin/python tests/prd01_exit_gate.py` | All 10 scenarios matched their expected verdict, exit code, and reason. Verified failure trace ZIPs and PNG screenshots. The known-good run ignored uncommitted files in the app checkout. |

The fixture tags resolve to `1c3bc345870aa77ac9a3d3c3fc1d40134437c7bd` (`checkout-base`) and `027a8f6d647b2f8d278038c77511bc224ce77c77` (`checkout-fixed`). The documented comparison also passed in the clean project copy, using a freshly populated npm cache. The retained demonstration is in `.buildverify/prd01-final/` and the exit-gate results are in `.buildverify/prd01-gates-l3pdwa7k/`.

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
