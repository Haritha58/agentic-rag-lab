import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { appsApi, jobsApi, type ScorePart } from "../api";
import {
  ARRANGEMENT, CATEGORY, DIFFICULTY, PROVENANCE, RECOMMENDATION, ROLE, SEGMENTS, lpa, money, scoreClass,
} from "../format";

const PART_LABELS: Record<string, string> = {
  technical: "Technical skills", experience: "Experience level", transferable: "Transferable backend skills",
  role_direction: "Role direction (AI first)", location: "Location fit", qualifications: "Qualifications",
  technical_match: "Technical & experience match", work_life_balance: "Work-life balance", compensation: "Compensation",
  company_stability: "Company stability", growth_ai_exposure: "Career growth & AI exposure",
  arrangement_location: "Work arrangement & location", interview_accessibility: "Interview accessibility",
};

export default function JobDrawer({ jobId, onClose }: { jobId: number; onClose: () => void }) {
  const qc = useQueryClient();
  const job = useQuery({ queryKey: ["job", jobId], queryFn: () => jobsApi.get(jobId) });
  const application = useQuery({ queryKey: ["applications", { job: jobId }], queryFn: () => appsApi.list({ job_id: jobId }) });
  const applied = application.data?.[0];
  const setStatus = useMutation({
    mutationFn: (status: string) => jobsApi.setStatus(jobId, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["job", jobId] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      qc.invalidateQueries({ queryKey: ["top-picks"] });
    },
  });

  const j = job.data;
  const s = j?.salary;
  const evidence = Object.entries(j?.evidence ?? {}).filter(([k, v]) => k !== "eligibility" && typeof v === "string");

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} aria-label="Job details">
        <button className="close" onClick={onClose} aria-label="Close">×</button>
        {job.isLoading && <p className="muted">Loading…</p>}
        {job.isError && <div className="callout error">{(job.error as Error).message}</div>}
        {j && (
          <>
            <div className="muted small">
              {j.company}
              {j.category && <> · {CATEGORY[j.category]}{j.category_source === "curated_estimate" ? " (estimated)" : ""}</>}
              {j.size_band && <> · {j.size_band} employees</>}
            </div>
            <h2 className="drawer-title">{j.title}</h2>
            <div className="chips-row">
              <span className="chip">{SEGMENTS.find((x) => x.key === j.segment)?.label}</span>
              <span className="chip">{ARRANGEMENT[j.arrangement]}</span>
              <span className="chip">{ROLE[j.role_family]}</span>
              {j.location && <span className="chip">{j.location}</span>}
            </div>

            <div className="drawer-actions">
              {j.user_status !== "shortlisted" && <button onClick={() => setStatus.mutate("shortlisted")}>Shortlist</button>}
              {j.user_status !== "skipped" && <button className="secondary" onClick={() => setStatus.mutate("skipped")}>Skip</button>}
              {j.user_status !== "new" && <button className="secondary" onClick={() => setStatus.mutate("new")}>Move back to new</button>}
              <a className="button-link" href={j.url} target="_blank" rel="noreferrer">Open posting ↗</a>
              <Link className="button-link" to={`/coach?mode=readiness&job=${j.id}`}>Prepare with Coach</Link>
              {applied
                ? <Link className="button-link" to={`/applications?open=${applied.id}`}>Applied · view application</Link>
                : <Link className="button-link" to={`/applications?job=${j.id}`}>I applied: log it</Link>}
            </div>
            <p className="muted small">Source: {j.source_label}{j.source === "remoteok" && <> (via <a href="https://remoteok.com" target="_blank" rel="noreferrer">Remote OK</a>)</>}</p>

            <div className="score-cards">
              <ScoreCard label="Opportunity" value={j.opportunity} sub={`${j.data_coverage}% backed by data`} />
              <ScoreCard label="Suitability" value={j.suitability} sub="Fit with your profile" />
              <ScoreCard label="Readiness" value={j.readiness}
                sub={j.readiness == null ? "Not assessed yet: run a readiness check" : `${j.readiness_breakdown?.coverage ?? 0}% backed by evidence`} />
            </div>
            <p>
              <span className={`badge ${j.recommendation === "apply_now" ? "ok" : j.recommendation === "skip" ? "" : "warn"}`}>
                {RECOMMENDATION[j.recommendation ?? ""]}
              </span>{" "}
              <span className="muted small">Interview difficulty: {DIFFICULTY[j.difficulty ?? ""]}</span>
            </p>
            {!!j.difficulty_evidence?.length && <ul className="small muted tight">{j.difficulty_evidence.map((e) => <li key={e}>{e}</li>)}</ul>}

            {!!j.rejection_risks?.length && (
              <>
                <h3>Possible rejection reasons</h3>
                <ul className="tight">{j.rejection_risks.map((r) => <li key={r}>{r}</li>)}</ul>
              </>
            )}

            <h3>Skills</h3>
            <SkillRow label="From your work" skills={j.existing_skills} kind="ok" />
            <SkillRow label="From your learning" skills={j.learning_skills} kind="learn" />
            <SkillRow label="Missing" skills={j.missing_skills} kind="miss" />

            <h3>Salary</h3>
            {s && s.provenance !== "not_disclosed" ? (
              <div className="small">
                <div>
                  {PROVENANCE[s.provenance].icon} {money(s.min, s.currency)} – {money(s.max, s.currency)} / year
                  {s.currency !== "INR" && s.inr_max && (
                    <> ≈ {lpa(s.inr_min)}–{lpa(s.inr_max)} LPA <span className="muted">(at {s.fx_rate} INR/{s.currency}, {s.fx_date})</span></>
                  )}
                </div>
                <div className="muted">{PROVENANCE[s.provenance].label}: “{s.source_text}”</div>
                {j.segment === "INTL_RELOCATION" && <div className="muted">Gross pay. Tax and cost of living aren't applied yet.</div>}
              </div>
            ) : <p className="muted small">— Not disclosed in the posting.</p>}

            {evidence.length > 0 && (
              <>
                <h3>Why it's in this tab</h3>
                {evidence.map(([k, v]) => <p key={k} className="evidence"><strong>{k}:</strong> {String(v)}</p>)}
              </>
            )}

            {j.opportunity_breakdown && <Breakdown title="Opportunity score" parts={j.opportunity_breakdown} />}
            {j.suitability_breakdown && <Breakdown title="Suitability score" parts={j.suitability_breakdown} />}

            <h3>Job description</h3>
            <div className="jd">{j.description || "No description provided by the source."}</div>
          </>
        )}
      </aside>
    </div>
  );
}

function ScoreCard({ label, value, sub }: { label: string; value: number | null; sub: string }) {
  return (
    <div className="score-card">
      <div className="muted small">{label}</div>
      <div className={`score-big ${scoreClass(value)}`}>{value ?? "—"}</div>
      <div className="muted tiny">{sub}</div>
    </div>
  );
}

function SkillRow({ label, skills, kind }: { label: string; skills?: string[]; kind: string }) {
  if (!skills?.length) return null;
  return (
    <div className="skill-row">
      <span className="muted small">{label}</span>
      <div>{skills.map((s) => <span key={s} className={`chip skill-${kind}`}>{s}</span>)}</div>
    </div>
  );
}

function Breakdown({ title, parts }: { title: string; parts: Record<string, ScorePart> }) {
  return (
    <>
      <h3>{title}</h3>
      <table className="breakdown">
        <tbody>
          {/* Postgres JSONB doesn't keep key order, so show factors in the weight table's order. */}
          {Object.keys(PART_LABELS).filter((k) => k in parts).map((k) => [k, parts[k]] as const).map(([k, p]) => (
            <tr key={k}>
              <td>{PART_LABELS[k] ?? k}<div className="muted tiny">{p.note}</div></td>
              <td className="muted small">{p.weight}%</td>
              <td className="bar-cell">
                <div className="bar"><div className={`bar-fill ${p.known ? "" : "unknown"}`} style={{ width: `${p.score}%` }} /></div>
              </td>
              <td className="num">{p.known ? p.score : <span className="muted" title="No data: scored at the floor value">{p.score}?</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
