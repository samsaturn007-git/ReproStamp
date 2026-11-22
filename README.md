# ReproStamp

ReproStamp compares two Git commits against the same independently maintained browser tests. The local CLI reproduces a checkout discount bug on the base commit, verifies the fix on the candidate, and checks ordinary checkout in Chromium.

## Local setup

Use Git, Python 3.12+, Node.js 22.12+ with npm, and a running local Docker engine for Linux containers. Run these commands from the repository root.

```sh
./scripts/setup.sh
.venv/bin/python scripts/prepare-checkout.py
```

Setup installs `reprostamp` in `.venv` and checks that Chromium can load a loopback page in the pinned Playwright image. The fixture script creates the same two Git commits on each run and prewarms a dedicated npm cache for the app and harness inside the pinned Linux image. Provisioning can download public packages and the image. Comparisons use the local cache and loopback-only networking. [Playwright Docker documentation](https://playwright.dev/docs/docker) · [Docker none network driver](https://docs.docker.com/engine/network/drivers/none/)

## Verify the checkout fix

```sh
.venv/bin/reprostamp compare \
  --repo .reprostamp/checkout/repo \
  --base checkout-base --head checkout-fixed \
  --profile profiles/checkout.json \
  --out ".reprostamp/results/checkout-$(date +%Y%m%d-%H%M%S)"
```

Use a fresh `--out` directory for each comparison. The CLI resolves both refs to commit SHAs and runs each commit twice. In the fixture, the base applies `SAVE10` and charges `$110.00` instead of `$90.00`. The candidate charges `$90.00`, and both commits still charge `$100.00` without a promo code. Open `result.json` in the output directory for case outcomes and relative paths to the failure screenshots, Playwright traces, and attempt logs.

| Exit code | Result |
| --- | --- |
| `0` | `VERIFIED` |
| `1` | `FAILED` |
| `2` | Invalid CLI usage or output directory |
| `3` | `INCONCLUSIVE` |
| `4` | `POLICY_BLOCKED` |

The [owner-managed profile](profiles/checkout.json) registers the repo path, locked harness, npm cache, image digest, expected assertion and baseline value, regression case IDs, editable globs rooted at `src/`, and attempt deadline. Put the profile and harness outside the application checkout. The runner copies committed files into fresh container storage and mounts evidence storage only in the harness container. The app and harness connect over loopback on port `4173`. Dependency lock edits, protected tests, symlinks, and submodules are blocked before either container starts.

## Run the PRD-01 exit checks

```sh
.venv/bin/python tests/prd01_exit_gate.py
```

The checks exercise the real fixture, assert the verdicts and exit codes, validate failure artifacts, and confirm that the attempt containers and temporary workspace are removed. See the recorded results in [implementation status](docs/IMPLEMENTATION_STATUS.md).

## Prepare the second repo for PRD-02

Run setup with `--all-browsers` to smoke-test Chromium, Firefox, and WebKit. The shipping fixture is a separate owned Git repository with its own profile, browser tests, and npm cache. Run its Chromium comparison as an onboarding check before implementing the browser matrix. [Shipping profile](profiles/shipping.json) · [Shipping tests](harness/shipping/shipping.spec.cjs)

```sh
./scripts/setup.sh --all-browsers
.venv/bin/python scripts/prepare_fixture.py shipping
.venv/bin/reprostamp compare \
  --repo .reprostamp/shipping/repo \
  --base shipping-base --head shipping-fixed \
  --profile profiles/shipping.json \
  --out ".reprostamp/results/shipping-$(date +%Y%m%d-%H%M%S)"
```

At exactly `$50.00`, the base shows a `$6.00` shipping fee and the candidate shows `$0.00`. Both charge `$6.00` at `$49.99`. The provisioner copies the owner-managed shipping test and shared runner files into a versioned harness snapshot outside the application repo.

The [PRD-02 specification](docs/prds/PRD-02-receipt-and-replay.md) covers the browser matrix, Verification Receipt, and offline commands. See [implementation status](docs/IMPLEMENTATION_STATUS.md) for the setup results and exit-gate requirements.

The [product plan](docs/PRODUCT_PLAN.md) lists all eight PRDs and their dependencies. The [original PRD pack](docs/reference/original_prd_pack/README.md) is retained for reference.
