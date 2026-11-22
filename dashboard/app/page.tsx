"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, errorMessage, writeHeaders, type Schema } from "../lib/client";
import { RunReview, Badge, when } from "./review";

type Run = Schema["RunSummary"];
type Registry = Schema["Registry"];

export default function Dashboard() {
  const [csrf, setCsrf] = useState<string | null>();
  const [registry, setRegistry] = useState<Registry>();
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    setSelected(new URLSearchParams(window.location.search).get("run") ?? "");
    api.GET("/api/v1/session").then(({ data }) => setCsrf(data?.csrf_token ?? null)).catch(() => {
      setError("The local API is unavailable.");
      setCsrf(null);
    });
  }, []);

  useEffect(() => {
    if (!csrf) return;
    const controller = new AbortController();
    Promise.all([
      api.GET("/api/v1/registry", { signal: controller.signal }),
      api.GET("/api/v1/runs", { signal: controller.signal }),
    ]).then(([register, history]) => {
      if (!register.data || !history.data) throw new Error("Unable to load the local run history.");
      setRegistry(register.data);
      setRuns(history.data);
      setShowForm(history.data.length === 0);
    }).catch((failure) => { if (!controller.signal.aborted) setError(failure.message); });
    return () => controller.abort();
  }, [csrf]);

  function choose(id: string) {
    setSelected(id);
    const url = new URL(window.location.href);
    url.searchParams.set("run", id);
    window.history.replaceState(null, "", url);
  }

  function refreshItem(run: Run) {
    setRuns((current) => {
      if (!current.some((item) => item.id === run.id)) return [run, ...current];
      return current.map((item) => item.id === run.id ? run : item);
    });
  }

  async function signOut() {
    try {
      const { response } = await api.DELETE("/api/v1/session", { params: { header: writeHeaders(csrf!) } });
      if (!response.ok && response.status !== 401) throw new Error();
      setCsrf(null);
      setRegistry(undefined);
      setRuns([]);
      setError("");
    } catch { setError("Could not sign out. Try again."); }
  }

  return (
    <>
      <header className="topbar">
        <div className="brand"><span className="stamp" aria-hidden="true">R</span>ReproStamp</div>
        {csrf && <button className="quiet" onClick={signOut}>Sign out</button>}
      </header>
      {csrf === undefined ? <main className="login"><p role="status">Connecting to ReproStamp…</p></main> :
        !csrf ? <SignIn error={error} onError={setError} onSession={setCsrf} /> :
        <main className="shell">
          <aside className="sidebar" aria-label="Run history">
            <div className="sidebar-head">
              <h2>Runs</h2>
              <button className="primary compact" onClick={() => setShowForm(true)}>New run</button>
            </div>
            {runs.length === 0 && <p className="muted sidebar-empty">No verification runs yet.</p>}
            <ul className="run-list">
              {runs.map((run) => (
                <li key={run.id}>
                  <button className="run-link" aria-current={selected === run.id ? "true" : undefined}
                    onClick={() => { choose(run.id); setShowForm(false); }}>
                    <strong>{registry?.repositories.find((repo) => repo.id === run.request.repo_id)?.label ?? run.request.repo_id}</strong>
                    <span className="run-link-refs">{run.request.base_ref} → {run.request.head_ref}</span>
                    <span className="run-link-meta"><Badge value={run.verdict ?? run.state} /><time>{when(run.created_at, true)}</time></span>
                  </button>
                </li>
              ))}
            </ul>
          </aside>
          <div className="workspace">
            {error && <p className="alert" role="alert">{error}</p>}
            {showForm && registry ? (
              <RunForm registry={registry} csrf={csrf} onCreated={(run) => {
                refreshItem(run);
                choose(run.id);
                setShowForm(false);
              }} onClose={selected ? () => setShowForm(false) : undefined} />
            ) : selected ? (
              <RunReview key={selected} id={selected} registry={registry} csrf={csrf} onUpdate={refreshItem} />
            ) : (
              <section className="empty">
                <h1>Verification runs</h1>
                <p className="muted">Select a run to review its browser evidence, or start a new comparison.</p>
                <button className="primary" onClick={() => setShowForm(true)}>New run</button>
              </section>
            )}
          </div>
        </main>}
    </>
  );
}

function SignIn({ error, onError, onSession }: {
  error: string; onError: (error: string) => void; onSession: (token: string) => void;
}) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    onError("");
    try {
      const { data, error } = await api.POST("/api/v1/session", { body: { password } });
      if (data) onSession(data.csrf_token);
      else onError(errorMessage(error, "Could not sign in."));
    } catch { onError("The local API is unavailable."); }
    finally { setBusy(false); }
  }

  return (
    <main className="login">
      <form className="panel login-card" onSubmit={submit}>
        <h1>Owner sign-in</h1>
        <p className="muted">Enter the owner password generated during local setup.</p>
        <label>Owner password
          <input autoComplete="current-password" type="password" required autoFocus value={password}
            onChange={(event) => setPassword(event.target.value)} />
        </label>
        {error && <p className="alert" role="alert">{error}</p>}
        <button className="primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
    </main>
  );
}

function RunForm({ registry, csrf, onCreated, onClose }: {
  registry: Registry; csrf: string; onCreated: (run: Run) => void; onClose?: () => void;
}) {
  const first = registry.repositories[0]?.id ?? "";
  const [repo, setRepo] = useState(first);
  const [profile, setProfile] = useState(registry.profiles.find((item) => item.repo_id === first)?.id ?? "");
  const profiles = registry.profiles.filter((item) => item.repo_id === repo);
  const selected = profiles.find((item) => item.id === profile);
  const [base, setBase] = useState(selected?.base ?? "");
  const [head, setHead] = useState(selected?.head ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<{ body: string; key: string } | null>(null);

  function chooseProfile(item?: Schema["ProfileChoice"]) {
    setProfile(item?.id ?? "");
    setBase(item?.base ?? "");
    setHead(item?.head ?? "");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !selected) return;
    setBusy(true);
    setError("");
    const body = { repo_id: repo, profile_id: profile, base_ref: base.trim(), head_ref: head.trim() };
    const payload = JSON.stringify(body);
    if (request.current?.body !== payload) request.current = { body: payload, key: crypto.randomUUID() };
    try {
      const { data, error } = await api.POST("/api/v1/runs", {
        body, params: { header: { ...writeHeaders(csrf), "Idempotency-Key": request.current.key } },
      });
      if (data) onCreated(data);
      else setError(errorMessage(error, "Could not submit the run. Check the registered refs."));
    } catch { setError("The connection dropped. Submit again to recover this request."); }
    finally { setBusy(false); }
  }

  return (
    <section className="new-run">
      <h1>New verification run</h1>
      <p className="muted">Choose a registered repository and profile, then enter the two Git refs to compare.</p>
      <form className="panel run-form" onSubmit={submit}>
        <div className="form-grid">
          <label>Repository
            <select value={repo} disabled={busy} onChange={(event) => {
              const id = event.target.value;
              setRepo(id);
              chooseProfile(registry.profiles.find((item) => item.repo_id === id));
            }}>
              {registry.repositories.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </label>
          <label>Profile
            <select value={profile} disabled={busy} onChange={(event) => {
              chooseProfile(profiles.find((item) => item.id === event.target.value));
            }}>
              {profiles.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </label>
          <label>Baseline ref
            <input value={base} onChange={(event) => setBase(event.target.value)} required maxLength={256} disabled={busy} />
          </label>
          <label>Candidate ref
            <input value={head} onChange={(event) => setHead(event.target.value)} required maxLength={256} disabled={busy} />
          </label>
        </div>
        {error && <p className="alert" role="alert">{error}</p>}
        <div className="actions">
          <button className="primary" disabled={busy || !selected}>{busy ? "Queuing run…" : "Start run"}</button>
          {onClose && <button className="quiet" type="button" onClick={onClose} disabled={busy}>Back to run</button>}
        </div>
      </form>
    </section>
  );
}
