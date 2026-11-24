# Hosted demo release handoff

The release record identifies the annotated tag, full commit SHA, and GitHub Actions results for the approved revision. Use that SHA for installation and for any later deployment. [PRD-11 release record](IMPLEMENTATION_STATUS.md#prd-11)

## Install the tested revision

Use a fresh Linux AMD64 checkout. CI uses Ubuntu 24.04, Python 3.12.16 with `venv`, and Node.js 22.23.5 with npm. Install Git, Bash, and a running native Linux AMD64 Docker Engine with the Docker Compose plugin. The operator needs Docker access. The local Compose service uses PostgreSQL 18.7 and binds to `127.0.0.1:55432`. Provisioning needs access to PyPI, npm, the Microsoft Container Registry, and Docker Hub.

Replace `APPROVED_TAG` and `APPROVED_SHA` with the release record's values. `git show --no-patch APPROVED_TAG` displays the tag annotation and the commit it names. Run the setup and build from the new checkout's root.

```sh
git clone https://github.com/samsaturn007-git/ReproStamp.git reprostamp-release
cd reprostamp-release
git checkout --detach 'APPROVED_TAG'
test "$(git rev-parse HEAD)" = 'APPROVED_SHA' || exit 1

./scripts/setup.sh --all-browsers
.venv/bin/python scripts/prepare-checkout.py
.venv/bin/python scripts/prepare_fixture.py shipping
.venv/bin/python scripts/setup_prd03.py --release
.venv/bin/python -m reprostamp.control migrate
NEXT_TELEMETRY_DISABLED=1 npm --prefix dashboard run build
```

`setup_prd03.py --release` installs the packaged CLI and control plane into `.venv`, installs the dashboard from its npm lockfile, and generates its client from the installed API. Release builds use the production PostgreSQL queue. The app fixtures, independent harnesses, and prewarmed caches remain separate. The app and harness workloads use the pinned Playwright image and run with loopback-only networking.

The [Python release lock](../requirements/hosted-release.lock) covers the control plane and wheel build tools. The [dashboard lock](../dashboard/package-lock.json) and [smoke test lock](../tools/runner-smoke/package-lock.json) pin the host JavaScript dependencies. The [checkout app lock](../fixtures/checkout/app/package-lock.json), [comparison harness lock](../harness/checkout/package-lock.json), and starter's [npm lock](../src/reprostamp/starter_assets/template/package-lock.json) and [Python lock](../src/reprostamp/starter_assets/template/requirements.lock) govern the isolated workloads.

The [Playwright image](../tools/runner-smoke/image.txt) is pinned to index digest `sha256:1507cbfc550a63a6b7396791ca4f00df17beb56342d2447b3f106c306f525579`. Its Linux AMD64 manifest is `sha256:766137e2d9caad4744187e53cdc89320ba6f2eb57cff097374020944b44dd0a9`. [PostgreSQL image pin](../compose.prd03.yml)

## Reproduce the release gates

Run these commands from the installed checkout. Host Chromium and its Ubuntu system dependencies power the dashboard acceptance test. That Playwright install step can use `sudo` to install system packages and needs access to the Playwright download servers and Ubuntu repositories.

```sh
.venv/bin/python tests/prd02_exit_gate.py
node tools/runner-smoke/node_modules/@playwright/test/cli.js install --with-deps chromium
.venv/bin/python tests/prd03_exit_gate.py
.venv/bin/python tests/prd08_exit_gate.py --mock-only --cache .reprostamp/ci-starter-cache
.venv/bin/python tests/prd09_exit_gate.py --cache .reprostamp/ci-starter-cache
```

CI records the checkout SHA, dependency lock hashes, installed Python versions, and actual Docker image ID. The run artifacts contain the approved fixture receipts, dashboard recovery evidence, and deterministic starter results. [Hosted release workflow](../.github/workflows/hosted-release.yml) · [Starter workflow](../.github/workflows/starter.yml)
