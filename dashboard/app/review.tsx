"use client";

import { useEffect, useRef, useState } from "react";
import { api, errorMessage, runUrl, writeHeaders, type Schema } from "../lib/client";

type Run = Schema["RunDetail"];
type Attempt = Schema["Attempt"];
type Artifact = Schema["Artifact"];
type RunEvent = Schema["RunEvent"];

const sides = ["base", "head"] as const;
const numbers = [1, 2] as const;
const activeStates = ["queued", "running", "cancelling"];
const labels: Record<string, string> = {
  verified: "Verified", failed: "Failed", policy_blocked: "Policy blocked", inconclusive: "Inconclusive",
  assertion_failed: "Assertion failed", lease_expired: "Worker lease expired", retry_started: "Recovery started",
  attempt_started: "Attempt started", attempt_finished: "Attempt finished", webkit: "WebKit",
};

export function title(value: string) {
  return labels[value.toLowerCase()] ?? value[0].toUpperCase() + value.slice(1).replaceAll("_", " ");
}

export function when(value: string, short = false) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short", day: "numeric", ...(short ? {} : { year: "numeric" }),
    hour: "numeric", minute: "2-digit",
  }).format(new Date(value));
}

export function Badge({ value }: { value: string }) {
  return <span className={`badge badge-${value.toLowerCase()}`}>{title(value)}</span>;
}

export function RunReview({ id, registry, csrf, onUpdate }: {
  id: string; registry?: Schema["Registry"]; csrf: string; onUpdate: (run: Run) => void;
}) {
  const [run, setRun] = useState<Run>();
  const [timeline, setTimeline] = useState<RunEvent[]>([]);
  const [connection, setConnection] = useState("Connecting");
  const [error, setError] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [log, setLog] = useState<Artifact>();
  const updateHistory = useRef(onUpdate);
  const sequence = useRef(0);
  const refresh = useRef<() => void>(() => {});
  updateHistory.current = onUpdate;

  useEffect(() => {
    const controller = new AbortController();
    let request = 0;
    let pending: ReturnType<typeof setTimeout> | undefined;
    refresh.current = () => {
      const version = ++request;
      api.GET("/api/v1/runs/{run_id}", { params: { path: { run_id: id } }, signal: controller.signal })
        .then(({ data, error }) => {
          if (controller.signal.aborted || version !== request) return;
          if (!data) {
            setError(errorMessage(error, "Run details are unavailable."));
            return;
          }
          setRun(data);
          updateHistory.current(data);
        }).catch(() => {
          if (!controller.signal.aborted && version === request) setError("The connection to the local API dropped.");
        });
    };
    refresh.current();
    const stream = new EventSource(`${runUrl(id)}/events`);
    stream.onopen = () => {
      setConnection("Live");
      setError("");
      refresh.current();
    };
    stream.onmessage = (message) => {
      const event: RunEvent = JSON.parse(message.data);
      if (event.seq <= sequence.current) return;
      sequence.current = event.seq;
      setTimeline((current) => [...current, event]);
      pending ??= setTimeout(() => {
        pending = undefined;
        refresh.current();
      }, 100);
    };
    stream.onerror = () => setConnection("Reconnecting");
    stream.addEventListener("timeline-complete", () => {
      stream.close();
      setConnection("Complete");
      clearTimeout(pending);
      refresh.current();
    });
    return () => { clearTimeout(pending); stream.close(); controller.abort(); };
  }, [id]);

  async function cancel() {
    setCancelling(true);
    setError("");
    try {
      const { data, error } = await api.POST("/api/v1/runs/{run_id}/cancel", {
        params: { path: { run_id: id }, header: writeHeaders(csrf) },
      });
      if (data) refresh.current();
      else setError(errorMessage(error, "Could not cancel this run."));
    } catch { setError("Could not reach the local API."); }
    finally { setCancelling(false); }
  }

  if (!run) return <p className={error ? "alert" : "muted"} role={error ? "alert" : "status"}>{error || "Loading run…"}</p>;
  const finished = run.attempts.filter((a) => a.fence === run.fence && a.result !== null).length;
  const total = run.plan.engines.length * sides.length * numbers.length;
  const expired = run.expired || Boolean(run.expires_at && Date.parse(run.expires_at) <= Date.now());
  const download = !expired && run.receipt_sha;
  const repository = registry?.repositories.find((repo) => repo.id === run.request.repo_id)?.label ?? run.request.repo_id;

  return (
    <article className="review">
      <div className="review-header">
        <div>
          <div className="badges"><Badge value={run.state} />{run.verdict && <Badge value={run.verdict} />}</div>
          <h1>{repository}</h1>
          <p className="muted">Run <code>{run.id.slice(0, 8)}</code> · {when(run.created_at)}</p>
        </div>
        <div className="actions">
          {download && <a className="primary" href={`${runUrl(id)}/receipt`}>Download receipt</a>}
          {["queued", "running"].includes(run.state) && <button className="outline" disabled={cancelling} onClick={cancel}>Cancel run</button>}
        </div>
      </div>
      {error && <p className="alert" role="alert">{error}</p>}
      <dl className="commit-grid panel">
        {sides.map((side) => <div key={side}>
          <dt>{side === "base" ? "Baseline" : "Candidate"}</dt>
          <dd><span>{side === "base" ? run.request.base_ref : run.request.head_ref}</span>
            <code title={side === "base" ? run.base_sha : run.head_sha}>{(side === "base" ? run.base_sha : run.head_sha).slice(0, 12)}</code>
          </dd>
        </div>)}
      </dl>
      {run.reason && <div className="notice"><strong>{title(run.reason)}</strong><p>{run.detail}</p></div>}
      {run.expires_at && <p className="retention muted">{expired ? "Evidence expired" : "Evidence expires"} {when(run.expires_at)}.</p>}
      <div className="review-grid">
        <section className="matrix-section">
          <div className="section-head"><h2>Browser matrix</h2><span className="muted">{finished} / {total} attempts</span></div>
          {activeStates.includes(run.state) && <progress aria-label="Browser attempts recorded" value={finished} max={total || 1} />}
          <Matrix run={run} expired={expired} />
        </section>
        <Timeline events={timeline} connection={connection} />
      </div>
      <section className="attempts-section">
        <div className="section-head"><h2>Attempts</h2></div>
        <div className="panel attempts">
          {run.attempts.length === 0 && <p className="muted inset">Attempts will appear as the worker starts them.</p>}
          {run.attempts.map((attempt) => (
            <AttemptRow key={`${attempt.fence}-${attempt.engine}-${attempt.side}-${attempt.number}`}
              run={run} attempt={attempt} expired={expired} onLog={setLog} />
          ))}
        </div>
      </section>
      {log && !expired && <LogViewer artifact={log} runId={run.id} close={() => setLog(undefined)} />}
    </article>
  );
}

function Matrix({ run, expired }: { run: Run; expired: boolean }) {
  const current = run.fence > 2 ? 2 : run.fence;
  return (
    <div className="panel table-wrap">
      <table aria-label="Browser verification matrix">
        <thead><tr><th scope="col">Browser and test</th><th scope="col">Base 1</th><th scope="col">Base 2</th>
          <th scope="col">Candidate 1</th><th scope="col">Candidate 2</th></tr></thead>
        <tbody>
          {run.plan.engines.flatMap((engine) => run.plan.case_ids.map((caseId, index) => (
            <tr key={`${engine}-${caseId}`}>
              <th scope="row">
                <span className="engine">{title(engine)} {index === 0 && run.engine_verdicts[engine] && <small>{title(run.engine_verdicts[engine].name)}</small>}</span>
                <code>{caseId}</code>
              </th>
              {sides.flatMap((side) => numbers.map((number) => {
                const attempt = run.attempts.find((item) =>
                  item.engine === engine && item.side === side && item.number === number && item.fence === current);
                const item = attempt?.result?.cases.find((test) => test.case_id === caseId);
                const unsupported = attempt?.result?.reason === "required_engine_unsupported";
                const status = (item?.status === "missing" && unsupported ? "unsupported" : item?.status) ??
                  (attempt?.state === "running" ? "running" :
                  attempt?.state === "interrupted" ? "interrupted" :
                  unsupported ? "unsupported" :
                  activeStates.includes(run.state) && !attempt ? "pending" : "missing");
                return <td key={`${side}-${number}`}>
                  <Badge value={status} />
                  {item?.assertion && <span className="cell-value">{item.assertion.actual ?? "—"}</span>}
                  {item && !expired && attempt?.fence === run.fence && <EvidenceLinks run={run} paths={item.artifacts} />}
                </td>;
              }))}
            </tr>
          )))}
        </tbody>
      </table>
    </div>
  );
}

function EvidenceLinks({ run, paths }: { run: Run; paths: Record<string, string> }) {
  return <div className="evidence-links">
    {Object.entries(paths).map(([kind, path]) => {
      const artifact = run.artifacts.find((item) => item.path === path);
      return artifact && <a key={path} href={`${runUrl(run.id)}/artifacts/${artifact.id}`}>{title(kind)}</a>;
    })}
  </div>;
}

function Timeline({ events, connection }: { events: RunEvent[]; connection: string }) {
  const list = useRef<HTMLOListElement>(null);
  const follow = useRef(true);
  useEffect(() => {
    const node = list.current;
    if (node && follow.current) node.scrollTop = node.scrollHeight;
  }, [events.length]);

  return (
    <section className="timeline-section">
      <div className="section-head"><h2>Timeline</h2><span className="stream-status" role="status">{connection}</span></div>
      <ol className="panel timeline" aria-label="Run timeline" ref={list} onScroll={(event) => {
        const { scrollTop, scrollHeight, clientHeight } = event.currentTarget;
        follow.current = scrollHeight - scrollTop - clientHeight < 40;
      }}>
        {events.length === 0 && <li className="muted">Waiting for run events…</li>}
        {events.map((event) => (
          <li key={event.seq} data-sequence={event.seq}>
            <span className="timeline-marker" aria-hidden="true" />
            <div>
              <strong>{title(event.kind)}</strong>
              <span className="event-detail">
                {event.data.engine ? `${title(String(event.data.engine))} · ${event.data.side === "base" ? "Base" : "Candidate"}
                  ${event.data.number} · Generation ${event.data.generation}` :
                  event.data.generation ? `Generation ${event.data.generation}` : ""}
              </span>
            </div>
            <time dateTime={event.created_at}>{new Date(event.created_at).toLocaleTimeString()}</time>
          </li>
        ))}
      </ol>
    </section>
  );
}

function AttemptRow({ run, attempt, expired, onLog }: {
  run: Run; attempt: Attempt; expired: boolean; onLog: (artifact: Artifact) => void;
}) {
  return (
    <details className="attempt">
      <summary>
        <strong>{title(attempt.engine)} · {attempt.side === "base" ? "Baseline" : "Candidate"} {attempt.number}</strong>
        <span className="muted">Generation {attempt.fence}</span>
        <Badge value={attempt.state} />
      </summary>
      <div className="attempt-body">
        {attempt.result ? <>
          <p className="muted">{attempt.result.browser_build
            ? `${attempt.result.browser_build.version} · ${attempt.result.browser_build.platform} · `
            : ""}{attempt.result.duration_ms} ms</p>
          {attempt.result.detail && <p>{attempt.result.detail}</p>}
          <ul className="case-results">
            {attempt.result.cases.map((item) => <li key={item.case_id}>
              <code>{item.case_id}</code> <Badge value={item.status} />
              {item.assertion && <p className="muted">Observed <code>{item.assertion.actual ?? "—"}</code>, expected <code>{item.assertion.expected}</code>.</p>}
              {item.detail && <p className="muted">{item.detail}</p>}
              {!expired && attempt.fence === run.fence && <EvidenceLinks run={run} paths={item.artifacts} />}
            </li>)}
          </ul>
          {!expired && attempt.fence === run.fence && <div className="actions">
            {Object.entries(attempt.result.logs).map(([role, path]) => {
              const artifact = run.artifacts.find((item) => item.path === path);
              return artifact && <button className="outline compact" key={path} onClick={() => onLog(artifact)}>View {role} log</button>;
            })}
          </div>}
        </> : <p className="muted">{attempt.state === "interrupted" ? "The worker stopped before recording a result." : "The browser workload is running."}</p>}
      </div>
    </details>
  );
}

function LogViewer({ artifact, runId, close }: { artifact: Artifact; runId: string; close: () => void }) {
  const [text, setText] = useState("Loading log…");
  const dialog = useRef<HTMLDialogElement>(null);
  const path = `${runUrl(runId)}/artifacts/${artifact.id}`;
  useEffect(() => {
    const controller = new AbortController();
    dialog.current?.showModal();
    fetch(path, { signal: controller.signal }).then((response) => response.ok ? response.text() : "This log is unavailable.")
      .then(setText).catch(() => { if (!controller.signal.aborted) setText("Could not load this log."); });
    return () => controller.abort();
  }, [path]);
  return (
    <dialog ref={dialog} onClose={close}>
      <div className="section-head"><h2>{artifact.path.split("/").at(-1)}</h2>
        <button className="outline compact" onClick={close}>Close</button></div>
      <pre>{text}</pre>
      <a href={path}>Download log</a>
    </dialog>
  );
}
