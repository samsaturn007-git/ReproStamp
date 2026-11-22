# ReproStamp

ReproStamp compares two Git commits against the same independently maintained browser tests. The local CLI reproduces a bug on the base commit, verifies the candidate, and checks for regressions in Chromium, Firefox, and WebKit. Each comparison produces a Verification Receipt you can share, check offline, and replay.

## Local setup

Use Git, Python 3.12+, Node.js 22.12+ with npm, and a running local Docker engine for Linux containers. Run these commands from the repository root.

```sh
./scripts/setup.sh --all-browsers
.venv/bin/python scripts/prepare-checkout.py
```

Setup installs `reprostamp` in `.venv` and checks that all three engines can load a loopback page in the pinned Playwright image. The fixture script creates the same two Git commits on each run and prewarms the npm cache for the app and harness inside the pinned Linux image. Provisioning can download public packages and the image. Comparisons use the local cache and loopback-only networking. [Playwright Docker documentation](https://playwright.dev/docs/docker) · [Docker none network driver](https://docs.docker.com/engine/network/drivers/none/)

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

The [product plan](docs/PRODUCT_PLAN.md) lists all eight PRDs and their dependencies. The [original PRD pack](docs/reference/original_prd_pack/README.md) is retained for reference.
