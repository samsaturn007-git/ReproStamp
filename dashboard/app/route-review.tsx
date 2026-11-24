import { useState } from "react";
import { api, errorMessage, runUrl, type Schema, writeHeaders } from "../lib/client";

type Run = Schema["RunDetail"];
type Review = Schema["RouteReview"];
type Binding = Schema["VisualBinding"];

const views = [["base", "Baseline"], ["head", "Candidate"], ["diff", "Pixel diff"]] as const;
const outcomes = {
  changed: "Changed",
  unchanged: "Unchanged",
  approved: "Approved",
  unavailable: "Unavailable",
  regression: "New findings",
  passed: "No new findings",
};

function sameScreenshot(left: Binding, right: Binding) {
  return left.route_id === right.route_id && left.commit === right.commit && left.engine === right.engine &&
    left.profile_sha256 === right.profile_sha256 && left.screenshot_sha256 === right.screenshot_sha256 &&
    left.browser_build.version === right.browser_build.version && left.browser_build.platform === right.browser_build.platform;
}

export function RouteReviews({ run, expired, csrf, refresh }: {
  run: Run; expired: boolean; csrf: string; refresh: () => void;
}) {
  return <section aria-labelledby="route-review-heading">
    <div className="section-head"><h2 id="route-review-heading">Visual and accessibility review</h2></div>
    <div className="route-reviews">
      {run.reviews.map((review) => <RouteReview key={review.route_id} {...{ run, review, expired, csrf, refresh }} />)}
    </div>
  </section>;
}

function RouteReview({ run, review, expired, csrf, refresh }: {
  run: Run; review: Review; expired: boolean; csrf: string; refresh: () => void;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const { visual, accessibility, browser_build: build, path } = review;
  const binding = visual.binding;
  const history = run.visual_approvals.filter((approval) => approval.binding.route_id === review.route_id);
  const accepted = binding && history.find((approval) => sameScreenshot(approval.binding, binding));
  const evidence = new Map(run.artifacts.map((artifact) => [artifact.path, `${runUrl(run.id)}/artifacts/${artifact.id}`]));

  async function approve() {
    if (!binding || !run.receipt_sha) return;
    setError("");
    setPending(true);
    try {
      const { data, error } = await api.POST("/api/v1/runs/{run_id}/visual-reviews/{route_id}/approval", {
        params: { path: { run_id: run.id, route_id: review.route_id }, header: writeHeaders(csrf) },
        body: { receipt_sha: run.receipt_sha, screenshot_sha256: binding.screenshot_sha256 },
      });
      if (data) refresh();
      else setError(errorMessage(error, "Could not approve this screenshot."));
    } catch { setError("Could not reach the local API."); }
    finally { setPending(false); }
  }

  return <article className="panel route-review">
    <header className="route-review-heading">
      <h3><code>{path}</code></h3>
      <span className="muted">{review.engine} {build && `${build.version} · ${build.platform}`}</span>
    </header>
    <div className="route-check">
      <div className="route-check-heading">
        <h4>Visual</h4><CheckStatus outcome={accepted ? "approved" : visual.status} required={visual.required} />
        {visual.changed_pixels !== null && <span className="muted">{visual.changed_pixels.toLocaleString()} changed pixels</span>}
      </div>
      {visual.detail && <p className="muted">{visual.detail}</p>}
      {!expired && Object.keys(visual.artifacts).length > 0 && <div className="route-screenshots">
        {views.map(([kind, label]) => {
          const url = evidence.get(visual.artifacts[kind]);
          if (!url) return null;
          return <figure key={kind}>
            <figcaption>{label}</figcaption>
            <a href={url} target="_blank" rel="noreferrer"><img alt={`${label} screenshot for ${path}`} src={url} /></a>
          </figure>;
        })}
      </div>}
      {binding && <div className="route-approval">
        {!expired && !accepted && visual.status === "changed" && run.receipt_sha &&
          <button type="button" className="outline compact" onClick={approve} disabled={pending}>
            {pending ? "Approving…" : "Approve candidate screenshot"}
          </button>}
        {accepted && <span role="status">Approved by {accepted.accepted_by} · {new Date(accepted.accepted_at).toLocaleString()}
          {visual.status === "changed" && " · Rerun the comparison to apply this approval."}</span>}
        <span className="muted">Candidate SHA-256 <code title={binding.screenshot_sha256}>{binding.screenshot_sha256.slice(0, 12)}</code></span>
      </div>}
      {error && <p className="alert" role="alert">{error}</p>}
      {history.length > 0 && <details className="approval-history">
        <summary>Approval history ({history.length})</summary>
        <ul>{history.map((approval) => <li key={`${approval.run_id}-${approval.binding.screenshot_sha256}`}>
          <strong>{approval.accepted_by}</strong> · <time dateTime={approval.accepted_at}>{new Date(approval.accepted_at).toLocaleString()}</time>
          {" · "}<a href={`/?run=${approval.run_id}`} title={approval.receipt_sha}>Source run</a>
          <div className="muted">
            Commit <code title={approval.binding.commit}>{approval.binding.commit.slice(0, 12)}</code>{" · "}
            Profile <code title={approval.binding.profile_sha256}>{approval.binding.profile_sha256.slice(0, 12)}</code>{" · "}
            {approval.binding.engine} {approval.binding.browser_build.version} ({approval.binding.browser_build.platform}){" · "}
            Screenshot <code title={approval.binding.screenshot_sha256}>{approval.binding.screenshot_sha256.slice(0, 12)}</code>
          </div>
        </li>)}</ul>
      </details>}
    </div>
    <div className="route-check">
      <div className="route-check-heading">
        <h4>Accessibility</h4><CheckStatus outcome={accessibility.status} required={accessibility.required} />
        {accessibility.axe_version && <span className="muted">axe-core {accessibility.axe_version}</span>}
      </div>
      {accessibility.detail && <p className="muted">{accessibility.detail}</p>}
      {accessibility.findings.length > 0 && <div className="table-wrap">
        <table className="axe-findings" aria-label={`New accessibility findings for ${path}`}>
          <thead><tr><th scope="col">Rule</th><th scope="col">Impact</th><th scope="col">Target</th></tr></thead>
          <tbody>{accessibility.findings.map(({ rule, impact, target }) => <tr key={JSON.stringify([rule, target, impact])}>
            <th scope="row"><code>{rule}</code></th><td>{impact ?? "Unrated"}</td><td><code>{target}</code></td>
          </tr>)}</tbody>
        </table>
      </div>}
    </div>
  </article>;
}

function CheckStatus({ outcome, required }: { outcome: keyof typeof outcomes; required: boolean }) {
  return <>
    <span className={`badge badge-${outcome}`}>{outcomes[outcome]}</span>
    <span className="muted">{required ? "Required" : "Advisory"}</span>
  </>;
}
