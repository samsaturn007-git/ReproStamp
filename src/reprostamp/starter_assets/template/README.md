# Task tracker starter

`starter.json` sets the project name, optional task fields, and status labels. New tasks use the first status. Completing a task sets the last status. Both React and FastAPI read this configuration.

## Start locally

Use Python 3.12+ and Node.js 22.12+ with npm. From the extracted source directory, run these commands in a POSIX shell.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r requirements.lock
npm ci --ignore-scripts --no-audit --no-fund
npm run build
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 4173
```

Open [the task tracker](http://127.0.0.1:4173) or [the API explorer](http://127.0.0.1:4173/docs). The app serves the built frontend and API from the same loopback origin. SQLite stores tasks in `tasks.sqlite3` beside the source. To choose another database file, set `TASK_DB_PATH` when starting Uvicorn. Rebuild after editing the frontend or configuration. This starter is for local single-user development.

## Rerun validation

With ReproStamp installed and Docker running Linux containers, run the following from the extracted source directory. Use a new results directory on each run.

```sh
reprostamp starter prepare --cache ../starter-cache
reprostamp starter validate --source . --cache ../starter-cache --out ../starter-rerun
reprostamp starter verify ../starter-rerun/receipt.zip
```

The independent ReproStamp harness checks API health and task CRUD, then creates, edits, and completes a task in Chromium, Firefox, and WebKit. Its receipt records which checks ran, their outcomes, browser builds, and the source archive digest. Dependency provisioning uses the public package registries. Validation runs offline in disposable containers.
