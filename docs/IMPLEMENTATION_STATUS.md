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

## PRD-04

Started on 23 November 2026 on `codex/prd04-github-pilot` from the locally verified PRD-02 and PRD-03 checkpoint `de86859`. The dedicated private checkout fixture at [reprostamp-checkout-pilot](https://github.com/samsaturn007-git/reprostamp-checkout-pilot) starts from `d3e8d0413daf4064085e7713206c3fa937d95b15`. The repository contains the fixture application and lockfile. The profile, harness, credential files, and evidence stay outside it. [Run the pilot](../README.md#run-the-github-pilot)

| Command or check | Observed result |
| --- | --- |
| `.venv/bin/python -m reprostamp.control migrate` | Upgraded the existing PostgreSQL database from `0001_durable_runs` to `0002_github_pilot`. The local pilot suite applied both migrations to a fresh database. |
| `.venv/bin/python tests/prd04_pilot.py` | Passed with a local GitHub HTTP test server and three real runs in the pinned Linux ARM64 browser image. The signed intake rejected an invalid signature, ignored fork and unapproved repository deliveries, and deduplicated a repeated delivery ID. |
| Check publication and reconciliation in `tests/prd04_pilot.py` | The first fixture commit received `failure`, the subsequent fix received `success`, and a third commit that moved while its run was active received a superseded `neutral` check. An out-of-order delivery queued no run. The server dropped its first creation response after persisting the check. Reconciliation found the original by external ID and preserved exactly one check for that head. |
| Timing from `.reprostamp/prd04-pilot-dt5yb8gu/integration.log` | Three runs, 36 browser attempts, and 72 case executions. Observed queue times were 223, 38, and 322 ms. Summed browser attempt durations were 33.156, 28.678, and 28.793 seconds. Response-loss reconciliation took approximately 5.1 seconds with one publication failure. |
| `npm --prefix dashboard run build` | Passed with the regenerated API client and the superseded evidence indicator. |
| `.venv/bin/python tests/prd03_exit_gate.py` | Passed after the new migration. The browser recovered 38 events and verified the replacement worker receipt. Evidence is in `.reprostamp/prd03-gates-thuh18b6/`. |

The owner selected the dedicated fixture and authorized a temporary Cloudflare Quick Tunnel for the webhook. `gh repo create --private`, `git push --set-upstream origin main`, and `gh api repos/samsaturn007-git/reprostamp-checkout-pilot/commits/main` confirmed the private repository and expected baseline SHA. Homebrew installed `cloudflared` and `cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8001` assigned an HTTPS URL. The dashboard and evidence remain on loopback.

The private ReproStamp Checkout Pilot App was registered and installed with access to the checkout fixture only. The App key authenticated with `GET /app`, and `GET /repos/{owner}/{repo}/installation` confirmed a selected-repository installation. The scoped installation token listed one repository, read check runs, and fetched the private baseline into a fresh Git repository. The dashboard and the GitHub integration use the owner-managed pilot registry.

The original temporary tunnel stopped resolving. A new Quick Tunnel forwarded an unsigned webhook request as HTTP 401, a dashboard path as HTTP 404, and a locally signed ping as HTTP 202. The first App's webhook returned to inactive after saving, and its authenticated `GET /app/hook/config` and `PATCH /app/hook/config` returned HTTP 404. The owner approved registering ReproStamp Checkout Webhook Pilot from a GitHub App manifest with the webhook active at creation. The GitHub API confirmed TLS verification, the `pull_request` event subscription, and installation access to the checkout fixture only.

### Live GitHub exit checks

| Command or check | Observed result |
| --- | --- |
| `REPROSTAMP_REGISTRY=.reprostamp/prd04/registry.json .venv/bin/python -m reprostamp.github --config .reprostamp/prd04/manifest-live/github.json` | Served the signed webhook on loopback port 8001 through the authorized temporary tunnel. The installation token fetched each candidate into the registered baseline-only checkout. |
| `REPROSTAMP_REGISTRY=.reprostamp/prd04/registry.json .venv/bin/python .reprostamp/prd04/live-pilot.py .reprostamp/prd04/manifest-live/github.json` | Pushed three fixture commits and opened [pull request #1](https://github.com/samsaturn007-git/reprostamp-checkout-pilot/pull/1). The first commit `c360789b` received a `failure` check. While the interim commit `8ff30052` was running, the PR moved to `27fba0df`. GitHub reported the interim evidence as superseded with a `neutral` conclusion and the final fix as `success`. The three check detail URLs identified the matching runs and their offline receipts recorded the exact tested head SHAs. |
| GitHub App delivery history and one `POST /app/hook/deliveries/{id}/attempts` | GitHub reported HTTP 202 for the opening event and both synchronize events. Redelivery of the opening event returned HTTP 202 and retained one queue entry for its delivery ID. |
| `gh pr view 1 --repo samsaturn007-git/reprostamp-checkout-pilot --json headRefOid,state,url,statusCheckRollup` | Confirmed the open PR's head is `27fba0df8e6c2ede162e75e63daa9b8d6223059d` and its ReproStamp check is completed with `SUCCESS`. |
| PostgreSQL run metrics and receipt verification | Three live runs on the pinned Linux ARM64 image produced 36 browser attempts and 72 case executions. Queue times were 126, 382, and 26,552 ms. Summed browser attempt durations were 42.053, 34.420, and 30.411 seconds. All three bundles verified and Docker reported no remaining comparison containers. The live run logged zero worker recoveries and publish failures. The local response-loss recovery result is recorded above. |
| `npm --prefix dashboard run typecheck`, `.venv/bin/python -m compileall -q src tests`, `.venv/bin/python -m pip check`, and `git diff --check` | Passed. |

All PRD-04 exit checks passed on 23 November 2026. Live evidence is in `.reprostamp/prd04/github-live-checks.json`, `.reprostamp/prd04/github-live-deliveries.json`, and `.reprostamp/prd04/live-manifest-integration.log`. The local receipts and simulated response-loss evidence are in `.reprostamp/prd04-pilot-dt5yb8gu/`.

## PRD-05 dependency audit

Rechecked the pre-PRD setup and PRD-01 through PRD-04 on 23 November 2026. All prerequisite exit gates passed. The live audit used the existing approved PR and read-only GitHub API calls.

| Command or check | Observed result |
| --- | --- |
| `./scripts/setup.sh --all-browsers` and `shasum -a 256 -c CONTENTS_SHA256.txt` from `docs/reference/original_prd_pack` | Pinned Linux ARM64 loopback smoke passed in Chromium `159.0.8154.6`, Firefox `159.0`, and WebKit `27.2`. All 10 archive checksums matched. |
| `.venv/bin/python tests/prd01_exit_gate.py` | All 10 scenarios passed. Four timed-out workloads reached app readiness and were cleaned up. Evidence is in `.reprostamp/prd01-gates-h9z45wnq/`. |
| `.venv/bin/python tests/prd02_exit_gate.py` | Both repositories passed the three-engine matrix with 12 attempts and 24 case executions each. The independent checkout replay matched. The tampering, missing evidence, changed oracle, and unavailable image and browser checks passed. Evidence is in `.reprostamp/prd02-gates-8zy5g7hs/`. |
| `.venv/bin/python tests/prd03_exit_gate.py` and `npm --prefix dashboard run build` | The browser recovered 38 ordered events and downloaded the recovered receipt and trace. Migration, stale completion, duplicate submission, cancellation, download authorization, and expiry checks passed. The dashboard built successfully. Evidence is in `.reprostamp/prd03-gates-r3hpl0x8/`. |
| `.venv/bin/python tests/prd04_pilot.py` | All local pilot checks passed. Three pinned Linux ARM64 runs produced 36 browser attempts and 72 case executions. The first Check creation response was lost, and reconciliation found the original check after approximately 5.1 seconds. Evidence is in `.reprostamp/prd04-pilot-m68umg6w/`. |
| `gh pr view 1 --repo samsaturn007-git/reprostamp-checkout-pilot --json headRefOid,state,url,statusCheckRollup`, `gh api repos/samsaturn007-git/reprostamp-checkout-pilot/check-runs/{check_id}`, and offline `verify_bundle` | The current PR head still shows `success`. Both older checks now show superseded `neutral`. The historical failure is recorded in the live pilot capture. All three GitHub head SHAs and detail URLs matched the retained receipts, which verified offline and recorded 12 attempts each. The archived duplicate redelivery response was HTTP 202 with one delivery row and one run. |

## PRD-05

Started on 23 November 2026. `reprostamp suggest` previews the issue summary, the receipt's repeated baseline assertion, and owner-selected files at the base commit. The approval digest binds this context to the provider, budgets, and output directory. The CLI validates the resulting changes in disposable Git storage and saves the proposal, patch hash, and usage metadata. The maintainer applies and commits any changes separately. [Run the suggestion workflow](../README.md#review-a-repair-suggestion)

| Command or check | Observed result |
| --- | --- |
| `.venv/bin/python tests/prd05_exit_gate.py .reprostamp/prd02-gates-8zy5g7hs/checkout/receipt.zip` | Passed. The deterministic provider exported two reviewed proposals. A separate checkout applied and committed each patch, then compared the resulting commit against the receipt's original base. Both runs completed in Chromium, Firefox, and WebKit on Linux ARM64, with 12 attempts and 24 case executions each. |
| Verified patch `4099d926ff9e8fbc97a6f9b18f1c9cab845782fc` | `VERIFIED` with `expected_fix_confirmed`. The candidate passed the discount assertion and the full-price regression in all six candidate attempts. The offline receipt recorded the exact reviewed commit. |
| Plausible patch `6da4e467f4a30a3b06d4d0a0513ff06df091dc7e` | `FAILED` with `candidate_assertion_failed`. The candidate charged `$95.00` in all six candidate attempts. The full-price regression passed. The offline receipt recorded the exact reviewed commit. |
| `env PATH=/usr/bin:/bin .venv/bin/reprostamp verify` against both PRD-05 receipt ZIPs | Offline verification passed for all 37 files in the `VERIFIED` bundle and all 49 files in the `FAILED` bundle. |
| Approval, scope, and budget checks in `tests/prd05_exit_gate.py` | Passed for a changed issue after approval, reused output path, malformed and duplicate JSON properties, protected tests, dependency locks and workflow paths, unselected files, mode changes, a patch that could not apply to the base, input and output byte limits, and an unreadable provider response. Preview used the committed source while the checkout contained uncommitted changes. |
| Simulated OpenAI adapter checks in `tests/prd05_exit_gate.py` | Preview and mismatched approval made no HTTP calls. A valid approval sent the reviewed context with tools disabled. The adapter rejected a simulated tool request while the issue contained untrusted instructions. It also handled output token exhaustion and HTTP 503. The successful simulated response reported 123 input tokens and 45 output tokens. The deterministic provider reported byte counts with token counts unset. |
| `git diff --check`, `.venv/bin/python -m compileall -q src scripts tests`, `.venv/bin/python -m pip check`, and `docker compose --file compose.prd03.yml config --quiet` | Passed. Docker listed zero comparison containers after the exit checks. |

The deterministic exit checks passed. Proposals, metadata, and browser receipts are in `.reprostamp/prd05-gates-nzx8x67l/`. This run used deterministic and simulated responses.

On 23 November 2026, `.venv/bin/reprostamp suggest` previewed one `gpt-5.4-mini` request using the checkout receipt, the fixture's `src/checkout.ts`, and a 2,048-token output cap. The historical preview is in `.reprostamp/prd05-cloud-34mkiK/preview.json`. A live OpenAI request remains untested because no API key was available. OpenAI usage was zero.

### Live inference without an API key

On 23 November 2026, Homebrew installed Ollama `0.40.16`. `OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11434 ollama serve` started a temporary server with cloud features disabled. The model cache and artifacts are in `.reprostamp/prd05-ollama/`. `env -u OPENAI_API_KEY .venv/bin/reprostamp suggest ... --ollama-model qwen2.5-coder:1.5b --approve <preview SHA-256>` sent only the reviewed checkout context to loopback with a 2,048-token cap. [Ollama local setup](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features)

| Command or check | Observed result |
| --- | --- |
| `ollama pull qwen2.5-coder:1.5b` and the loopback `/api/tags` endpoint | Downloaded the model with digest `d7372fd828518a4d38b1eb196c673c31a85f2ed302b3d1e406c4c2d1b64a0668`. |
| First approved local request and diagnostic repeat | Each used 549 input tokens and 666 output tokens. Both returned an invalid unified diff, and ReproStamp rejected them. |
| Approved request with clarified patch-format instructions | Used 602 input tokens and 326 output tokens. The diff passed applicability and scope checks. Its explanation identified the arithmetic bug, but review found the diff altered unrelated code and left the bug in place. The proposed diff is in `retry-proposal/candidate.patch`. |
| Approved request with a focused checkout issue summary | Used 640 input tokens and 257 output tokens. ReproStamp rejected the malformed diff. The exact context is in `focused-preview.json`. |
| `ollama pull qwen2.5-coder:3b` and approved comparison request at the same context and budgets | The model digest was `f72c60cabf6237b07f6e632b2c48d533cef25eda2efbd34bed21c5e9c01e6225`. The response used 640 input tokens and 200 output tokens. ReproStamp rejected the diff because it made no file changes. |
| `reprostamp compare --repo .reprostamp/prd05-ollama/verification-app --profile .reprostamp/prd05-ollama/verification-profile.json --base checkout-base --head HEAD --out .reprostamp/prd05-ollama/reviewed-comparison` | A reviewer removed the unrelated edits and corrected the arithmetic before committing `1a3456f639399c6e4d3440ec8c2a1f293caed499`. The reviewed commit returned `VERIFIED` with 12 attempts and 24 case executions across Chromium, Firefox, and WebKit. Offline `verify` checked all 37 receipt files. |
| `.venv/bin/python tests/prd05_exit_gate.py .reprostamp/prd02-gates-8zy5g7hs/checkout/receipt.zip` | Passed after the provider changes. Both simulated adapters passed their contract checks. The two deterministic browser runs returned `VERIFIED` and `FAILED` as expected. Evidence is in `.reprostamp/prd05-gates-emn_a4_n/`. |

The live local run made five Ollama requests, totaling 2,980 input tokens and 2,115 output tokens reported by the server. One proposal passed patch validation and required reviewer edits. The independently verified receipt is in `.reprostamp/prd05-ollama/reviewed-comparison/receipt.zip`. The temporary Ollama server was stopped, the model cache was retained for reuse, and the hosted OpenAI adapter remains untested with a live key.

## PRD-06 dependency audit

Rechecked setup and PRD-01 through PRD-05 on 24 November 2026. PRD-04 is the direct dependency for PRD-06. The optional hosted PRD-05 adapter still has no live result.

| Command or check | Observed result |
| --- | --- |
| `./scripts/setup.sh --all-browsers` and `shasum -a 256 -c CONTENTS_SHA256.txt` from the original PRD pack directory | Chromium, Firefox, and WebKit passed the pinned Linux ARM64 loopback checks. All 10 archive checksums matched. |
| `.venv/bin/python tests/prd01_exit_gate.py` | All 10 scenarios passed. Four timed-out workloads reached app readiness and were removed. Evidence is in `.reprostamp/prd01-gates-4h4s1sle/`. |
| `.venv/bin/python tests/prd02_exit_gate.py` | Both three-browser matrices, independent replay, offline integrity checks, and missing or unsupported cells passed. Evidence is in `.reprostamp/prd02-gates-7jaoptgk/`. |
| `.venv/bin/python tests/prd03_exit_gate.py` | Passed with the PRD-06 schema. The replacement worker recovered frozen inputs, the browser resumed 38 ordered events, and owner authorization, cancellation, and retention passed. Evidence is in `.reprostamp/prd03-gates-g5_112b5/`. |
| `.venv/bin/python tests/prd04_pilot.py` | The local pilot passed signature and scope checks, duplicate handling, lost-response reconciliation, and moving-head checks with real browser workloads. Evidence is in `.reprostamp/prd04-pilot-spmk0dmk/`. |
| `gh pr view 1 --repo samsaturn007-git/reprostamp-checkout-pilot --json headRefOid,state,url,statusCheckRollup`, `gh api repos/samsaturn007-git/reprostamp-checkout-pilot/check-runs/{check_id}`, and offline `reprostamp verify` on the three retained bundles | GitHub reported success for `27fba0df` and neutral for the two superseded heads. Both superseded receipts retained their recorded failed verdicts. All three bundles verified. The archived redelivery showed HTTP 202, one delivery row, and one run. |
| `.venv/bin/python tests/prd05_exit_gate.py .reprostamp/prd02-gates-8zy5g7hs/checkout/receipt.zip` and `reprostamp verify .reprostamp/prd05-ollama/reviewed-comparison/receipt.zip` | The reviewed deterministic commits returned `VERIFIED` and `FAILED` as expected. Provider and approval checks passed. The prior local-model reviewed receipt verified all 37 files. Evidence is in `.reprostamp/prd05-gates-20vkbqgy/`. |

## PRD-06

Implemented and verified on 24 November 2026. **Replay failing case** queues five isolated attempts for the selected browser and case using the source commit and frozen profile. The dashboard shows durations, outcomes, and available traces. Replay classifications remain separate from verification verdicts. Repository failure history groups receipt-backed application assertions and runner or dependency failures. [Dashboard workflow](../README.md#replay-a-failing-case)

| Command or check | Observed result |
| --- | --- |
| `.venv/bin/python -m reprostamp.control migrate` | Upgraded the existing PostgreSQL database from `0002_github_pilot` to `0003_case_replays`. A repeat made no schema changes. The exit suite also migrated a fresh database. |
| `.venv/bin/python tests/prd06_exit_gate.py` | Passed on the pinned Linux ARM64 runner. Replays produced five attempts per fixture, including traces on passing attempts. The runner startup failure recorded five incomplete attempts with logs. A replay used the original commit and harness after the registered ref and harness moved. The suite checked owner authorization, idempotency, and evidence expiry. |
| Repository failure history in `tests/prd06_exit_gate.py` | Grouped eight `checkout.full-price` failures at `src/checkout.ts:17` across Chromium, Firefox, and two receipts, with distinct first and last observation times. The startup failure appeared separately. |
| Dashboard browser checks in `tests/prd06_browser.cjs` | Submitted a replay from the failed attempt, showed five durations and trace links, and opened the original attempt from the replay. The mobile layout at `390 × 844` showed all four outcome columns without horizontal scrolling. |
| `env PATH=/usr/bin:/bin .venv/bin/reprostamp verify .reprostamp/prd06-gates-80hx9nho/consistent-receipt.zip` | Verified all 33 files offline. The original receipt retained its `FAILED` verdict and `candidate_regression` reason. |
| `npm --prefix dashboard run build`, `.venv/bin/python -m compileall -q src scripts tests`, `.venv/bin/python -m pip check`, and `git diff --check` | Passed. Docker reported zero remaining comparison containers after the exit suite. |

| Labeled fixture | Passing attempts | Assertion failures | Infrastructure failures | Replay classification |
| --- | ---: | ---: | ---: | --- |
| Consistent regression | 0 | 5 | 0 | Consistent failure |
| Mixed assertion | 3 | 2 | 0 | Suspected flaky |
| Runner startup failure | 0 | 0 | 5 | Infrastructure failure |
| Order-dependent assertion | 5 | 0 | 0 | Passed on replay |

The order-dependent case passed all five isolated attempts. The original failed attempt stayed visible, and its receipt remained byte-for-byte identical. No PRD-06 exit checks remain open. The final evidence is in `.reprostamp/prd06-gates-80hx9nho/`, including `classifications.json`, `failure-groups.json`, source receipts, and desktop and mobile screenshots.

## PRD-07

Implemented on 24 November 2026. The recorded live PRD-04 gate and a fresh local GitHub pilot run verified the direct dependency. `.venv/bin/python tests/prd04_pilot.py` retried a lost check-creation response, published failure and success for the tested commits, and preserved evidence for a superseded head. The post-migration pilot passed again and retained its logs and receipts in `.reprostamp/prd04-pilot-g59ayht3/`. Offline verification matched the three archived live receipts to their recorded SHAs and 12 attempts each. [PRD-07 specification](prds/PRD-07-visual-accessibility-review.md) · [Dashboard workflow and keyboard walkthrough](../README.md#review-visual-and-accessibility-changes)

The profile selects a browser and routes. The approved harness captures each route twice per commit under the pinned image, viewport, fonts, and page seed. The receipt includes the pixel diff and newly detected axe findings. Checks default to advisory. The single dashboard owner can approve the exact candidate screenshot, and a fresh comparison uses approvals available at its first worker claim.

| Command or check | Observed result |
| --- | --- |
| `.venv/bin/python -m reprostamp.control migrate` | Upgraded the existing database from `0003_case_replays` to `0004_route_reviews`. A repeat made no schema changes. The pilot also migrated a fresh database. |
| `.venv/bin/python scripts/prepare_fixture.py checkout-review` | Created an independent versioned review harness snapshot and prewarmed its locked Playwright and axe-core `4.14.1` dependencies. The checkout commits matched the existing fixture tags. |
| `.venv/bin/reprostamp compare --repo .reprostamp/checkout/repo --profile profiles/checkout-review.json --base checkout-base --head checkout-fixed --out .reprostamp/prd07-sample-lEDFgK/compare` | Returned `VERIFIED` after 12 functional attempts on Chromium, Firefox, and WebKit. The configured Chromium route showed zero changed pixels and no new axe findings. The receipt verified all 40 files. |
| `.venv/bin/python tests/prd07_exit_gate.py` | Passed on Linux ARM64, Chromium `159.0.8154.6`, viewport `1100 × 800`, and seed `42`. The three screenshots matched their manifest hashes and the diff contained exactly 43,249 changed pixels for the first layout shift. Axe reported the new `label` violation at `#promo` with critical impact. The other configured route remained unchanged. |
| Dashboard and keyboard checks in the PRD-07 gate | Viewed the three authenticated images, approved the candidate from the dashboard with Enter, opened approval history, and confirmed that the review fit a `390 × 844` viewport. The checkout walkthrough confirmed visible focus on the input and Apply button, reverse tab order, and the status message after keyboard submission. |
| Approval and integrity checks in the PRD-07 gate | Anonymous requests and requests with an invalid CSRF token were rejected. Incorrect receipt and screenshot hashes were rejected. Retrying approval retained one record. The source receipt stayed byte-for-byte identical, and approval history remained visible after the source run expired. Offline verification rejected a tampered screenshot binding even with a recomputed receipt payload hash. |
| `env PATH=/usr/bin:/bin .venv/bin/reprostamp verify` on the advisory, approved, and replayed receipts | Each bundle verified all 19 files. A CLI replay reproduced the approved screenshot binding and linked its source payload hash. |
| `.venv/bin/python tests/prd03_exit_gate.py` | Passed after the PRD-07 migration. The browser recovered 38 ordered events and downloaded the receipt and trace. Lease recovery, cancellation, owner authorization, and evidence expiry passed. Evidence is in `.reprostamp/prd03-gates-kr9sfqsw/`. |
| `npm --prefix dashboard run build`, `npm --prefix dashboard run typecheck`, `.venv/bin/python -m compileall -q src scripts tests`, `.venv/bin/python -m pip check`, `docker compose --file compose.prd03.yml config --quiet`, and `git diff --check` | Passed. |

| Pilot scenario | Execution state | Verification verdict | Route review result |
| --- | --- | --- | --- |
| Advisory layout shift and unlabeled promo input | Completed | `VERIFIED` | 43,249 changed pixels and one new axe finding |
| Required accessibility check | Completed | `FAILED` | `required_accessibility_regression` |
| Required intentional screenshot change | Completed | `FAILED` | `required_visual_change` |
| Exact rerun with the owner's approval | Completed | `VERIFIED` | Screenshot approved with the original commit, profile, browser build, and digest |
| Later screenshot | Completed | `FAILED` | 75,520 changed pixels and fresh approval required |
| Same screenshot bytes on a different commit | Completed | `FAILED` | Fresh approval required |
| Missing advisory route evidence | Completed | `VERIFIED` | Both route checks unavailable |
| Missing required visual evidence | Completed | `INCONCLUSIVE` | `required_visual_unavailable` |

No PRD-07 exit checks remain open. Both full gate runs passed. Browser screenshots, receipts, the replay, and service logs from the repeat run are in `.reprostamp/prd07-gates-wpuybh_2/`. Docker listed zero comparison containers after that run.

## PRD-08 dependency audit

On 24 November 2026, rechecked setup and the exit gates for PRD-01 through PRD-07. The dashboard audit exposed two races. The **New run** buttons now wait for registry loading, and the event stream opens a new connection with its last observed cursor if an HTTP error permanently closes the browser's connection. The recovery test waits for an actual proxy error before restarting the API.

| Command or check | Observed result |
| --- | --- |
| `./scripts/setup.sh --all-browsers`, `scripts/prepare-checkout.py`, `scripts/prepare_fixture.py shipping`, `scripts/prepare_fixture.py checkout-review`, and the original pack's `shasum -a 256 -c CONTENTS_SHA256.txt` | All three pinned Linux ARM64 browsers and all 10 archive checksums passed. All fixture caches and frozen harnesses were prepared. |
| `.venv/bin/python tests/prd01_exit_gate.py` | All 10 scenarios passed. The four deadline tests reached app readiness and cleaned up afterward. Evidence is in `.reprostamp/prd01-gates-sguzz090/`. |
| `.venv/bin/python tests/prd02_exit_gate.py` | Checkout and shipping each passed 12 browser attempts and 24 case executions. Independent replay, bundle integrity, and missing input checks passed. Evidence is in `.reprostamp/prd02-gates-y6bt8u2r/`. |
| `.venv/bin/python -m reprostamp.control openapi .reprostamp/prd03/openapi.json`, `npm --prefix dashboard run generate`, and `.venv/bin/python tests/prd03_exit_gate.py` | The repaired dashboard recovered 34 ordered events through the proxy outage using event 3 as its cursor. It downloaded one receipt and a trace. Fencing, cancellation, exhausted recovery, authorization, expiry, and migration passed. Evidence is in `.reprostamp/prd03-gates-7l6jq8ux/`. |
| `gh pr view 1`, `gh api repos/samsaturn007-git/reprostamp-checkout-pilot/check-runs/{check_id}`, and offline `verify_bundle` for the live pilot | GitHub still reports success at `27fba0df` and neutral for both superseded heads. All three GitHub SHAs and evidence links matched the archived receipts, each with 12 attempts. The archived duplicate redelivery returned HTTP 202 with one delivery row and one run. |
| `.venv/bin/python tests/prd04_pilot.py` | The sequential rerun passed signed intake, fork exclusion, deduplication, reconciliation after a lost response, and supersession while the pinned browser workloads ran. Three runs covered 36 browser attempts and 72 case executions. Queue times were 311, 526, and 244 ms. Summed browser attempt times were 54.820, 47.052, and 46.388 seconds. Reconciliation took 5.191 seconds after the publication failure. Evidence is in `.reprostamp/prd04-pilot-x_m6j7tf/`. |
| Offline `reprostamp verify` on the two PRD-05 deterministic proposals and the local-model comparison | The reviewed candidates retained `VERIFIED`, `FAILED`, and `VERIFIED` respectively. The hosted OpenAI adapter has simulated coverage and no live result. |
| `.venv/bin/python tests/prd05_exit_gate.py .reprostamp/prd02-gates-y6bt8u2r/checkout/receipt.zip` | Both reviewed proposals matched their expected verdicts after 12 attempts each. The approval, budget, patch scope, and simulated adapter checks passed. The repeat after sharing the provider request and usage code with PRD-08 also passed. Evidence is in `.reprostamp/prd05-gates-w93qcc57/` and `.reprostamp/prd05-gates-ihw_8rub/`. |
| `verify_bundle` on the four retained PRD-06 receipts and review of `classifications.json` | All original receipts verified. The four labeled five-attempt replays confirmed consistent failure, suspected flake, infrastructure failure, and pass on replay. The original order-dependent assertion failure remains visible in its receipt. |
| `.venv/bin/python tests/prd06_exit_gate.py` | The sequential rerun matched all four replay classifications and passed the dashboard, grouped history, authorization, idempotency, and expiry checks. Evidence is in `.reprostamp/prd06-gates-8ioyvfxj/`. |
| `verify_bundle` on the eight retained PRD-07 receipts and the offline replay | All nine bundles verified. The seeded change recorded 43,249 changed pixels and the critical axe `label` finding at `#promo`. The owner approval replayed against its exact binding. Later screenshots and a different commit required review. Advisory and required outcomes matched the profile. |
| `.venv/bin/python tests/prd07_exit_gate.py`, `npm --prefix dashboard run build`, and `npm --prefix dashboard run typecheck` | All eight route review scenarios, exact approval replay, keyboard and mobile dashboard checks, and the production build and typecheck passed. Evidence is in `.reprostamp/prd07-gates-_1vygrdy/`. |

The retained local PRD-04 pilot log and check capture also confirm reconciliation after one lost response, two conclusive checks, and a third run superseded during execution. An earlier parallel rerun exceeded the pilot's 120-second wait on the moving-head case. The sequential rerun passed. No PRD-01 through PRD-07 exit checks remain open.

## PRD-08

Started on 24 November 2026 after checking the previous exit gates. The starter uses one React and FastAPI task-tracker template. The request or local JSON controls the project name, optional task fields, and ordered status labels. The CLI exports locked source and a `starter_validation` receipt. [PRD-08 specification](prds/PRD-08-verified-app-starter.md) · [Starter workflow](../README.md#generate-and-validate-a-task-tracker)

| Command or check | Observed result |
| --- | --- |
| `.venv/bin/reprostamp starter prepare --cache .reprostamp/prd08-cache` | Downloaded the pinned pip wheel, locked Python wheels, and npm dependencies. Validation used the existing Playwright image on Linux ARM64 with offline installs and loopback-only networking. |
| `.venv/bin/python tests/prd08_exit_gate.py --cache .reprostamp/prd08-cache` | Field Notes, Studio Requests, and an unzipped Studio Requests rerun each passed 9 checks across Chromium `159.0.8154.6`, Firefox `159.0`, and WebKit `27.2`. Each engine checked FastAPI health, task CRUD, and creation, editing, completion, and persistence after a page reload in the browser. The suite rejected an invalid configuration and incorrect approval before creating output. An altered source archive in the receipt failed integrity verification. Evidence is in `.reprostamp/prd08-gates-smnh66l3/`. |
| Initial comparison with `starter generate --config examples/starter/field-notes.json` | API checks passed and the browser journey failed in all three engines. The priority label wrapped the select and included its option text. Explicit labels fixed the issue. The initial failure receipt and all three traces verified offline in `.reprostamp/prd08-field-first/`. |
| Startup commands from the extracted Studio Requests README | A clean venv installed the locked dependencies, `npm ci` and `npm run build` passed, and Uvicorn served the app and health endpoint on a free loopback port. A task created through the API persisted across a restart via SQLite. Logs are in `.reprostamp/prd08-host-smoke/uvicorn.log`. |
| `starter generate --description examples/starter/field-notes.txt --ollama-model qwen2.5-coder:3b` preview and matching `--approve` request | One live request to loopback with `OLLAMA_NO_CLOUD=1` returned the requested configuration. Ollama reported 141 input and 42 output tokens. The generated app passed all 9 isolated checks. The usage record and receipt are in `.reprostamp/prd08-live/`. The temporary Ollama server was stopped. |
| `env PATH=/usr/bin:/bin .venv/bin/reprostamp starter verify` on both sample bundles, the extracted-source rerun, and the live bundle | All four passing bundles verified 8 files each without Docker or Node.js on `PATH`. |
| Clean venv, `python -m pip install .`, and `python tests/prd08_exit_gate.py --mock-only` | The local CI command passed all 9 deterministic checks from the installed package and a fresh dependency cache. The package includes the maintained template and independent harness. Evidence is in `.reprostamp/prd08-gates-_7hmcoyt/`. |
| `.venv/bin/python tests/prd01_exit_gate.py` after sharing the isolated container runner with the starter | All 10 scenarios passed again. All four deadline cases reached app readiness and cleaned up after the timeout. Docker reported no remaining comparison containers. Evidence is in `.reprostamp/prd01-gates-ewgv76s1/`. |

The PRD-08 exit gate passed locally. The first hosted GitHub Actions run at `e766984` passed all nine mock configuration checks in Chromium, Firefox, and WebKit. The job finished in 1 minute 8 seconds. [Hosted starter validation](https://github.com/samsaturn007-git/ReproStamp/actions/runs/45405766943)

Live inference was verified with local Ollama. The optional hosted OpenAI path has simulated provider coverage from PRD-05 and no live result.

## PRD-09 readiness

Rechecked the starter exit gate on 24 November 2026 before adopting the archived proposal as the basis for active scope. [PRD-09 specification](prds/PRD-09-bounded-app-generation-and-evaluation.md) · [Archived PRD-09](reference/original_prd_pack/docs/PHASED_PRDS.md#prd-09--full-stack-app-generation-adaptive-context-and-ab-evaluation-p2)

| Command or check | Observed result |
| --- | --- |
| `.venv/bin/python tests/prd08_exit_gate.py --cache .reprostamp/prd08-cache` | Field Notes, Studio Requests, and the extracted-source rerun each passed all 9 checks across Chromium, Firefox, and WebKit. Invalid configuration, incorrect approval, and receipt tampering were rejected. Evidence is in `.reprostamp/prd08-gates-gqdzmwt1/`. |
| `env PATH=/usr/bin:/bin .venv/bin/reprostamp starter verify` on the three retained PRD-08 gate bundles and the live Ollama bundle | All four bundles verified 8 files each and reported passing validation. |
| `docker ps -a --filter label=io.reprostamp.run --format '{{.Names}}'` | No ReproStamp workload containers remained after the gate. |
| `shasum -a 256 -c CONTENTS_SHA256.txt` from `docs/reference/original_prd_pack` | All 10 archive checksums matched. |

## PRD-09

Implemented on 24 November 2026 using the approved scope derived from the archived proposal. The CLI generates one React and FastAPI task-tracker template with typed configuration and presentation patches. Exports include a command and preview manifest, MIT license, dependency locks, unit tests, and startup instructions. The independently maintained Playwright harness stays outside the export. [Active specification](prds/PRD-09-bounded-app-generation-and-evaluation.md) · [CLI workflow](../README.md#generate-a-task-tracker-with-a-bounded-patch) · [Evaluation](PRD09_EVALUATION.md)

| Command or check | Observed result |
| --- | --- |
| `.venv/bin/python tests/prd08_exit_gate.py --cache .reprostamp/prd08-cache` after adding the v2 workflow | Both configurations and the extracted-source rerun passed all 9 checks. Earlier v1 receipts still verified offline. Evidence is in `.reprostamp/prd08-gates-l8t58_oi/`. |
| Clean venv, `python -m pip install .`, and `python -m pip check` | Installed the generator assets and independent harness from the built package. Dependency consistency passed. |
| `python tests/prd09_exit_gate.py --cache .reprostamp/prd08-cache` from the clean install | Passed sequentially. Golden plans passed 1 of 2 single-stage trials and 2 of 2 plan-and-review trials. The seeded incorrect empty-state message failed in three engines. Direct generation and extracted-source revalidation each passed all 12 browser checks and produced the same source SHA-256 as the benchmark export. The gate rejected unsupported stacks, file and script edits, a symlink, a modified dependency manifest, and the wrong approval digest. One changed file caused one index rebuild, and diagnostic text ranked it first. Evidence is in `.reprostamp/prd09-gates-8gj2e_ly/`. |
| `shasum -a 256` on the three Field Notes archives and offline `reprostamp starter verify` | The three archives matched at `622415b97b9f1de5babc83ebf9278b48fefc0e5fade6497ef2c0292be47e4a1a`. The passing and seeded-failure receipts verified 8 and 14 files respectively and preserved their recorded outcomes. |
| Startup and test commands in the extracted Field Notes export | Locked Python and Node installs, TypeScript, the Vite build, and all three unit and whitespace checks passed. Uvicorn served the frontend and returned HTTP 200 from `/api/health` on a free loopback port. Logs are in `.reprostamp/prd09-host-qshXST/`. |
| `app generate --requirements examples/app/field-notes.txt --arm plan-review --ollama-model qwen2.5-coder:3b --planner-model qwen2.5-coder:1.5b` preview and matching `--approve` | The local provider reported 1,804 input and 214 output tokens across three calls. All 12 cross-browser checks passed. The experimental receipt verified 8 files without Docker or Node.js on `PATH`. Evidence is in `.reprostamp/prd09-generate-live-qkdqy6/`. |
| `app benchmark --suite examples/app/evaluation.json --ollama-model qwen2.5-coder:3b --planner-model qwen2.5-coder:1.5b` with approval | The single-stage arm passed 0 of 2 and plan and review passed 1 of 2. The live suite recorded one incomplete trial due to a startup failure and two completed assertion failures. All four bundles verified with the same frozen harness digest. Evidence is in `.reprostamp/prd09-final-live-sOMXdS/`. The temporary Ollama server was stopped. |
| `docker inspect` on the live app and harness | Both ran as `pwuser` with read-only roots. The app used the `none` network and the harness joined its network namespace. Only the harness mounted writable evidence. |
| `python -m compileall -q src scripts tests`, `python -m pip check`, and `git diff --check` | Passed. |

The first presentation test ran after the lifecycle test had inserted a task. The harness now checks the empty state first. Early live planner responses exceeded the search-term or output limit. The final planner uses a bounded vocabulary and 128 output tokens within the shared 512-token attempt budget. Follow-up runs retained the planner failures and startup failures as separate evidence.

The local PRD-09 exit gate passed. Docker listed zero remaining ReproStamp workload containers. The hosted golden gate subsequently passed at the PRD-11 release revision. [Hosted golden gate](https://github.com/samsaturn007-git/ReproStamp/actions/runs/45440476886)

## PRD-10

Chose the workflow engine comparison on 24 November 2026. The PostgreSQL arm uses the current production queue and worker. The Temporal arm runs one opt-in activity against the same registered checkout and pinned Linux runner. PRD-03 recovery and the PRD-09 local exit gate had already passed. The architecture decision retains PostgreSQL for production. [PRD-10 specification](prds/PRD-10-workflow-recovery-comparison.md) · [Timings and decision](ADR-PRD10-workflow-engine.md)

| Command or check | Observed result |
| --- | --- |
| `python -m pip install -e '.[prd03]' -r experiments/prd10/requirements.txt` in a separate venv | Installed Temporal Python SDK 1.36.1 and passed `pip check`. The SDK's versioned download endpoint returned 404. The official CLI 1.8.3 GitHub release archive downloaded successfully and matched its published SHA-256. The CLI reported server 1.31.2. |
| `python -m experiments.prd10.benchmark --temporal-cli .reprostamp/prd10-tools/temporal --out .reprostamp/prd10-20261124-203431` | Both controls and all four crash trials completed. Each crash recovered on generation two. PostgreSQL recorded lease expiry and Temporal recorded an activity heartbeat timeout. Every trial accepted one receipt and handled a duplicate submission without starting a second job. |
| `env PATH=/usr/bin:/bin .venv/bin/reprostamp verify` on the six benchmark receipts and `reprostamp diff-receipts` on the first crash pair | All six bundles verified 13 files each. The diff reported matching inputs and case outcomes with the same `VERIFIED` verdict. |
| `docker ps -a --filter label=io.reprostamp.run` and PostgreSQL and process checks after the benchmark | Zero workload containers remained. The dedicated experiment database was dropped and the loopback Temporal server stopped. The run retains raw timings, receipts, worker logs, and recovery histories. |
| `.venv/bin/python tests/prd02_exit_gate.py` | Both three-browser fixture matrices, independent receipt replay, offline integrity checks, and missing or changed input diagnostics passed. Evidence is in `.reprostamp/prd02-gates-bwb0o6bm/`. |
| `.venv/bin/python tests/prd03_exit_gate.py` | Passed migration, duplicate submission, owner authorization, cancellation, exhausted recovery, and expiry. The replacement worker recovered frozen inputs and fenced stale writes. The dashboard resumed at event 3, recovered 36 ordered events, and downloaded one receipt and one trace. Evidence is in `.reprostamp/prd03-gates-hyy8jkc8/`. |
| `python -m compileall -q src scripts tests experiments/prd10` and `git diff --check` | Passed. |

The local PRD-10 exit gate passed. PostgreSQL reached the replacement app in 10.34–10.78 seconds and Temporal in 11.68–12.21 seconds on this two-crash sample per engine. [Raw benchmark results](../.reprostamp/prd10-20261124-203431/report.json)

## PRD-11

Started on 24 November 2026 after checking the recorded PRD-09 and PRD-10 local exit gates. The hosted workflows use Linux AMD64 and the maintained fixture provisioners. The production build uses a packaged CLI and control plane, a locked Python and npm dependency set, and the PostgreSQL queue. [Release requirements](prds/PRD-11-hosted-demo-release-baseline.md) · [Install and reproduce](HOSTED_RELEASE.md)

The first hosted comparison at `313cf0e0bbe1d2fc15ce19cd64d69875a3c3bb6f` completed all 12 checkout attempts with the expected assertion outcomes. Its receipt recorded `INCONCLUSIVE` because Node named the browser platform `linux/x64` and Docker named the runner platform `linux/amd64`. Browser report ingestion now maps the Node alias to Docker's platform name for functional tests, route reviews, and starter receipts. The initial bundle still verifies offline with its recorded verdict. [Initial hosted run](https://github.com/samsaturn007-git/ReproStamp/actions/runs/45439522482)

All release checks passed on 24 November 2026 at `9d901abc608496284590b2caf63d5d98c7d8f0b6` on Ubuntu 24.04 Linux AMD64. The remote annotated tag `hosted-demo-rc.1` resolves to that exact commit. [Release tag](https://github.com/samsaturn007-git/ReproStamp/tree/hosted-demo-rc.1) · [Hosted release checks](https://github.com/samsaturn007-git/ReproStamp/actions/runs/45440477070) · [Hosted starter checks](https://github.com/samsaturn007-git/ReproStamp/actions/runs/45440476886)

| Command or check | Observed result at the tagged commit |
| --- | --- |
| `./scripts/setup.sh --all-browsers`, `.venv/bin/python scripts/prepare-checkout.py`, and `.venv/bin/python scripts/prepare_fixture.py shipping` | Chromium `159.0.8154.6`, Firefox `159.0`, and WebKit `27.2` loaded loopback in the pinned runner. Both owned fixture repositories, independent harnesses, and npm caches were prepared. |
| `.venv/bin/python scripts/setup_prd03.py --release`, `.venv/bin/reprostamp --help`, `.venv/bin/python -m reprostamp.control migrate`, and `npm --prefix dashboard run build` | The wheel installed the CLI and control plane into `.venv` from a clean checkout. `pip check` passed. Compose started PostgreSQL `18.7`, migration reached `0004_route_reviews`, and OpenAPI generation, type checking, and the Next.js `16.4.6` production build passed. |
| `.venv/bin/python tests/prd02_exit_gate.py` | Checkout, shipping, and the independent checkout replay each returned `VERIFIED` after 12 attempts and 24 case executions. All five receipt corruption cases were rejected, the replay linked the source payload and matched its case outcomes, and changed or missing inputs produced the expected verdicts. |
| `node tools/runner-smoke/node_modules/@playwright/test/cli.js install --with-deps chromium` and `.venv/bin/python tests/prd03_exit_gate.py` | The replacement worker used frozen inputs, fenced stale writes, and published one receipt. The browser resumed from event 3, recovered 34 ordered events, and downloaded the receipt and trace. Cancellation, exhausted retry, owner authorization, and evidence expiry passed. |
| `python tests/prd08_exit_gate.py --mock-only --cache .reprostamp/ci-starter-cache` | All nine mock starter checks passed across the three browsers. Approval, invalid configuration, and offline receipt checks passed. |
| `python tests/prd09_exit_gate.py --cache .reprostamp/ci-starter-cache` | The golden benchmark passed 1 of 2 single-stage trials and 2 of 2 plan-and-review trials. The seeded incorrect presentation failed in all three browsers. The direct and extracted-source revalidation each passed all 12 checks with identical source hashes. The policy and context checks passed. |
| `gh run download` for the two hosted runs, followed by offline `verify_bundle` | All 11 downloaded receipts verified. The four comparison and dashboard receipts recorded completed runs with `VERIFIED` verdicts. The seven starter receipts recorded six passing validations and the intended seeded assertion failure. Each reported `linux/amd64`. Local copies are under `.reprostamp/prd11-hosted-9d901ab/`. |
| `.venv/bin/python tests/prd07_exit_gate.py` on the local ARM64 runner | The platform parsing change preserved all eight review scenarios, the dashboard walkthrough, and exact approval replay. Evidence is in `.reprostamp/prd07-gates-dff6w5xn/`. |
| `git ls-remote origin 'refs/tags/hosted-demo-rc.1*'` | GitHub returned the annotated tag and its target `9d901abc608496284590b2caf63d5d98c7d8f0b6`. |

The hosted build used Python `3.12.16`, Node.js `22.23.5`, npm `10.9.9`, Docker Engine `28.0.4`, and Compose `2.38.2`. The runner index is `sha256:1507cbfc550a63a6b7396791ca4f00df17beb56342d2447b3f106c306f525579`. Docker inspected the Linux AMD64 image ID as `sha256:12708c20bc005b7ecc920dd23b27079baa55359fd2739c7f0f3070c47cf263e9`.

| Dependency lock | SHA-256 recorded in hosted CI |
| --- | --- |
| `requirements/hosted-release.lock` | `71cc47d5e866001329260ac8cd05ee39d72b75838af82560fffc481cd9f0fb5f` |
| `dashboard/package-lock.json` | `32972297c10f199b3ec2137b04150a41fb6efc041489202c340decc60cc74f2a` |
| `tools/runner-smoke/package-lock.json` | `7acdc5ed3147105d0553bcf585c6f16a8d47b82f2662e0e355ed098543b7a45a` |

No PRD-11 exit checks remain open. The handoff gives the exact revision and commands for the next deployment. [Release handoff](HOSTED_RELEASE.md)

## Hosted demo roadmap

Planned on 24 November 2026. PRD-11 through PRD-14 define the sequence for a public HTTPS demo using the approved checkout fixture. Implementation starts with the hosted release gate.

| PRD | Exit check |
| --- | --- |
| [PRD-11](prds/PRD-11-hosted-demo-release-baseline.md) | Passed on `hosted-demo-rc.1`. |
| [PRD-12](prds/PRD-12-deploy-hosted-verifier.md) | Verify the hosted comparison and private owner access on an approved VM with DNS. |
| [PRD-13](prds/PRD-13-public-checkout-demo.md) | Verify an anonymous live sample, reviewed evidence, and durable submission limits. |
| [PRD-14](prds/PRD-14-github-and-demo-launch.md) | Verify the approved GitHub walkthrough, independent replay, recovery, and backup restore. |
