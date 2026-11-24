"use client";

import { useEffect, useRef, useState } from "react";
import { api, errorMessage, runUrl, writeHeaders, type Schema } from "../lib/client";
import { RouteReviews } from "./route-review";

type Run = Schema["RunDetail"];
type Attempt = Schema["Attempt"];
type Artifact = Schema["Artifact"];
type RunEvent = Schema["RunEvent"];
type ReplayRequest = Schema["NewCaseReplay"];

const sides = ["base", "head"] as const;
const numbers = [1, 2] as const;
const replayAttempts = 5;
const activeStates = ["queued", "running", "cancelling"];
const labels: Record<string, string> = {
  verified: "Verified", failed: "Failed", policy_blocked: "Policy blocked", inconclusive: "Inconclusive",
  assertion_failed: "Assertion failed", lease_expired: "Worker lease expired", retry_started: "Recovery started",
  attempt_started: "Attempt started", attempt_finished: "Attempt finished", webkit: "WebKit",
  consistent_failure: "Consistent failure", suspected_flaky: "Suspected flaky",
  infrastructure_failure: "Infrastructure failure", passed_on_replay: "Passed on replay",
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

export function RunReview({ id, registry, csrf, onUpdate, onReplay }: {
  id: string; registry?: Schema["Registry"]; csrf: string; onUpdate: (run: Run) => void;
  onReplay: (run: Schema["RunSummary"]) => void;
}) {
  const [run, setRun] = useState<Run>();
  const [timeline, setTimeline] = useState<RunEvent[]>([]);
  const [connection, setConnection] = useState("Connecting");
  const [error, setError] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [replaying, setReplaying] = useState(false);
  const replayKey = useRef<{ selection: string; key: string } | null>(null);
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
    let stream: EventSource;
    let retry: ReturnType<typeof setTimeout> | undefined;
    function connect(after?: number) {
      const url = `${runUrl(id)}/events${after === undefined ? "" : `?after=${after}`}`;
      const source = new EventSource(url);
      stream = source;
      source.onopen = () => {
        setConnection("Live");
        setError("");
        refresh.current();
      };
      source.onmessage = (message) => {
        const event: RunEvent = JSON.parse(message.data);
        if (event.seq <= sequence.current) return;
        sequence.current = event.seq;
        setTimeline((current) => [...current, event]);
        pending ??= setTimeout(() => {
          pending = undefined;
          refresh.current();
        }, 100);
      };
      source.onerror = () => {
        setConnection("Reconnecting");
        // HTTP errors during a reconnect can permanently close the browser's EventSource.
        if (source.readyState === EventSource.CLOSED) {
          retry = setTimeout(() => connect(sequence.current), 1200);
        }
      };
      source.addEventListener("timeline-complete", () => {
        source.close();
        setConnection("Complete");
        clearTimeout(pending);
        refresh.current();
      });
    }
    connect();
    return () => { clearTimeout(retry); clearTimeout(pending); stream.close(); controller.abort(); };
  }, [id]);

  useEffect(() => {
    if (!run || !window.location.hash.startsWith("#attempt-")) return;
    const target = document.getElementById(window.location.hash.slice(1));
    if (target instanceof HTMLDetailsElement && !target.open) {
      target.open = true;
      target.scrollIntoView({ block: "nearest" });
    }
  }, [run]);

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

  async function replay(body: ReplayRequest) {
    const selection = JSON.stringify(body);
    if (replayKey.current?.selection !== selection) replayKey.current = { selection, key: crypto.randomUUID() };
    setReplaying(true);
    setError("");
    try {
      const { data, error } = await api.POST("/api/v1/runs/{run_id}/case-replays", {
        body, params: { path: { run_id: id }, header: {
          ...writeHeaders(csrf), "Idempotency-Key": replayKey.current.key,
        } },
      });
      if (data) onReplay(data);
      else setError(errorMessage(error, "Could not queue the case replay."));
    } catch { setError("The connection dropped. Select the same case again to recover this request."); }
    finally { setReplaying(false); }
  }

  if (!run) return <p className={error ? "alert" : "muted"} role={error ? "alert" : "status"}>{error || "Loading run…"}</p>;
  const finished = run.attempts.filter((a) => a.fence === run.fence && a.result !== null).length;
  const total = run.replay ? replayAttempts : run.plan.engines.length * sides.length * numbers.length;
  const expired = run.expired || Boolean(run.expires_at && Date.parse(run.expires_at) <= Date.now());
  const download = !expired && run.receipt_sha;
  const repository = registry?.repositories.find((repo) => repo.id === run.request.repo_id)?.label ?? run.request.repo_id;

  return (
    <article className="review">
      <div className="review-header">
        <div>
          <div className="badges"><Badge value={run.state} />{run.verdict && <Badge value={run.verdict} />}</div>
          <h1>{run.replay ? `Case replay · ${run.replay.case_id}` : repository}</h1>
          <p className="muted">Run <code>{run.id.slice(0, 8)}</code> · {when(run.created_at)}</p>
        </div>
        <div className="actions">
          {download && <a className="primary" href={`${runUrl(id)}/receipt`}>Download receipt</a>}
          {["queued", "running"].includes(run.state) && <button className="outline" disabled={cancelling} onClick={cancel}>Cancel run</button>}
        </div>
      </div>
      {error && <p className="alert" role="alert">{error}</p>}
      {run.replay ? <div className="panel replay-source">
        <p><strong>{repository}</strong> · {title(run.replay.engine)} · {run.replay.side === "base" ? "Baseline" : "Candidate"} · <code title={run.replay.commit}>{run.replay.commit.slice(0, 12)}</code></p>
        <p><a href={`/?run=${run.source_run_id}#attempt-${run.replay.engine}-${run.replay.side}-${run.replay.number}`}>Original run and attempt</a>
          {" · "}<code title={run.replay.receipt_sha}>{run.replay.receipt_sha.slice(0, 12)}</code></p>
      </div> : <dl className="commit-grid panel">
        {sides.map((side) => <div key={side}>
          <dt>{side === "base" ? "Baseline" : "Candidate"}</dt>
          <dd><span>{side === "base" ? run.request.base_ref : run.request.head_ref}</span>
            <code title={side === "base" ? run.base_sha : run.head_sha}>{(side === "base" ? run.base_sha : run.head_sha).slice(0, 12)}</code>
          </dd>
        </div>)}
      </dl>}
      {run.superseded_at && <div className="notice"><strong>Evidence superseded</strong>
        <p>The pull request moved away from the tested base and candidate.</p></div>}
      {run.reason && run.reason !== "case_replay_finished" && <div className="notice"><strong>{title(run.reason)}</strong><p>{run.detail}</p></div>}
      {run.expires_at && <p className="retention muted">{expired ? "Evidence expired" : "Evidence expires"} {when(run.expires_at)}.</p>}
      <div className="review-grid">
        <section className="matrix-section">
          <div className="section-head"><h2>{run.replay ? "Replay outcomes" : run.plan.review ? "Functional browser matrix" : "Browser matrix"}</h2><span className="muted">{finished} / {total} attempts</span></div>
          {activeStates.includes(run.state) && <progress aria-label="Browser attempts recorded" value={finished} max={total || 1} />}
          {run.replay ? <ReplayOutcomes run={run} expired={expired} /> : <Matrix run={run} expired={expired} />}
        </section>
        <Timeline events={timeline} connection={connection} />
      </div>
      {run.reviews.length > 0 && <RouteReviews run={run} expired={Boolean(expired)} csrf={csrf}
        refresh={() => refresh.current()} />}
      <section className="attempts-section">
        <div className="section-head"><h2>Attempts</h2></div>
        <div className="panel attempts">
          {run.attempts.length === 0 && <p className="muted inset">Attempts will appear as the worker starts them.</p>}
          {run.attempts.map((attempt) => (
            <AttemptRow key={`${attempt.fence}-${attempt.engine}-${attempt.side}-${attempt.number}`}
              run={run} attempt={attempt} expired={expired} onLog={setLog} busy={replaying}
              onReplay={download && !run.replay && attempt.fence === run.fence ? replay : undefined} />
          ))}
        </div>
      </section>
      {run.case_replays.length > 0 && <section>
        <div className="section-head"><h2>Case replays</h2></div>
        <ul className="panel failure-receipts">
          {run.case_replays.map(({ id, replay, state, created_at }) => <li key={id}>
            <a href={`/?run=${id}`}><code>{replay.case_id}</code> · {title(replay.engine)} · {replay.side === "base" ? "Baseline" : "Candidate"} {replay.number}</a>
            <Badge value={state} /> <time className="muted" dateTime={created_at}>{when(created_at, true)}</time>
          </li>)}
        </ul>
      </section>}
      {!run.replay && <FailureHistory repoId={run.request.repo_id} finished={run.finished_at} />}
      {log && !expired && <LogViewer artifact={log} runId={run.id} close={() => setLog(undefined)} />}
    </article>
  );
}

function ReplayOutcomes({ run, expired }: { run: Run; expired: boolean }) {
  const attempts = run.attempts.filter((attempt) => attempt.fence === run.fence);
  const summary = run.replay_summary;
  return <>
    {summary?.classification && <div className="notice replay-classification">
      <Badge value={summary.classification} /> <span>Sample size {summary.sample_size}</span>
      <p>{summary.passed} passed · {summary.assertion_failed} assertion failures · {summary.infrastructure_failure} infrastructure failures</p>
    </div>}
    <div className="panel table-wrap replay-table">
      <table aria-label="Case replay outcomes">
        <thead><tr><th scope="col">Attempt</th><th scope="col">Outcome</th><th scope="col">Duration</th><th scope="col">Evidence</th></tr></thead>
        <tbody>{Array.from({ length: replayAttempts }, (_, index) => {
          const number = index + 1;
          const attempt = attempts.find((item) => item.number === number);
          const result = attempt?.result;
          const item = result?.cases[0];
          const status = result ? (attempt?.state === "completed" && item ? item.status : "infrastructure_failure")
            : attempt?.state ?? (activeStates.includes(run.state) ? "pending" : "missing");
          return <tr key={number}>
            <th scope="row">{number}</th>
            <td><Badge value={status} />{result?.reason && <span className="cell-value">{title(result.reason)}</span>}</td>
            <td>{result ? `${result.duration_ms} ms` : "—"}</td>
            <td>{!expired && item && <EvidenceLinks run={run} paths={item.artifacts} />}</td>
          </tr>;
        })}</tbody>
      </table>
    </div>
  </>;
}

function FailureHistory({ repoId, finished }: { repoId: string; finished?: string | null }) {
  const [groups, setGroups] = useState<Schema["FailureGroup"][]>();
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api.GET("/api/v1/repositories/{repo_id}/failures", {
      params: { path: { repo_id: repoId } }, signal: controller.signal,
    }).then(({ data }) => {
      if (!controller.signal.aborted) { setGroups(data); setError(!data); }
    }).catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [repoId, finished]);

  return <section>
    <div className="section-head"><h2>Repository failure history</h2></div>
    {error && <p className="alert" role="alert">Failure history is unavailable.</p>}
    {!error && !groups && <p className="muted" role="status">Loading failure history…</p>}
    {groups?.length === 0 && <p className="muted">No failures with verification receipts.</p>}
    {groups && (["application_assertion", "infrastructure_failure"] as const).map((kind) => {
      const items = groups.filter((group) => group.kind === kind);
      if (!items.length) return null;
      return <section className="panel failure-groups" key={kind}>
        <h3>{kind === "application_assertion" ? "Application assertions" : "Runner and dependency failures"}</h3>
        {items.map((group) => <details className="attempt" key={JSON.stringify(
          [group.case_id, group.assertion, group.expected, group.application_location, group.reason],
        )}>
          <summary><strong>{group.case_id ?? title(group.reason ?? kind)}</strong>
            {group.assertion && <code>{group.assertion}</code>}
            {group.reason && group.case_id && <span>{title(group.reason)}</span>}
            <span className="muted">{group.count} {group.count === 1 ? "observation" : "observations"}</span></summary>
          <div className="attempt-body">
            {group.assertion && <p>Expected <code>{group.expected}</code> · {group.application_location
              ? <code>{group.application_location}</code> : "Application stack location unavailable"}</p>}
            <p className="muted">First seen {when(group.first_seen)} · Last seen {when(group.last_seen)}
              {group.browsers.length > 0 && ` · ${group.browsers.map(title).join(", ")}`}</p>
            <ul className="failure-receipts">
              {group.receipts.map((receipt) => <li key={receipt.run_id}>
                <a href={`/?run=${receipt.run_id}`}>Run {receipt.run_id.slice(0, 8)}</a>
                {receipt.expired ? <span className="muted">Receipt expired</span>
                  : <a href={`${runUrl(receipt.run_id)}/receipt`}>Receipt <code>{receipt.receipt_sha.slice(0, 12)}</code></a>}
              </li>)}
            </ul>
          </div>
        </details>)}
      </section>;
    })}
  </section>;
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

function AttemptRow({ run, attempt, expired, onLog, onReplay, busy }: {
  run: Run; attempt: Attempt; expired: boolean; onLog: (artifact: Artifact) => void;
  onReplay?: (body: ReplayRequest) => void; busy: boolean;
}) {
  function replayAction(caseId: string) {
    if (!onReplay || (attempt.number !== 1 && attempt.number !== 2)) return null;
    const { engine } = attempt;
    if (engine !== "chromium" && engine !== "firefox" && engine !== "webkit") return null;
    const body = { engine, side: attempt.side, number: attempt.number, case_id: caseId } as const;
    return <button className="outline compact" type="button" disabled={busy}
      onClick={() => onReplay(body)}>Replay failing case</button>;
  }

  return (
    <details className="attempt" id={attempt.fence === run.fence ? `attempt-${attempt.engine}-${attempt.side}-${attempt.number}` : undefined}>
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
              {item.application_location && <p><code>{item.application_location}</code></p>}
              {item.detail && <p className="muted">{item.detail}</p>}
              {!expired && attempt.fence === run.fence && <EvidenceLinks run={run} paths={item.artifacts} />}
              {(item.status === "assertion_failed" || attempt.result?.reason) && replayAction(item.case_id)}
            </li>)}
            {onReplay && attempt.result.reason && run.plan.case_ids.filter((caseId) =>
              !attempt.result?.cases.some((item) => item.case_id === caseId),
            ).map((caseId) => <li key={caseId}><code>{caseId}</code> <Badge value="missing" /> {replayAction(caseId)}</li>)}
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
