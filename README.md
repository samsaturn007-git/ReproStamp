# ReproStamp

ReproStamp compares two Git commits against the same independently maintained browser tests. The local CLI reproduces a bug on the base commit, verifies the candidate, and checks for regressions in Chromium, Firefox, and WebKit. Each comparison produces a Verification Receipt you can share, check offline, and replay.

## Local setup

Use Git, Python 3.12+, Node.js 22.12+ with npm, and a running local Docker engine for Linux containers. Run these commands from the repository root.

```sh
./scripts/setup.sh --all-browsers
.venv/bin/python scripts/prepare-checkout.py
```

Setup installs `reprostamp` in `.venv` and checks that all three engines can load a loopback page in the pinned Playwright image. The fixture script creates the same two Git commits on each run and prewarms the npm cache for the app and harness inside the pinned Linux image. Provisioning can download public packages and the image. Comparisons use the local cache and loopback-only networking. [Playwright Docker documentation](https://playwright.dev/docs/docker) · [Docker none network driver](https://docs.docker.com/engine/network/drivers/none/)

For the hosted demo, use the [release handoff](docs/HOSTED_RELEASE.md) to identify the tested revision and install it on Linux AMD64.

## Verify the checkout fix

```sh
checkout_out=".reprostamp/results/checkout-$(date +%Y%m%d-%H%M%S)"
.venv/bin/reprostamp compare \
  --repo .reprostamp/checkout/repo \
  --base checkout-base --head checkout-fixed \
  --profile profiles/checkout.json \
  --out "$checkout_out"
```

Use a fresh `--out` directory for each comparison. The CLI resolves both refs to commit SHAs and runs each commit twice per required engine. The base charges `$110.00` after applying `SAVE10`. The candidate charges `$90.00`, and both commits charge `$100.00` without a promo code. Open `receipt.md` in the output directory to inspect the browser matrix and follow the links to failure traces and screenshots. `result.json` contains structured attempt details.

| Exit code | Result |
| --- | --- |
| `0` | `VERIFIED` |
| `1` | `FAILED` |
| `2` | Invalid CLI usage, output directory, or receipt bundle |
| `3` | `INCONCLUSIVE` |
| `4` | `POLICY_BLOCKED` |

The [owner-managed profile](profiles/checkout.json) registers the repo, locked harness, npm cache, image digest, expected baseline assertion, required regressions, editable paths, attempt deadline, and browser settings. The supplied profiles use all three engines, an `1100 × 800` viewport, `en-US`, UTC, and seed `42` for page `Math.random()`. Profiles without an `engines` entry use Chromium. Keep the profile, harness, and output outside the application checkout. The runner copies committed files into fresh container storage and mounts evidence storage only in the harness container. The app and harness connect over loopback on port `4173`. Dependency lock edits, protected tests, symlinks, and submodules are blocked before either container starts.

## Verify and replay a receipt

```sh
bundle="$checkout_out/receipt.zip"
.venv/bin/reprostamp verify "$bundle"

replay_out=".reprostamp/results/replay-$(date +%Y%m%d-%H%M%S)"
.venv/bin/reprostamp replay "$bundle" \
  --repo .reprostamp/checkout/repo \
  --profile profiles/checkout.json \
  --out "$replay_out"

.venv/bin/reprostamp diff-receipts "$bundle" "$replay_out/receipt.zip"
```

Share `receipt.zip` to send the receipt and its approved logs, traces, and screenshots as one file. `verify` validates the schema, approved paths, payload hash, and every artifact hash offline. Check the reported payload SHA-256 against a digest received through a trusted channel when you need assurance of origin. A successful integrity check reports the recorded verification verdict separately. [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785)

To replay on another machine, run the setup and fixture commands there, copy the ZIP, and point `bundle` at the copy. Replay uses the recorded commit SHAs and matches the Git history identity, commit delta, dependency locks, frozen harness and oracle, effective profile, and locally available pinned Linux image and platform. Host directory paths can differ. The new receipt records the original payload hash. `diff-receipts` aligns engines, case IDs, sides, and attempt numbers and reports changes to those outcomes or to the conditions needed for a fair comparison.

## Onboard the shipping repository

The shipping fixture is a separate owned Git repository with its own profile, browser tests, and npm cache. After setup, provision it and run the same three-engine comparison. [Shipping profile](profiles/shipping.json) · [Shipping tests](harness/shipping/shipping.spec.cjs)

```sh
.venv/bin/python scripts/prepare_fixture.py shipping
shipping_out=".reprostamp/results/shipping-$(date +%Y%m%d-%H%M%S)"
.venv/bin/reprostamp compare \
  --repo .reprostamp/shipping/repo \
  --base shipping-base --head shipping-fixed \
  --profile profiles/shipping.json \
  --out "$shipping_out"
.venv/bin/reprostamp verify "$shipping_out/receipt.zip"
```

At exactly `$50.00`, the base shows a `$6.00` shipping fee and the candidate shows `$0.00`. Both charge `$6.00` at `$49.99`. The provisioner copies the owner-managed shipping test and shared runner files into a versioned harness snapshot outside the application repo.

For another approved repo, register its checkout, an independent Playwright harness, and a prewarmed npm cache in an owner-managed profile. Use the shipping profile and harness as examples. Set the expected case and assertion IDs, baseline value, required regressions, and editable application paths before comparing commits. Use the shared `test.cjs` fixture to apply the page seed and report the launched browser build. The test titles must match the case IDs in the profile.

## Run the exit checks

```sh
.venv/bin/python tests/prd01_exit_gate.py
.venv/bin/python tests/prd02_exit_gate.py
```

Provision both fixtures first. The checks cover runner cleanup, the browser matrices, modified and missing evidence, replay on a separate checkout, and input mismatch diagnostics. See the observed results in [implementation status](docs/IMPLEMENTATION_STATUS.md).

## Run the local dashboard

After [local setup](#local-setup), install the dashboard and start the pinned PostgreSQL service with Docker Compose.

```sh
.venv/bin/python scripts/setup_prd03.py
.venv/bin/python -m reprostamp.control migrate
```

Setup installs the API and dashboard dependencies, starts PostgreSQL, and regenerates the TypeScript client from the FastAPI OpenAPI schema. The migration applies the database tables and creates the owner password at `.reprostamp/prd03/owner-password`.

Run each command in a separate terminal from the repository root.

```sh
.venv/bin/python -m reprostamp.control serve
.venv/bin/python -m reprostamp.control worker
npm --prefix dashboard run dev
```

Open [the dashboard](http://127.0.0.1:3000), sign in with the owner password, and select **New run**. The checkout profile defaults to `checkout-base` and `checkout-fixed`. To use Shipping threshold, provision the [shipping fixture](#onboard-the-shipping-repository) first. The API is bound to loopback on port 8000 and publishes its [OpenAPI schema](http://127.0.0.1:8000/api/v1/openapi.json).

The dashboard shows browser attempts as they finish. A replacement worker recovers an expired lease using the original commits, profile, and browser harness. Download the receipt to verify it offline, or download an individual trace to open in a local Playwright Trace Viewer. Evidence expires 30 days after the run finishes. The timeline and case outcomes remain available.

PostgreSQL binds to `127.0.0.1:55432`. If the port is in use, set `REPROSTAMP_PG_PORT` for setup, migration, API, and worker. To stop PostgreSQL and preserve the workspace-scoped data volume, run `.venv/bin/python scripts/setup_prd03.py --stop`.

To register another approved checkout, set `REPROSTAMP_REGISTRY` for the API to point to an owner-managed JSON file. Use `repositories` and `profiles` objects keyed by ID. Each repository entry has a `label` and `path`. Each profile entry has a `label`, `path`, `repo_id`, and default `base` and `head` Git refs. Paths may be absolute or relative to the registry file. The browser submits the registered IDs and refs.

Run the PRD-03 exit check after local setup and checkout fixture preparation. The first command provisions a host Chromium for the dashboard test. Comparison workloads still run in the pinned Docker image.

```sh
node tools/runner-smoke/node_modules/@playwright/test/cli.js install chromium
.venv/bin/python tests/prd03_exit_gate.py
```

The exit check starts an isolated PostgreSQL database, API, worker, and dashboard. It captures a browser recording, downloads, and logs under `.reprostamp/`. [PRD-03 specification](docs/prds/PRD-03-dashboard-and-durable-runs.md)

## Run the GitHub pilot

Use one private, developer-owned repository with a local checkout and an owner-managed profile. Set `REPROSTAMP_REGISTRY` for the GitHub process and dashboard API to the registry that contains the approved checkout. Keep the independent harness, profile, npm cache, and App keys outside the application. Apply the schema with `.venv/bin/python -m reprostamp.control migrate` and start the dashboard and worker as above. The existing worker executes pilot and dashboard runs through the same queue.

Register a private GitHub App with **Contents** and **Pull requests** set to read, **Checks** set to read and write, and the **Pull request** event selected. Configure the webhook URL as an HTTPS endpoint ending in `/github/webhook`, enable TLS verification, and install the App only on the approved repository. Store the webhook secret and App PEM in owner-only files. [GitHub App registration](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app)

Create a GitHub configuration JSON file outside the application tree. These example numeric IDs stand for the App, its installation, and the approved GitHub repository. Relative credential paths resolve from the configuration file.

```json
{
  "app_id": 1234,
  "installation_id": 5678,
  "repository_id": 9012,
  "repository": "owner/checkout-fixture",
  "profile_id": "checkout-pilot",
  "dashboard_url": "http://127.0.0.1:3000",
  "webhook_secret_file": "webhook-secret",
  "private_key_file": "app.pem"
}
```

Run the integration with OpenSSL and Git installed. Terminate HTTPS at the endpoint that forwards the webhook to port 8001. The integration serves the webhook only. The dashboard link in the check is accessible to the local owner with a loopback dashboard origin.

```sh
REPROSTAMP_REGISTRY=/path/to/registry.json .venv/bin/python -m reprostamp.github --config /path/to/github.json
```

Open a same-repository pull request through the usual GitHub workflow. The ReproStamp check links to the evidence for the tested SHA. It reports `success` for `VERIFIED`, `failure` for `FAILED`, and `action_required` for `INCONCLUSIVE` or `POLICY_BLOCKED`. When refs move, the old check and dashboard label the evidence as superseded. View the check's details to inspect the immutable SHAs, attempts, and verdict reasons. Branch protection is opt-in.

To disconnect, disable the App webhook or suspend the repository installation and stop the integration. To recover, restart it with the same database and configuration. GitHub's App delivery history can redeliver missed events. The integration checks for an existing remote check before retrying a creation with an uncertain response. Its logs report queue time, total duration from browser attempts, worker retries, and publish failures. [GitHub webhook redelivery](https://docs.github.com/en/webhooks/testing-and-troubleshooting-webhooks/redelivering-webhooks)

Run `.venv/bin/python tests/prd04_pilot.py` for the local checks. It uses a local GitHub HTTP test server, a fresh PostgreSQL database, and the real pinned browser runner. [PRD-04 specification](docs/prds/PRD-04-github-pilot.md)

## Review a repair suggestion

Start with an intact receipt that reproduced the approved baseline assertion. The CLI reads the issue summary, the repeated baseline assertion from the receipt, and the source files you select from the receipt's base commit. Choose a fresh output directory outside the application checkout. This example uses a deterministic response with the known fix from the checkout fixture. [Checkout comparison](#verify-the-checkout-fix)

```sh
repair_dir=".reprostamp/repair-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$repair_dir"
printf '%s\n' 'SAVE10 should subtract $10 from the checkout total.' > "$repair_dir/issue.txt"
.venv/bin/python - "$repair_dir/response.json" <<'PY'
import json
import sys
from pathlib import Path

diff = Path("fixtures/checkout/fix.patch").read_text(encoding="utf-8")
Path(sys.argv[1]).write_text(json.dumps({"explanation": "Subtract the promo discount.", "diff": diff}), encoding="utf-8")
PY
```

Run the preview in Bash or Zsh and inspect its `context` and `instructions` fields. Repeat `--file` to select additional editable source files.

```bash
suggest_args=(
  --repo .reprostamp/checkout/repo --profile profiles/checkout.json
  --receipt "$checkout_out/receipt.zip" --issue-file "$repair_dir/issue.txt"
  --file src/checkout.ts --response-file "$repair_dir/response.json"
  --out "$repair_dir/proposal"
)
.venv/bin/reprostamp suggest "${suggest_args[@]}"
```

After reviewing the preview, copy its `approval_sha256` into the command below. The approval binds the context, provider, budgets, and output directory. An approved request makes one provider call. The output directory records the attempt and must be fresh for a new request. Set `--max-input-bytes` and `--max-output-bytes` to change the byte limits and `--max-output-tokens` to cap model generation.

```bash
.venv/bin/reprostamp suggest "${suggest_args[@]}" --approve PASTE_REVIEWED_APPROVAL_SHA256
```

Review `candidate.patch` and `suggestion.json`. ReproStamp checks that the applied changes affect only existing selected source files and exports a normalized Git diff from the recorded base SHA. To try the patch, start a branch or worktree at that SHA, apply the patch with `git apply`, review or edit the result, and commit it. Use `reprostamp compare` or **New run** in the dashboard with the approved base and your new commit SHA. The verification receipt identifies the commit executed by the independent browser runner.

To use a local model without an API key, start your Ollama server with `OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11434 ollama serve`. In a second terminal, download the model with `ollama pull qwen2.5-coder:1.5b`. Replace `--response-file "$repair_dir/response.json"` with `--ollama-model qwen2.5-coder:1.5b` before previewing and approving. The CLI sends the request over loopback and records the model's reported token counts. [Ollama local setup](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features)

For the optional OpenAI adapter, use `--openai-model MODEL` in place of `--response-file` and supply `OPENAI_API_KEY` to the CLI process. [OpenAI Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)

Run the exit checks with `.venv/bin/python tests/prd05_exit_gate.py "$checkout_out/receipt.zip"`. The suite reviews and commits two deterministic proposals, verifies each in three browsers, and checks the Ollama and OpenAI adapters with simulated responses. [PRD-05 specification](docs/prds/PRD-05-ai-repair-suggestions.md)

## Replay a failing case

Run `.venv/bin/python -m reprostamp.control migrate`, then open a finished comparison in the dashboard while its receipt is available. Expand a browser attempt under **Attempts**, then choose **Replay failing case** beside the case you want to investigate. ReproStamp runs that browser and case five times against the recorded commit and frozen profile, with a fresh app and harness workspace each time.

The replay shows each outcome, duration, and available trace. A mix of passing attempts and assertion failures is labeled **Suspected flaky** with its sample size. The replay links back to the original attempt and leaves its receipt and verification verdict intact. The original run also lists its case replays.

**Repository failure history** groups receipt-backed observations by case, assertion, and application stack location when captured. Each group shows when it first and last occurred, the affected browsers, and its receipts. Runner and dependency failures appear in their own section. Required cases still come from the owner-managed profile.

The shared reporter reads application locations from browser error stacks. If an approved harness captures a location separately, it can report a `reprostamp.application-location` annotation with a value such as `src/checkout.ts:17:33`.

Run `.venv/bin/python tests/prd06_exit_gate.py` after dashboard setup and host Chromium installation to exercise the labeled fixtures and dashboard. [PRD-06 specification](docs/prds/PRD-06-flake-and-failure-analysis.md) · [Observed classifications](docs/IMPLEMENTATION_STATUS.md#prd-06)

## Review visual and accessibility changes

Provision the independent review harness with `.venv/bin/python scripts/prepare_fixture.py checkout-review`. Use [the checkout review profile](profiles/checkout-review.json) with `reprostamp compare`, or register it for **New run** in the dashboard after running `.venv/bin/python -m reprostamp.control migrate`. Keep `review.cjs`, its locked dependencies, and route definitions in the owner-managed harness and profile.

```json
{
  "review": {
    "engine": "chromium",
    "routes": [
      { "id": "checkout", "path": "/", "ready": "main h1" },
      { "id": "confirmation", "path": "/confirmation", "ready": "#confirmation", "accessibility_required": true }
    ]
  }
}
```

Choose one of the profile's functional browsers and a unique visible readiness selector per route. The harness opens a fresh browser context for each route and uses the profile's seed, viewport, locale, and time zone. Captures use the fonts in the pinned Linux image and any local font assets loaded by the application. Each result requires two consistent observations per commit. [Playwright screenshot options](https://playwright.dev/docs/api/class-page#page-screenshot) · [axe-core scan results](https://github.com/dequelabs/axe-core/blob/develop/doc/API.md)

Open **Visual and accessibility review** in the run detail. Click the baseline, candidate, or pixel diff to inspect it at full size. Pink pixels mark differences. The axe table lists newly detected rule, impact, and target combinations. The receipt includes both check outcomes and all three screenshot files. Set `visual_required` or `accessibility_required` on a route to make an unapproved change or new axe finding fail verification. Missing required review evidence yields `INCONCLUSIVE`. Both checks are advisory by default.

Select **Approve candidate screenshot** to accept an intentional change. Approval history records the owner, time, source receipt, commit, effective profile, browser build, and screenshot SHA-256. Submit a new run to apply that approval. Both the original receipt and the original verdict remain historical records. A later commit or screenshot needs its own approval.

Run `.venv/bin/python tests/prd07_exit_gate.py` after preparing the checkout review harness, setting up the dashboard, and installing host Chromium. The pilot runs a keyboard walkthrough on `/review`. Press **Tab** to focus the promo input, type `SAVE10`, press **Tab** to reach **Apply**, and use **Shift+Tab** to confirm the reverse order. Tab back to **Apply** and press **Enter**. The walkthrough checks visible focus on both controls and the **Promo code applied** status message. [PRD-07 specification](docs/prds/PRD-07-visual-accessibility-review.md) · [Observed results](docs/IMPLEMENTATION_STATUS.md#prd-07)

## Generate and validate a task tracker

The starter uses one React and FastAPI template with SQLite. Title is always available. Choose `description`, `due_date`, and `priority` as optional fields, and specify two to five ordered status labels. The first label is the default for a new task. The last label marks a completed task. [Field Notes configuration](examples/starter/field-notes.json) · [Studio Requests configuration](examples/starter/studio-requests.json)

After installing ReproStamp, use a Linux Docker engine and run these commands from the repository root.

```sh
starter_cache=.reprostamp/starter-cache
starter_out=".reprostamp/starter-$(date +%Y%m%d-%H%M%S)"
.venv/bin/reprostamp starter prepare --cache "$starter_cache"
.venv/bin/reprostamp starter generate \
  --config examples/starter/field-notes.json \
  --cache "$starter_cache" --out "$starter_out"
.venv/bin/reprostamp starter verify "$starter_out/receipt.zip"
```

`source.zip` contains the complete starter, locked dependencies, and startup and rerun instructions. Extract it into a new directory. Its README starts the built frontend and API together on `127.0.0.1:4173`. The `starter_validation` receipt records API health, task CRUD, and the create-edit-complete journey for Chromium, Firefox, and WebKit. Its ZIP contains the source archive and checksums for all included evidence. Generation and validation exit `0` for passing checks, `1` for completed checks with an assertion failure, `2` for invalid inputs, and `3` for incomplete validation. Use the engine logs in the results directory to diagnose incomplete validation. `starter verify` checks the bundle offline and reports the recorded result separately.

To generate configuration from a description, preview a request, review its `context` and `instructions`, and rerun with the exact `approval_sha256`. The provider receives only that description and the template instructions. `configuration-request.json` records the provider and reported usage. The deterministic example below runs without a model service.

```bash
model_out="${starter_out}-description"
starter_args=(
  --description examples/starter/field-notes.txt
  --response-file examples/starter/field-notes.json
  --cache "$starter_cache" --out "$model_out"
)
.venv/bin/reprostamp starter generate "${starter_args[@]}"
.venv/bin/reprostamp starter generate "${starter_args[@]}" --approve PASTE_REVIEWED_APPROVAL_SHA256
```

For live inference, replace `--response-file` and its path with `--ollama-model MODEL` for an installed local model or `--openai-model MODEL` with `OPENAI_API_KEY` set. Start and configure the chosen service as in [Review a repair suggestion](#review-a-repair-suggestion). The generation and validation steps run with the same template for every provider. Dependency provisioning downloads public packages, and the app and independent acceptance suite then run with loopback-only networking.

Run `.venv/bin/python tests/prd08_exit_gate.py --cache "$starter_cache"` to validate both configurations and rerun the tests from the extracted source. The `--mock-only` mode runs the checked-in deterministic example in CI. [PRD-08 specification](docs/prds/PRD-08-verified-app-starter.md)

## Generate a task tracker with a bounded patch

The app generator extends the React, TypeScript, FastAPI, and SQLite starter with a list heading, empty-state message, and one of three palettes. It produces the same source archive for the same plan and template. The export includes the dependency locks, supported preview and commands in `app-manifest.json`, a license, unit tests, and a README. Validation runs the build, TypeScript, Python unit and lint checks, and the independent browser suite inside the pinned Linux runner. [Example plan](examples/app/field-notes.json)

```sh
app_cache=.reprostamp/app-cache
app_out=".reprostamp/app-$(date +%Y%m%d-%H%M%S)"
.venv/bin/reprostamp starter prepare --cache "$app_cache"
.venv/bin/reprostamp app generate --plan examples/app/field-notes.json --cache "$app_cache" --out "$app_out"
.venv/bin/reprostamp starter verify "$app_out/receipt.zip"
```

Extract `source.zip` into a fresh directory and follow its README to start the app locally. To rerun the independent checks, run `reprostamp app validate --source . --cache /path/to/app-cache --out ../app-rerun` from the extracted directory. Revalidation checks that the maintained source and locks match the generated plan. Screenshots, traces, and Playwright tests stay outside the export.

To generate a plan with local Ollama, run the first command to inspect the request and the second command with the approval digest. The live receipt labels the result **experimental**. The generator writes only the typed application settings and can use reviewed diagnostics passed with `--failure` when choosing which template excerpts to include.

```bash
app_args=(
  app generate --requirements examples/app/field-notes.txt
  --ollama-model qwen2.5-coder:3b --cache "$app_cache" --out "${app_out}-live"
)
.venv/bin/reprostamp "${app_args[@]}"
.venv/bin/reprostamp "${app_args[@]}" --approve PASTE_REVIEWED_APPROVAL_SHA256
```

### Run the paired evaluation

The seeded suite gives both workflows the same requirements and grades the outputs against independent expected settings and browser checks. It records attempts, timings, provider usage, context bytes, and failure modes. The deterministic run uses scripted provider responses. Add `--ollama-model qwen2.5-coder:3b --planner-model qwen2.5-coder:1.5b` to preview a live run, then repeat that command with its approval digest. [Fixture suite](examples/app/evaluation.json) · [Evaluation results](docs/PRD09_EVALUATION.md)

```sh
.venv/bin/reprostamp app benchmark --suite examples/app/evaluation.json \
  --cache "$app_cache" --out "${app_out}-benchmark"
.venv/bin/python tests/prd09_exit_gate.py --cache "$app_cache"
```

[PRD-09 specification](docs/prds/PRD-09-bounded-app-generation-and-evaluation.md)

## Compare worker recovery

The optional workflow experiment pairs the production PostgreSQL worker with a local Temporal activity. Each runs the same independently maintained Chromium checkout comparison. The experiment records one control and two worker crashes per engine, then verifies the receipts offline. [PRD-10 specification](docs/prds/PRD-10-workflow-recovery-comparison.md) · [Results and architecture decision](docs/ADR-PRD10-workflow-engine.md)

Use the prepared checkout fixture, the local dashboard PostgreSQL service, and the Temporal CLI 1.8.3 binary for your host. Verify the downloaded archive against the release's checksums. [Checkout setup](#local-setup) · [PostgreSQL setup](#run-the-local-dashboard) · [Temporal CLI 1.8.3 release](https://github.com/temporalio/cli/releases/tag/v1.8.3)

```sh
python3 -m venv .reprostamp/prd10-venv
.reprostamp/prd10-venv/bin/python -m pip install -e '.[prd03]' -r experiments/prd10/requirements.txt
.reprostamp/prd10-venv/bin/python -m experiments.prd10.benchmark \
  --temporal-cli /path/to/temporal \
  --out ".reprostamp/prd10-$(date +%Y%m%d-%H%M%S)"
```

The benchmark uses an isolated database on the local ReproStamp PostgreSQL service and an ephemeral Temporal dev server on loopback. It only submits the approved checkout fixture. The fresh output directory contains the measured timings, worker logs, PostgreSQL events, Temporal histories, and receipts.

[Product plan](docs/PRODUCT_PLAN.md) · [Original PRD pack](docs/reference/original_prd_pack/README.md)
