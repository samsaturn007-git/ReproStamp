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

## PRD-02

Implemented on 23 November 2026. The checkout and shipping profiles require Chromium, Firefox, and WebKit. Both use the same frozen harness and browser settings for every attempt within a comparison. The Verification Receipt records the immutable inputs, observed builds, case outcomes, verdicts, and approved artifact hashes. It is available as `receipt.json`, `receipt.md`, and `receipt.zip`. [PRD-02 requirements](prds/PRD-02-receipt-and-replay.md)

| Command | Observed result |
| --- | --- |
| `./scripts/setup.sh --all-browsers` | Passed 3 smoke tests on Linux ARM64. Recorded Chromium `159.0.8154.6`, Firefox `159.0`, and WebKit `27.2`. |
| `.venv/bin/python scripts/prepare_fixture.py shipping` | Rebuilt the independent shipping harness snapshot with the shared browser settings and reporter, warmed its npm cache, and confirmed both shipping SHAs. |
| `.venv/bin/python tests/prd01_exit_gate.py` | Passed all 10 scenarios before PRD-02 changes, after adding the matrix and receipts, and from the fresh project copy. Four timeout workloads reached app readiness and were removed on each run. |
| `.venv/bin/python tests/prd02_exit_gate.py` | Checkout and shipping each returned `VERIFIED`, exit `0`. Each run completed 12 attempts and 24 case executions. The expected assertion failed on all 6 base attempts, passed on all 6 candidate attempts, and the corresponding regression passed on all 12 attempts. Each bundle passed offline verification and contained 6 baseline traces and 6 screenshots. |
| `verify` via `tests/prd02_exit_gate.py` | Returned exit `2` for a modified receipt, a same-size replacement trace, a missing artifact, an unsafe ZIP entry, and a malformed attempt with a recomputed manifest hash. |
| `replay` via `tests/prd02_exit_gate.py` | Replayed all 12 checkout attempts using a separate Git clone and harness copy. The new receipt linked the original payload hash. A changed oracle and an unavailable pinned image each returned `INCONCLUSIVE`, exit `3`, with a specific reason and zero new attempts. |
| `diff-receipts` via `tests/prd02_exit_gate.py` | Found matching inputs and no changed case outcomes for the replay. Aligned 6 changed candidate assertions against the ineffective run and flagged the changed oracle as a barrier to comparison. |
| Required-cell scenarios via `tests/prd02_exit_gate.py` | A skipped Firefox case returned `INCONCLUSIVE` with `required_cell_missing`. An unavailable Firefox executable returned `INCONCLUSIVE` with `required_engine_unsupported`. Both exported valid receipts with the missing or unsupported cells labeled. |
| `docker inspect` on live app and harness containers | Both ran as `pwuser` with read-only root filesystems. The harness shared the app's isolated network and was the only workload with writable evidence storage. |
| `env PATH=/usr/bin:/bin .venv/bin/reprostamp verify .reprostamp/prd02-checkout-proxy-fix/receipt.zip` | Verified all 37 manifest files with Docker and Node.js excluded from `PATH`. |
| README setup, fixture preparation, `compare`, `verify`, `replay`, and `diff-receipts` commands in a fresh project copy | Created a new venv and populated empty fixture caches. Checkout, checkout replay, and shipping each returned `VERIFIED`, exit `0`. Both bundle checks passed and the replay diff reported matching inputs and outcomes. |
| `git diff --check` and `.venv/bin/python -m compileall -q src scripts tests` | Passed. |

The first comparison attempts in WebKit exposed a proxy lookup failure when proxy variables were present with empty values. The runner now removes them before launching either workload, with the Docker network isolated throughout. Both fixture matrices passed after the change. The original inconclusive receipts remain in `.reprostamp/prd02-checkout-dev/` and `.reprostamp/prd02-shipping-dev/`.

The repeated PRD-02 exit suite retained its checkout, shipping, and replay bundles in `.reprostamp/prd02-gates-hrrvrsck/`. It found no remaining attempt containers or temporary workspaces for the checked runs. No PRD-02 exit checks remain open.

The PRD-03 readiness audit reran `.venv/bin/python tests/prd02_exit_gate.py` on 23 November 2026. All exit checks passed again. The new evidence is in `.reprostamp/prd02-gates-wxy_i8ut/`. `env PATH=/usr/bin:/bin .venv/bin/reprostamp verify .reprostamp/prd02-gates-wxy_i8ut/checkout/receipt.zip` also verified all 37 manifest files and reported the recorded `VERIFIED` verdict.

The implementation audit on 23 November 2026 reran both dependency suites against the current workspace. `.venv/bin/python tests/prd01_exit_gate.py` passed all 10 scenarios and confirmed cleanup for the four timed-out workloads. `.venv/bin/python tests/prd02_exit_gate.py` passed the checkout and shipping matrices, independent replay, offline integrity checks, and missing or unsupported browser cases. Evidence is in `.reprostamp/prd01-gates-zzvjvhql/` and `.reprostamp/prd02-gates-msg6cmyw/`.

## PRD-03 readiness

Setup verified on 23 November 2026. The required PRD-02 exit gate passed. Docker Compose now provides a pinned local PostgreSQL service, the Python API stack installs as an optional extra, and the dashboard has a locked npm dependency tree. [PRD-03 requirements](prds/PRD-03-dashboard-and-durable-runs.md) · [Setup commands](../README.md#run-the-local-dashboard)

| Command or check | Observed result |
| --- | --- |
| `docker buildx imagetools inspect postgres@sha256:1757c628698dd1ca67ff7a5fc386bfd91040afc62a45484c346c788b0cbe5402` | The pinned PostgreSQL 18.7 image index includes Linux ARM64 and AMD64. |
| `.venv/bin/python scripts/setup_prd03.py` | Installed FastAPI `0.165.0`, Pydantic `2.14.4`, Uvicorn `0.54.0`, SQLAlchemy `2.1.9`, psycopg `3.3.9`, and Alembic `1.20.1`. Connected to PostgreSQL `18.7` through `127.0.0.1:55432`. Alembic reported no applied revisions. |
| OpenAPI smoke check in `scripts/setup_prd03.py` | Next.js `16.4.6` started its CLI. `openapi-typescript` `7.13.0` generated declarations from a FastAPI OpenAPI document, and TypeScript `5.9.3` compiled a client using those declarations. |
| PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED` over two connections | While one transaction held the first row, the second claimed the next row. The probe table was dropped. |
| `.venv/bin/python scripts/setup_prd03.py --stop` followed by setup from the parent directory | The port stopped accepting connections. Setup restarted PostgreSQL with the same cluster identity and an empty application schema. The service was left healthy and bound to loopback. |
| `.venv/bin/python -m pip check`, `docker compose --file compose.prd03.yml config --quiet`, and `git diff --check` | Passed. |

## PRD-03

Implemented on 23 November 2026. The local dashboard submits comparisons against registered repositories and profiles using an owner session and CSRF protection. PostgreSQL records execution states, attempts, events, and artifact references. Submission freezes the Git commits, profile, and independent harness. The worker retries once after lease expiry and publishes evidence only under the active fencing token. The dashboard resumes the timeline and displays case results, verdict reasons, and a 30-day evidence expiry. [Run the dashboard](../README.md#run-the-local-dashboard)

| Command or check | Observed result |
| --- | --- |
| `.venv/bin/python scripts/setup_prd03.py` | Installed locked dependencies, connected to PostgreSQL 18.7, and generated and type-checked the dashboard client from the actual API schema. |
| `.venv/bin/python -m reprostamp.control migrate` | Applied `0001_durable_runs`. A second invocation preserved the same revision. The integration suite applied it again to a separate empty database. |
| `npm --prefix dashboard run build` | Production build and TypeScript checks passed. |
| `.venv/bin/python tests/prd03_exit_gate.py` | The browser signed in, submitted checkout, disconnected after event 3, and recovered all 38 ordered events. The replacement for a killed worker used the original commits and harness after the registered inputs changed. It produced one `VERIFIED` receipt after 12 attempts and 24 case executions. A stale token could neither record progress nor finalize. Two worker losses on another run exhausted the single retry and left the run incomplete with no verdict or receipt. |
| Access and retention checks in `tests/prd03_exit_gate.py` | Concurrent duplicate requests returned one run ID and a changed request with the same key returned 409. Queued and active cancellation kept the verdict empty. Anonymous downloads returned 401, traces were ZIP attachments, HTML in log text rendered as text, expired downloads returned 410, and the worker removed expired files. |
| `env PATH=/usr/bin:/bin .venv/bin/reprostamp verify .reprostamp/prd03-gates-2sxvpxdl/ui-receipt.zip` | Verified all 37 manifest files without Docker or Node.js on `PATH`. A diff against the PRD-02 checkout receipt showed matching inputs and case outcomes. |
| `npm --prefix dashboard run start` and a Playwright smoke check at `390 × 844` | The production build was reachable on loopback. The owner signed in, opened the completed checkout run, saw all 27 timeline events, and signed out. The page fit the viewport. |
| `git diff --check`, `.venv/bin/python -m compileall -q src scripts tests`, `.venv/bin/python -m pip check`, and `docker compose --file compose.prd03.yml config --quiet` | Passed. |

The first browser acceptance run exposed compression buffering on live events through the dashboard proxy. The SSE response now sends `no-transform`, and the browser verified that `Last-Event-ID` resumes delivery through the proxy.

No PRD-03 exit checks remain open. The worker-recovery recording, screenshot, receipt, and trace are in `.reprostamp/prd03-gates-2sxvpxdl/`. The exit suite found no comparison containers left after recovery, cancellation, or exhausted retry.

A fresh readiness audit on 23 November 2026 reran `.venv/bin/python tests/prd03_exit_gate.py` and `npm --prefix dashboard run build`. Both passed. The browser recovered 38 ordered events, the replacement worker produced one receipt, and the 37-file bundle passed `verify` with Node.js and Docker excluded from `PATH`. Evidence is in `.reprostamp/prd03-gates-e4l7w6ve/`.
