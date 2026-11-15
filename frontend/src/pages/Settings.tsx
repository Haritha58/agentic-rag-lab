import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, jobsApi } from "../api";

const SECTIONS: { key: string; title: string; hint: string; total?: boolean }[] = [
  { key: "opportunity_weights", title: "Opportunity score weights", hint: "Must add up to 100.", total: true },
  { key: "company_allocation", title: "Application mix by company size", hint: "Must add up to 100.", total: true },
  { key: "compensation", title: "Compensation (LPA)", hint: "Drives the compensation sub-score and application answers." },
  { key: "scoring", title: "Scoring", hint: "missing_data_floor is the score an unknown factor gets (never above neutral)." },
  { key: "segments", title: "Job segments", hint: "Which dashboard tabs are active." },
  { key: "discovery", title: "Job discovery", hint: "Postings older than max_posting_age_days are skipped and hidden (1-365). Jobs you applied to or shortlisted always stay." },
  { key: "documents", title: "Documents", hint: "main_resume_path is the resume you send by default (currently v5)." },
  { key: "llm", title: "LLM", hint: "Model aliases per tier, and a daily call cap that protects your Pro plan limits." },
];

export default function Settings() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  return (
    <>
      <h1>Settings</h1>
      <LlmCheck />
      {settings.isError && <div className="callout error">{(settings.error as Error).message}</div>}
      {settings.data &&
        SECTIONS.map((s) => (
          <SectionForm key={s.key} section={s.key} title={s.title} hint={s.hint} total={s.total} initial={settings.data[s.key]} />
        ))}
    </>
  );
}

function SectionForm({ section, title, hint, total, initial }: {
  section: string; title: string; hint: string; total?: boolean;
  initial: Record<string, number | string | boolean>;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState(initial);
  useEffect(() => setForm(initial), [initial]);

  const save = useMutation({
    mutationFn: async () => {
      const saved = await api.saveSettings(section, form);
      await jobsApi.recompute();  // weights, floor and pay targets all change scores
      return saved;
    },
    onSuccess: () => {
      for (const k of ["settings", "jobs", "top-picks"]) qc.invalidateQueries({ queryKey: [k] });
    },
  });

  const sum = Object.values(form).reduce<number>((acc, v) => acc + (typeof v === "number" ? v : 0), 0);

  return (
    <section className="card">
      <div className="page-head">
        <h2>{title}</h2>
        {total && <span className={`badge ${sum === 100 ? "ok" : "warn"}`}>total {sum}</span>}
      </div>
      <p className="muted small">{hint}</p>
      <div className="form-grid">
        {Object.entries(form).map(([field, value]) => (
          <label key={field}>
            <span>{field.replace(/_/g, " ")}</span>
            {typeof value === "boolean" ? (
              <input type="checkbox" checked={value} onChange={(e) => setForm({ ...form, [field]: e.target.checked })} />
            ) : (
              <input
                type={typeof value === "number" ? "number" : "text"}
                step="any"
                value={value}
                onChange={(e) =>
                  setForm({ ...form, [field]: typeof value === "number" ? Number(e.target.value) : e.target.value })
                }
              />
            )}
          </label>
        ))}
      </div>
      <div className="row">
        <button onClick={() => save.mutate()} disabled={save.isPending}>Save</button>
        {save.isError && <span className="error-text">{(save.error as Error).message}</span>}
        {save.isSuccess && <span className="ok-text">Saved, jobs re-scored</span>}
      </div>
    </section>
  );
}

function LlmCheck() {
  const qc = useQueryClient();
  const ping = useMutation({ mutationFn: api.ping, onSettled: () => qc.invalidateQueries({ queryKey: ["usage"] }) });
  return (
    <section className="card">
      <div className="page-head">
        <h2>Claude connection</h2>
        <button onClick={() => ping.mutate()} disabled={ping.isPending}>
          {ping.isPending ? "Testing…" : "Test connection"}
        </button>
      </div>
      <p className="muted small">Makes one tiny call through Claude Code on this Mac (counts toward your Pro usage).</p>
      {ping.data?.ok && <div className="callout ok">Working. Model {ping.data.model} replied {JSON.stringify(ping.data.reply)}.</div>}
      {ping.data && !ping.data.ok && <div className="callout error">{ping.data.error}</div>}
      {ping.isError && <div className="callout error">{(ping.error as Error).message}</div>}
    </section>
  );
}
