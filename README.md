# BuildVerify AI

BuildVerify AI compares two Git commits against the same independently maintained browser tests. PRD-01 starts with a local CLI that reproduces a checkout bug on the base commit, verifies the fix on the candidate, and checks for regressions in Chromium.

## Local setup

Use Git, Python 3.12+, Node.js 22.12+ with npm, and a running local Docker engine for Linux containers. Run the setup script from the repository root.

```sh
./scripts/setup.sh
```

The script creates or reuses `.venv`, installs the locked Playwright smoke-test dependencies, and pulls the pinned browser image if it is missing. npm and the image registry serve the initial setup. The smoke test runs in Docker with loopback-only networking and checks that headless Chromium can load a local page.

The smoke test checks the local toolchain. PRD-01 defines the checkout fixture, the `bverify compare` command, and the verifier's runner and exit gates.

## Start PRD-01

Open [PRD-01](docs/prds/PRD-01-verification-cli.md) with the [product plan](docs/PRODUCT_PLAN.md) and [implementation status](docs/IMPLEMENTATION_STATUS.md). Paste this prompt into Codex.

> Implement only PRD-01. Inspect the current workspace and follow the shared BuildVerify decisions. Work through the numbered steps, run the exit-gate checks, and record commands, actual results, and blocked checks in `docs/IMPLEMENTATION_STATUS.md`. Stop at the PRD-01 exit gate and report which criteria passed.

The [product plan](docs/PRODUCT_PLAN.md) lists all eight PRDs and their dependencies. The [original PRD pack](docs/reference/buildverify_prd_pack/README.md) is retained for reference.
