import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { jobsApi } from "../api";
import JobDrawer from "../components/JobDrawer";
import { ARRANGEMENT, DIFFICULTY, PROVENANCE, RECOMMENDATION, ROLE, SEGMENTS, ago, fmtDate, salaryShort, scoreClass } from "../format";

type Filters = Record<string, string>;
const SORTS: Record<string, string> = {
  fresh: "Fresh + good fit", posted: "Newest posted", oldest: "Oldest posted",
  opportunity: "Opportunity", suitability: "Suitability", salary: "Salary",
};
const DAY = 86_400_000;

const DEFAULTS: Filters = {
  q: "", role_family: "", category: "", arrangement: "", difficulty: "", min_suitability: "",
  min_salary_lpa: "", posted_within_days: "", user_status: "new", sort: "fresh",
};

export default function Jobs() {
  const [params, setParams] = useSearchParams();
  const segment = params.get("segment") ?? "IN_ONSITE_HYBRID";
  const [filters, setFilters] = useState<Filters>(DEFAULTS);
  const [openId, setOpenId] = useState<number | null>(null);

  const jobs = useQuery({
    queryKey: ["jobs", segment, filters],
    queryFn: () => jobsApi.list({ segment, ...filters }),
    placeholderData: keepPreviousData,
  });
  const overview = useQuery({ queryKey: ["overview"], queryFn: jobsApi.overview });
  const set = (k: string, v: string) => setFilters((f) => ({ ...f, [k]: v }));
  const seg = SEGMENTS.find((s) => s.key === segment)!;

  return (
    <>
      <h1>Jobs</h1>
      <div className="tabs" role="tablist">
        {SEGMENTS.map((s) => (
          <button
            key={s.key} role="tab" aria-selected={s.key === segment}
            className={`tab ${s.key === segment ? "active" : ""} ${s.key === "UNVERIFIED" ? "tab-muted" : ""}`}
            onClick={() => setParams({ segment: s.key })}
          >
            {s.label} <span className="count">{jobs.data?.segment_counts[s.key] ?? 0}</span>
          </button>
        ))}
      </div>
      <p className="muted small">{seg.hint}</p>

      <div className="filters">
        <input placeholder="Search title or company" value={filters.q} onChange={(e) => set("q", e.target.value)} />
        <Select label="Role" value={filters.role_family} onChange={(v) => set("role_family", v)} options={ROLE} />
        <Select label="Company size" value={filters.category} onChange={(v) => set("category", v)}
          options={{ 1: "Medium", 2: "Large", 3: "Highly competitive", 0: "Uncategorized" }} />
        <Select label="Arrangement" value={filters.arrangement} onChange={(v) => set("arrangement", v)} options={ARRANGEMENT} />
        <Select label="Difficulty" value={filters.difficulty} onChange={(v) => set("difficulty", v)} options={DIFFICULTY} />
        <Select label="Suitability" value={filters.min_suitability} onChange={(v) => set("min_suitability", v)}
          options={{ 80: "High (80+)", 60: "Medium+ (60+)" }} />
        <Select label="Salary" value={filters.min_salary_lpa} onChange={(v) => set("min_salary_lpa", v)}
          options={{ 25: "25+ LPA (posted)", 30: "30+ LPA (posted)", 40: "40+ LPA (posted)" }} />
        <Select label="Posted" value={filters.posted_within_days} onChange={(v) => set("posted_within_days", v)}
          options={{ 1: "Last 24h", 3: "Last 3 days", 7: "Last 7 days", 14: "Last 14 days" }} allLabel="Within limit" />
        <Select label="Status" value={filters.user_status} onChange={(v) => set("user_status", v)} allLabel="All"
          options={{ new: "New", shortlisted: "Shortlisted", skipped: "Skipped" }} allValue="all" />
        <Select label="Sort" value={filters.sort} onChange={(v) => set("sort", v)} noAll
          options={SORTS} />
        <button className="secondary" onClick={() => setFilters(DEFAULTS)}>Reset</button>
      </div>

      <p className="muted small">
        {jobs.data ? `${jobs.data.jobs.length} jobs · sorted by ${SORTS[filters.sort].toLowerCase()}` : "Loading…"}
        {filters.sort === "fresh" && " (opportunity score, weighted toward recent postings: early applicants get more replies)"}
        {overview.data && <> · postings older than {overview.data.max_posting_age_days} days are hidden unless you applied or shortlisted (<Link to="/settings">change</Link>)</>}
      </p>
      {jobs.isError && <div className="callout error">{(jobs.error as Error).message}</div>}
      <div className="table-wrap">
        <table className="jobs-table">
          <thead>
            <tr>
              <th>Company</th><th>Title</th>
              <SortTh label="Opp" title="Opportunity score (ranking)" sort={filters.sort} keys={["opportunity"]} onSort={(v) => set("sort", v)} />
              <SortTh label="Suit" title="Job suitability: fit with your profile" sort={filters.sort} keys={["suitability"]} onSort={(v) => set("sort", v)} />
              <th title="Interview readiness: measured from Phase 5">Ready</th>
              <th>WLB</th>
              <SortTh label="Salary" title="Highest posted salary first" sort={filters.sort} keys={["salary"]} onSort={(v) => set("sort", v)} />
              <th>Difficulty</th><th>Arrangement</th>
              <SortTh label="Posted" title="Click to toggle newest / oldest" sort={filters.sort} keys={["posted", "oldest"]} onSort={(v) => set("sort", v)} />
            </tr>
          </thead>
          <tbody>
            {jobs.data?.jobs.map((j) => (
              <tr key={j.id} className="clickable" onClick={() => setOpenId(j.id)}>
                <td>
                  <div>{j.company}</div>
                  <div className="muted tiny">{j.category ? `Cat ${j.category}` : "Uncategorized"}</div>
                </td>
                <td>
                  <div className="title-cell">{j.title}{j.applied && <span className="badge ok" style={{ marginLeft: 6 }}>Applied</span>}</div>
                  <div className="muted tiny">{ROLE[j.role_family]} · {RECOMMENDATION[j.recommendation ?? ""]}</div>
                </td>
                <td className={`num ${scoreClass(j.opportunity)}`}>{j.opportunity ?? "—"}</td>
                <td className={`num ${scoreClass(j.suitability)}`}>{j.suitability ?? "—"}</td>
                <td className="num muted">{j.readiness ?? "—"}</td>
                <td className="small">{j.wlb_rating === "insufficient" ? <span className="muted">No data</span> : j.wlb_rating}</td>
                <td className="small nowrap" title={PROVENANCE[j.salary?.provenance ?? "not_disclosed"].label}>{salaryShort(j.salary)}</td>
                <td className="small">{DIFFICULTY[j.difficulty ?? ""]}</td>
                <td className="small">{ARRANGEMENT[j.arrangement]}</td>
                <td className="small nowrap"><Posted iso={j.posted_at ?? j.first_seen_at} /></td>
              </tr>
            ))}
            {jobs.data && jobs.data.jobs.length === 0 && (
              <tr><td colSpan={10} className="muted empty">No jobs match. Try resetting filters, or run discovery from Overview.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {openId !== null && <JobDrawer jobId={openId} onClose={() => setOpenId(null)} />}
    </>
  );
}

function Select({ label, value, onChange, options, allLabel = "Any", allValue = "", noAll = false }: {
  label: string; value: string; onChange: (v: string) => void; options: Record<string | number, string>;
  allLabel?: string; allValue?: string; noAll?: boolean;
}) {
  return (
    <label className="select">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {!noAll && <option value={allValue}>{allLabel}</option>}
        {Object.entries(options).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
    </label>
  );
}

function SortTh({ label, title, sort, keys, onSort }: {
  label: string; title: string; sort: string; keys: string[]; onSort: (v: string) => void;
}) {
  const i = keys.indexOf(sort);
  const next = i === -1 ? keys[0] : keys[(i + 1) % keys.length];
  const arrow = i === -1 ? "" : keys[i] === "oldest" ? " ↑" : " ↓";
  return (
    <th title={title} aria-sort={i === -1 ? "none" : keys[i] === "oldest" ? "ascending" : "descending"}>
      <button className="th-sort" onClick={() => onSort(next)}>{label}{arrow}</button>
    </th>
  );
}

function Posted({ iso }: { iso: string | null }) {
  if (!iso) return <span className="muted">—</span>;
  const days = (Date.now() - new Date(iso).getTime()) / DAY;
  return (
    <span title={`Posted ${fmtDate(iso)}`}>
      <span className={days > 30 ? "muted" : ""}>{ago(iso)}</span>
      {days <= 3 && <span className="badge ok" style={{ marginLeft: 4 }}>New</span>}
      {days > 30 && <span className="badge" style={{ marginLeft: 4 }} title="Shown because you applied or shortlisted it. Older postings are often filled or get fewer replies">Old</span>}
    </span>
  );
}
