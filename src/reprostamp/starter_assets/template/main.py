"""Local FastAPI task service for the maintained starter template."""

import json
import os
import sqlite3
from contextlib import asynccontextmanager, closing
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "starter.json").read_text(encoding="utf-8"))
DATABASE = Path(os.environ.get("TASK_DB_PATH", ROOT / "tasks.sqlite3"))


class TaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=120)
    status: str | None = None
    description: str = Field(default="", max_length=2000)
    due_date: date | None = None
    priority: Literal["Low", "Normal", "High"] = "Normal"


@asynccontextmanager
async def lifespan(app: FastAPI):
    with closing(sqlite3.connect(DATABASE)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)")
    yield


app = FastAPI(title=CONFIG["project_name"], lifespan=lifespan)


def task_data(task: TaskInput) -> dict:
    enabled = set(CONFIG["task_fields"])
    if blocked := (task.model_fields_set - {"title", "status"} - enabled):
        raise HTTPException(422, f"Fields disabled for this project: {', '.join(sorted(blocked))}.")
    data = task.model_dump(mode="json", include=enabled | {"title", "status"})
    data["status"] = CONFIG["statuses"][0] if task.status is None else task.status
    if data["status"] not in CONFIG["statuses"]:
        raise HTTPException(422, "Choose one of this project's status labels.")
    return data


def result(row: tuple) -> dict:
    task_id, data = row
    return {"id": task_id, **json.loads(data)}


@app.get("/api/health")
def health():
    with closing(sqlite3.connect(DATABASE)) as db:
        db.execute("SELECT id FROM tasks LIMIT 1").fetchone()
    return {"status": "ok"}


@app.get("/api/tasks")
def list_tasks():
    with closing(sqlite3.connect(DATABASE)) as db:
        return [result(row) for row in db.execute("SELECT id, data FROM tasks ORDER BY id DESC")]


@app.post("/api/tasks", status_code=201)
def create_task(task: TaskInput):
    data = task_data(task)
    with closing(sqlite3.connect(DATABASE)) as db, db:
        created = db.execute("INSERT INTO tasks (data) VALUES (?)", (json.dumps(data),))
        return {"id": created.lastrowid, **data}


@app.get("/api/tasks/{task_id}")
def read_task(task_id: int):
    with closing(sqlite3.connect(DATABASE)) as db:
        row = db.execute("SELECT id, data FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Task not found.")
    return result(row)


@app.put("/api/tasks/{task_id}")
def update_task(task_id: int, task: TaskInput):
    data = task_data(task)
    with closing(sqlite3.connect(DATABASE)) as db, db:
        changed = db.execute("UPDATE tasks SET data = ? WHERE id = ?", (json.dumps(data), task_id))
        if not changed.rowcount:
            raise HTTPException(404, "Task not found.")
    return {"id": task_id, **data}


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: int):
    with closing(sqlite3.connect(DATABASE)) as db, db:
        changed = db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if not changed.rowcount:
            raise HTTPException(404, "Task not found.")
    return Response(status_code=204)


app.mount("/", StaticFiles(directory=ROOT / "dist", html=True), name="frontend")
