import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, jobsApi } from "../api";
import JobDrawer from "../components/JobDrawer";
import { CATEGORY, RECOMMENDATION, SEGMENTS, salaryShort, scoreClass } from "../format";

const PIPELINE: [string, string][] = [
  ["discovered", "Discovered"], ["shortlisted", "Shortlisted"], ["awaiting_approval", "Awaiting approval"],
  ["applied", "Applied"], ["recruiter_replies", "Recruiter replies"], ["assessments", "Assessments"],
  ["interviews", "Interviews"], ["offers", "Offers"], ["rejections", "Rejections"],
];

export default function Overview() {
  const qc = useQueryClient();
  const [openId, setOpenId] = useState<number | null>(null);
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const facts = useQuery({ queryKey: ["facts"], queryFn: api.facts });
  const usage = useQuery({ queryKey: ["usage"], queryFn: api.usage });
  const overview = useQuery({ queryKey: ["overview"], queryFn: jobsApi.overview });
  const picks = useQuery({ queryKey: ["top-picks"], queryFn: () => jobsApi.topPicks(10) });
  const runs = useQuery({
    queryKey: ["runs"], queryFn: jobsApi.runs,
    refetchInterval: (q) => (q.state.data?.[0]?.status === "running" ? 3000 : false),
  });
  const latest = runs.data?.[0];
  const running = latest?.status === "running";

  const start = useMutation({
    mutationFn: jobsApi.runDiscovery,
    onSettled: () => qc.invalidateQueries({ queryKey: ["runs"] }),
  });

  // When a run finishes, refresh everything that depends on job data.
  const finishedId = latest && latest.status !== "running" ? latest.id : null;
  const firstSeen = useRef<number | null>(null);
  useEffect(() => {
    if (finishedId === null) return;
    if (firstSeen.current === null) {
      firstSeen.current = finishedId;  // already-finished run on page load: nothing to refresh
      return;
    }
    for (const k of ["overview", "top-picks", "jobs", "companies"]) qc.invalidateQueries({ queryKey: [k] });
  }, [finishedId, qc]);

  const unconfirmed = facts.data?.facts.filter((f) => f.needs_confirmation).length ?? 0;

  return (
    <>
      <div className="page-head">
        <h1>Overview</h1>
        <button onClick={() => start.mutate()} disabled={running || start.isPending}>
          {running ? "Discovering…" : "Run discovery"}
        </button>
      </div>
      <RunStatus run={latest} />
      {start.isError && <div className="callout error">{(start.error as Error).message}</div>}

      {unconfirmed > 0 && (
        <div className="callout warn">
          <strong>{unconfirmed} profile facts need your confirmation.</strong> Until then your AI work experience
          isn't counted in job scores. Answer A/B/C in <code>data/profile_facts.yaml</code>, then reload on{" "}
          <Link to="/profile">Profile facts</Link>.
        </div>
      )}

      <section className="tiles">
        {PIPELINE.map(([key, label]) => (
          <div key={key} className="tile">
            <div className="tile-value">{overview.data?.[key] ?? "…"}</div>
            <div className="tile-label">{label}</div>
          </div>
        ))}
      </section>

      <div className="page-head">
        <h2>Top picks today</h2>
        <Link to="/settings" className="small">Mix: 60/30/10 by company size ›</Link>
      </div>
      <div className="table-wrap">
        <table className="jobs-table">
          <thead><tr><th>Company</th><th>Title</th><th>Tab</th><th>Opp</th><th>Suit</th><th>Salary</th><th>Next step</th></tr></thead>
          <tbody>
            {picks.data?.map((j) => (
              <tr key={j.id} className="clickable" onClick={() => setOpenId(j.id)}>
                <td>{j.company}<div className="muted tiny">{j.category ? CATEGORY[j.category] : "Uncategorized"}</div></td>
                <td className="title-cell">{j.title}</td>
                <td className="small">{SEGMENTS.find((s) => s.key === j.segment)?.label}</td>
                <td className={`num ${scoreClass(j.opportunity)}`}>{j.opportunity}</td>
                <td className={`num ${scoreClass(j.suitability)}`}>{j.suitability}</td>
                <td className="small nowrap">{salaryShort(j.salary)}</td>
                <td className="small">{RECOMMENDATION[j.recommendation ?? ""]}</td>
              </tr>
            ))}
            {picks.data?.length === 0 && (
              <tr><td colSpan={7} className="muted empty">No picks yet. Click “Run discovery”.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <h2>System</h2>
      <div className="status-grid">
        <Status label="Database" value={health.data?.db ?? "…"} good={health.data?.db === "ok"} />
        <Status label="LLM engine" value={health.data?.llm_engine ?? "…"} good={!!health.data} />
        <Status label="LLM calls today" value={usage.data ? `${usage.data.calls_today} / ${usage.data.daily_limit}` : "…"}
          good={!!usage.data && usage.data.calls_today < usage.data.daily_limit} />
        <Status label="Usable facts" value={facts.data ? `${facts.data.usable} of ${facts.data.facts.length}` : "…"}
          good={!!facts.data && unconfirmed === 0} />
      </div>
      {openId !== null && <JobDrawer jobId={openId} onClose={() => setOpenId(null)} />}
    </>
  );
}

function RunStatus({ run }: { run?: { status: string; finished_at: string | null; stats: Record<string, number>; errors: { feed: string; error: string }[] } }) {
  if (!run) return <p className="muted small">No discovery run yet.</p>;
  if (run.status === "running") return <p className="muted small">Fetching from ~100 sources. This takes about a minute.</p>;
  const when = run.finished_at ? new Date(run.finished_at).toLocaleString() : "";
  return (
    <p className="muted small">
      Last run {when}: {run.stats.new ?? 0} new, {run.stats.expired ?? 0} closed, {run.stats.scored ?? 0} open jobs scored
      {run.status === "failed" && <span className="error-text"> · failed: {run.errors[0]?.error}</span>}
      {run.status === "done" && run.errors.length > 0 && <span className="error-text"> · {run.errors.length} source(s) failed</span>}
    </p>
  );
}

function Status({ label, value, good }: { label: string; value: string; good: boolean }) {
  return (
    <div className="status">
      <span className={`dot ${good ? "ok" : "warn"}`} />
      <span className="status-label">{label}</span>
      <span className="status-value">{value}</span>
    </div>
  );
}
