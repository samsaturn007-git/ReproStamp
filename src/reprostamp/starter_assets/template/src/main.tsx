import { useEffect, useState, type FormEvent } from "react";
import { createRoot } from "react-dom/client";
import config from "../starter.json";
import "./style.css";

type Details = {
  title: string;
  status: string;
  description?: string;
  due_date?: string | null;
  priority?: string;
};
type Task = Details & { id: number };

const [firstStatus] = config.statuses;
const completeStatus = config.statuses[config.statuses.length - 1];
const fields = new Set(config.task_fields);
const blankTask = (): Details => ({ title: "", status: firstStatus });

async function tasksRequest<T>(path = "", method = "GET", body?: Details): Promise<T> {
  const response = await fetch(`/api/tasks${path}`, {
    method,
    ...(body && { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  });
  if (!response.ok) throw new Error(`The task service returned HTTP ${response.status}.`);
  return response.status === 204 ? (undefined as T) : response.json();
}

function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [draft, setDraft] = useState<Details>(blankTask);
  const [editing, setEditing] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    tasksRequest<Task[]>().then(setTasks)
      .catch(() => setError("Could not load tasks. Refresh to try again."))
      .finally(() => setBusy(false));
  }, []);

  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not save changes. Try again.");
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setEditing(null);
    setDraft(blankTask());
  }

  function edit({ id, ...details }: Task) {
    setEditing(id);
    setDraft(details);
    document.getElementById("task-title")?.focus();
  }

  function save(event: FormEvent) {
    event.preventDefault();
    if (!draft.title.trim()) return;
    void perform(async () => {
      const updating = editing !== null;
      const saved = await tasksRequest<Task>(updating ? `/${editing}` : "", updating ? "PUT" : "POST", draft);
      setTasks(current => updating ? current.map(task => task.id === saved.id ? saved : task) : [saved, ...current]);
      reset();
      setMessage(updating ? "Task updated." : "Task added.");
    });
  }

  function complete({ id, ...details }: Task) {
    void perform(async () => {
      const saved = await tasksRequest<Task>(`/${id}`, "PUT", { ...details, status: completeStatus });
      setTasks(current => current.map(task => task.id === saved.id ? saved : task));
      if (id === editing) setDraft(current => ({ ...current, status: saved.status }));
      setMessage("Task completed.");
    });
  }

  function remove(id: number) {
    void perform(async () => {
      await tasksRequest<void>(`/${id}`, "DELETE");
      setTasks(current => current.filter(task => task.id !== id));
      if (id === editing) reset();
      setMessage("Task deleted.");
    });
  }

  return (
    <>
      <header className="masthead"><div className="frame"><h1>{config.project_name}</h1></div></header>
      <main className="frame layout">
        <section className="editor" aria-labelledby="editor-title">
          <h2 id="editor-title">{editing === null ? "New task" : "Edit task"}</h2>
          <form onSubmit={save}>
            <fieldset disabled={busy}>
              <label>Task title
                <input id="task-title" required maxLength={120} value={draft.title}
                  onChange={event => setDraft({ ...draft, title: event.target.value })} />
              </label>
              {fields.has("description") && <label>Description
                <textarea value={draft.description ?? ""} maxLength={2000}
                  onChange={event => setDraft({ ...draft, description: event.target.value })} />
              </label>}
              {fields.has("due_date") && <label>Due date
                <input type="date" value={draft.due_date ?? ""}
                  onChange={event => setDraft({ ...draft, due_date: event.target.value || null })} />
              </label>}
              {fields.has("priority") && <div className="control">
                <label htmlFor="task-priority">Priority</label>
                <select id="task-priority" value={draft.priority ?? "Normal"}
                  onChange={event => setDraft({ ...draft, priority: event.target.value })}>
                  <option>Low</option><option>Normal</option><option>High</option>
                </select>
              </div>}
              <div className="control">
                <label htmlFor="task-status">Status</label>
                <select id="task-status" value={draft.status} onChange={event => setDraft({ ...draft, status: event.target.value })}>
                  {config.statuses.map(status => <option key={status}>{status}</option>)}
                </select>
              </div>
              <div className="actions">
                <button className="primary" type="submit">{editing === null ? "Add task" : "Save changes"}</button>
                {editing !== null && <button type="button" onClick={reset}>Cancel</button>}
              </div>
            </fieldset>
          </form>
          <p className="feedback" role="status">{message}</p>
          {error && <p className="error" role="alert">{error}</p>}
        </section>
        <section aria-labelledby="tasks-title">
          <div className="list-heading">
            <h2 id="tasks-title">Tasks</h2>
            <span>{tasks.length} {tasks.length === 1 ? "task" : "tasks"}</span>
          </div>
          {tasks.length === 0 && <p className="empty">{busy ? "Loading tasks…" : "No tasks yet."}</p>}
          <ul className="tasks">
            {tasks.map(task => (
              <li key={task.id} className="task">
                <div className="task-heading">
                  <h3>{task.title}</h3>
                  <span className={task.status === completeStatus ? "status complete" : "status"}>{task.status}</span>
                </div>
                {task.description && <p className="description">{task.description}</p>}
                {(task.due_date || task.priority) && <p className="details">
                  {task.due_date && <span>Due <time dateTime={task.due_date}>{task.due_date}</time></span>}
                  {task.priority && <span>{task.priority} priority</span>}
                </p>}
                <div className="actions">
                  {task.status !== completeStatus && <button disabled={busy} onClick={() => complete(task)}>Complete</button>}
                  <button disabled={busy} onClick={() => edit(task)}>Edit</button>
                  <button disabled={busy} className="delete" onClick={() => remove(task.id)}>Delete</button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </>
  );
}

document.title = config.project_name;
createRoot(document.getElementById("root")!).render(<App />);
