#!/usr/bin/env bash
set -euo pipefail

smoke_browser=chromium
if [[ $# -eq 1 && ${1:-} == --all-browsers ]]; then
  smoke_browser=all
elif [[ $# -ne 0 ]]; then
  printf 'Usage: %s [--all-browsers]\n' "${0##*/}" >&2
  exit 2
fi

root_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
smoke_dir="$root_dir/tools/runner-smoke"
venv_dir="$root_dir/.venv"
image="$(cat "$smoke_dir/image.txt")"

for program in git python3 node npm docker; do
  if ! command -v "$program" >/dev/null; then
    printf 'Missing required command %s.\n' "$program" >&2
    exit 1
  fi
done

git --version
if [ ! -x "$venv_dir/bin/python" ]; then
  python3 -c 'import sys; sys.exit("Python 3.12 or newer is required." if sys.version_info < (3, 12) else 0)'
  python3 -m venv "$venv_dir"
fi
"$venv_dir/bin/python" -c 'import sys; sys.exit("Recreate .venv with Python 3.12 or newer." if sys.version_info < (3, 12) else 0)'
"$venv_dir/bin/python" --version
"$venv_dir/bin/python" -m pip --version
node -e 'const [major, minor] = process.versions.node.split(".").map(Number); if (major < 22 || (major === 22 && minor < 12)) { console.error("Node.js 22.12 or newer is required."); process.exit(1); }'
node --version
npm --version
docker info --format 'Docker server {{.ServerVersion}} ({{.OSType}}/{{.Architecture}})'

if ! docker image inspect "$image" >/dev/null 2>&1; then
  docker pull "$image"
fi

npm --prefix "$smoke_dir" ci --prefer-offline --ignore-scripts --no-audit --no-fund --include=dev

docker run --rm --init --pull=never --network=none --user=pwuser --env=HOME=/tmp \
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=256m --shm-size=256m \
  --cap-drop=ALL --security-opt=no-new-privileges \
  --cpus=2 --memory=1g --pids-limit=256 \
  --mount "type=bind,source=$smoke_dir,target=/smoke,readonly" \
  --workdir /smoke "$image" \
  node node_modules/@playwright/test/cli.js test browsers.spec.cjs \
    --browser="$smoke_browser" --workers=1 --timeout=20000 --reporter=list --output=/tmp/test-results

"$venv_dir/bin/python" -m pip install --disable-pip-version-check -e "$root_dir"
