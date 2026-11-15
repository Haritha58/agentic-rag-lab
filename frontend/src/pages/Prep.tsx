import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { coachApi, type PrepJob, type TopicProficiency } from "../api";
import { MODE_LABEL, ago, scoreClass } from "../format";

export default function Prep() {
  const jobs = useQuery({ queryKey: ["prep-jobs"], queryFn: coachApi.prepJobs });
  const topics = useQuery({ queryKey: ["prep-topics"], queryFn: coachApi.topics });
  const sessions = useQuery({ queryKey: ["coach-sessions"], queryFn: coachApi.sessions });

  return (
    <>
      <div className="page-head">
        <h1>Interview prep</h1>
        <Link className="button-link" to="/coach">Open Coach</Link>
      </div>
      <p className="muted">
        Readiness is how prepared you are for a job's interviews today, kept separate from how well the job fits you.
        It's built from the coach's rubric scores (older answers count less) and your self-ratings. Topics with no
        evidence count at the missing-data floor, so the number can't look better than the evidence.
      </p>

      <h2>Shortlisted jobs</h2>
      {jobs.isError && <div className="callout error">{(jobs.error as Error).message}</div>}
      {jobs.data?.length === 0 && (
        <p className="muted">Nothing shortlisted yet. Shortlist jobs on the <Link to="/jobs">Jobs</Link> page to prepare for them here.</p>
      )}
      <div className="prep-jobs">
        {jobs.data?.map((j) => <PrepJobCard key={j.id} job={j} />)}
      </div>

      <h2>Your topics</h2>
      <p className="muted small">
        Rate yourself 0-5 to give the coach a starting point. A self-rating counts as half of one fresh coach answer.
      </p>
      {topics.data && <TopicTable topics={topics.data} />}

      <h2>Recent coach sessions</h2>
      {sessions.data?.length === 0 && <p className="muted">No sessions yet.</p>}
      {!!sessions.data?.length && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Session</th><th>Job</th><th>Answers</th><th>Readiness</th><th>Started</th></tr></thead>
            <tbody>
              {sessions.data.slice(0, 10).map((s) => (
                <tr key={s.id}>
                  <td><Link to={`/coach/${s.id}`}>{MODE_LABEL[s.mode]}{s.round_label ? ` · ${s.round_label}` : ""}{s.topic_label ? ` · ${s.topic_label}` : ""}</Link>
                    {s.status === "active" && <span className="badge warn" style={{ marginLeft: 6 }}>in progress</span>}</td>
                  <td className="small">{s.job ? `${s.job.title} · ${s.job.company}` : <span className="muted">General</span>}</td>
                  <td className="num">{s.answers}</td>
                  <td className="small">{s.readiness_after != null ? `${s.readiness_before ?? "—"} → ${s.readiness_after}` : "—"}</td>
                  <td className="small muted">{ago(s.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function PrepJobCard({ job }: { job: PrepJob }) {
  const [open, setOpen] = useState(false);
  const b = job.readiness_breakdown;
  const label = Object.fromEntries(b.topics.map((t) => [t.topic, t.label]));
  return (
    <section className="card">
      <div className="prep-job-head">
        <div>
          <div className="muted small">{job.company}{job.status !== "open" && <> · <span className="error-text">posting closed</span></>}</div>
          <strong>{job.title}</strong>
        </div>
        <div className="prep-score">
          <div className={`score-big ${scoreClass(job.readiness)}`}>{job.readiness ?? "—"}</div>
          <div className="muted tiny">{job.readiness == null ? "not assessed yet" : `readiness · ${b.coverage}% backed by evidence`}</div>
        </div>
      </div>
      <div className="small">
        <span className="muted">Biggest gaps: </span>
        {b.top_gaps.length ? b.top_gaps.map((g) => <span key={g} className="chip skill-miss">{label[g]}</span>) : "none"}
        <span className="muted"> · about {b.prep_hours_est} h of prep (rough estimate)</span>
      </div>
      <div className="row">
        <Link className="button-link primary" to={`/coach?mode=readiness&job=${job.id}`}>Readiness check</Link>
        <Link className="button-link" to={`/coach?mode=mock&job=${job.id}`}>Mock round</Link>
        <button className="secondary" onClick={() => setOpen(!open)}>{open ? "Hide topics" : "Show topics"}</button>
      </div>
      {open && (
        <table className="breakdown">
          <tbody>
            {b.topics.map((t) => (
              <tr key={t.topic}>
                <td>{t.label}<div className="muted tiny">{t.evidence ? `${t.evidence} coach answer${t.evidence > 1 ? "s" : ""}` : t.known ? "self-rating only" : "no evidence"}</div></td>
                <td className="muted small">{t.weight}%</td>
                <td className="bar-cell"><div className="bar"><div className={`bar-fill ${t.known ? "" : "unknown"}`} style={{ width: `${t.score}%` }} /></div></td>
                <td className="num">{t.known ? t.score : <span className="muted" title="No evidence: counted at the floor value">{t.score}?</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function TopicTable({ topics }: { topics: TopicProficiency[] }) {
  const qc = useQueryClient();
  const rate = useMutation({
    mutationFn: ({ topic, rating }: { topic: string; rating: number | null }) => coachApi.setSelfRating(topic, rating),
    onSuccess: () => {
      for (const k of ["prep-topics", "prep-jobs", "jobs", "job", "top-picks"]) qc.invalidateQueries({ queryKey: [k] });
    },
  });
  return (
    <div className="table-wrap">
      <table className="breakdown">
        <thead><tr><th>Topic</th><th>Proficiency</th><th></th><th>Coach answers</th><th>Self-rating</th></tr></thead>
        <tbody>
          {topics.map((t) => (
            <tr key={t.topic}>
              <td>{t.label}{t.last_at && <div className="muted tiny">last scored {ago(t.last_at)}</div>}</td>
              <td className="bar-cell"><div className="bar"><div className="bar-fill" style={{ width: `${t.score ?? 0}%` }} /></div></td>
              <td className="num">{t.score ?? <span className="muted">—</span>}</td>
              <td className="num">{t.evidence}</td>
              <td>
                <select
                  aria-label={`Self-rating for ${t.label}`}
                  value={t.self_rating ?? ""}
                  disabled={rate.isPending}
                  onChange={(e) => rate.mutate({ topic: t.topic, rating: e.target.value === "" ? null : Number(e.target.value) })}
                >
                  <option value="">—</option>
                  {[0, 1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rate.isError && <div className="callout error">{(rate.error as Error).message}</div>}
    </div>
  );
}
