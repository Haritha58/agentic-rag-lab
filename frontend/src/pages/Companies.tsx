import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { jobsApi } from "../api";
import { CATEGORY } from "../format";

const SECTIONS = [
  { cat: 1, title: "Medium-sized companies", hint: "Highest priority while you rebuild interview experience." },
  { cat: 2, title: "Large established companies", hint: "Stage 3 targets." },
  { cat: 3, title: "Highly competitive companies", hint: "Stage 4 targets, after you've gained interview confidence." },
  { cat: null, title: "Uncategorized", hint: "Mostly companies found on job boards. Set a category so they count toward your 60/30/10 mix." },
];

export default function Companies() {
  const qc = useQueryClient();
  const companies = useQuery({ queryKey: ["companies"], queryFn: jobsApi.companies });
  const [onlyWithJobs, setOnlyWithJobs] = useState(true);
  const update = useMutation({
    mutationFn: ({ id, category }: { id: number; category: number | null }) => jobsApi.setCompany(id, { category }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["companies"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["top-picks"] });
    },
  });

  const rows = (companies.data ?? []).filter((c) => !onlyWithJobs || c.open_jobs > 0);

  return (
    <>
      <div className="page-head">
        <h1>Companies</h1>
        <label className="inline-check">
          <input type="checkbox" checked={onlyWithJobs} onChange={(e) => setOnlyWithJobs(e.target.checked)} /> Only with open jobs
        </label>
      </div>
      <p className="muted small">
        Categories and sizes marked <em>estimated</em> are my curated guesses; change any you know better. Size alone
        doesn't decide difficulty or work-life balance. Each company is rated on its own evidence (research arrives in Phase 2b).
      </p>
      {update.isError && <div className="callout error">{(update.error as Error).message}</div>}
      {SECTIONS.map((s) => {
        const list = rows.filter((c) => c.category === s.cat);
        if (!list.length) return null;
        return (
          <section key={String(s.cat)}>
            <h2>{s.title} <span className="muted small">({list.length})</span></h2>
            <p className="muted small">{s.hint}</p>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Company</th><th>Category</th><th>Size</th><th>Work-life balance</th><th>Source</th><th className="num">Open jobs</th></tr></thead>
                <tbody>
                  {list.map((c) => (
                    <tr key={c.id}>
                      <td>{c.name}</td>
                      <td>
                        <select
                          value={c.category ?? ""}
                          onChange={(e) => update.mutate({ id: c.id, category: e.target.value ? Number(e.target.value) : null })}
                        >
                          <option value="">Uncategorized</option>
                          {[1, 2, 3].map((n) => <option key={n} value={n}>{CATEGORY[n]}</option>)}
                        </select>
                        {c.category_source === "curated_estimate" && <span className="muted tiny"> estimated</span>}
                      </td>
                      <td className="small">{c.size_band ?? "—"}{c.size_source === "curated_estimate" && <span className="muted tiny"> est.</span>}</td>
                      <td className="small muted">{c.wlb_rating === "insufficient" ? "Insufficient information" : c.wlb_rating}</td>
                      <td className="small muted">{c.on_watchlist ? `Watchlist (${c.ats})` : "Job boards"}</td>
                      <td className="num">{c.open_jobs}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
    </>
  );
}
