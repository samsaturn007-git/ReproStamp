# BuildVerify AI

BuildVerify AI compares two Git commits against the same independently maintained browser tests. The local CLI reproduces a checkout discount bug on the base commit, verifies the fix on the candidate, and checks ordinary checkout in Chromium.

## Local setup

Use Git, Python 3.12+, Node.js 22.12+ with npm, and a running local Docker engine for Linux containers. Run these commands from the repository root.

```sh
./scripts/setup.sh
.venv/bin/python scripts/prepare-checkout.py
```

Setup installs `bverify` in `.venv` and confirms that the pinned Playwright image can run Chromium. The fixture script creates the same two Git commits on each run and prewarms a dedicated npm cache for the app and harness inside the pinned Linux image. Provisioning can download public packages and the image. Comparisons use the local cache and loopback-only networking. [Playwright Docker documentation](https://playwright.dev/docs/docker) · [Docker none network driver](https://docs.docker.com/engine/network/drivers/none/)

## Verify the checkout fix

```sh
.venv/bin/bverify compare \
  --repo .buildverify/checkout/repo \
  --base checkout-base --head checkout-fixed \
  --profile profiles/checkout.json \
  --out ".buildverify/results/checkout-$(date +%Y%m%d-%H%M%S)"
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

The [product plan](docs/PRODUCT_PLAN.md) lists all eight PRDs and their dependencies. The [original PRD pack](docs/reference/buildverify_prd_pack/README.md) is retained for reference.
