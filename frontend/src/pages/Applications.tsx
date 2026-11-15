import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { appsApi, coachApi, jobsApi, type Application, type JobEmail, type ApplicationsMeta, type InterviewRound } from "../api";
import { APP_STATUS_TONE, EMAIL_CATEGORY, ROUND_STATUS_TONE, fmtDate, fmtDateTime, toLocalInput } from "../format";

const ACTIVE = ["applied", "viewed", "screening", "interviewing", "offer", "no_response"];
const SORTS: Record<string, string> = {
  applied_new: "Applied: newest first", applied_old: "Applied: oldest first", updated: "Last updated",
  next_round: "Next round soonest", follow_up: "Follow-up due first", company: "Company A–Z",
};

function sortApps(list: Application[], by: string): Application[] {
  const t = (s: string | null | undefined, empty: number) => (s ? new Date(s).getTime() : empty);
  const cmp: Record<string, (a: Application, b: Application) => number> = {
    applied_new: (a, b) => t(b.applied_at, 0) - t(a.applied_at, 0) || b.id - a.id,
    applied_old: (a, b) => t(a.applied_at, 0) - t(b.applied_at, 0) || a.id - b.id,
    updated: (a, b) => t(b.updated_at, 0) - t(a.updated_at, 0),
    next_round: (a, b) => t(a.next_round?.scheduled_at, Infinity) - t(b.next_round?.scheduled_at, Infinity),
    follow_up: (a, b) => Number(b.follow_up_due) - Number(a.follow_up_due) || t(a.follow_up_on, Infinity) - t(b.follow_up_on, Infinity),
    company: (a, b) => a.company.localeCompare(b.company) || a.title.localeCompare(b.title),
  };
  return [...list].sort(cmp[by]);
}

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    for (const k of ["applications", "application", "prep-jobs", "pending-emails"]) qc.invalidateQueries({ queryKey: [k] });
  };
}

export default function Applications() {
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ["applications-meta"], queryFn: appsApi.meta });
  const apps = useQuery({ queryKey: ["applications"], queryFn: () => appsApi.list() });
  const [filter, setFilter] = useState("active");
  const [q, setQ] = useState("");
  const [channel, setChannel] = useState("");
  const [sort, setSort] = useState("applied_new");
  const [adding, setAdding] = useState(params.get("job") !== null);
  const openId = params.get("open");

  const all = apps.data ?? [];
  const needle = q.trim().toLowerCase();
  const shown = sortApps(all.filter((a) =>
    (filter === "all" || (filter === "active" ? ACTIVE.includes(a.status) : a.status === filter))
    && (!channel || a.channel === channel)
    && (!needle || `${a.company} ${a.title}`.toLowerCase().includes(needle))
  ), sort);
  const due = all.filter((a) => a.follow_up_due).length;
  const upcoming = all.filter((a) => a.next_round).length;

  const open = (id: number | null) => {
    const next = new URLSearchParams(params);
    if (id === null) next.delete("open"); else next.set("open", String(id));
    next.delete("job");
    setParams(next);
  };

  return (
    <>
      <div className="page-head">
        <h1>Applications</h1>
        <button onClick={() => setAdding(!adding)}>{adding ? "Close" : "Log an application"}</button>
      </div>
      <p className="muted">
        Log each application after you submit it yourself. Add every interview round as it gets scheduled: there's no
        limit on rounds. Each status change is kept with what caused it.
      </p>

      {adding && meta.data && (
        <NewApplicationForm meta={meta.data} jobParam={params.get("job")} onDone={(a) => { setAdding(false); open(a.id); }} />
      )}

      <PendingEmails onOpen={open} />

      <div className="tiles">
        <Tile label="Active" value={all.filter((a) => ACTIVE.includes(a.status)).length} />
        <Tile label="Interviewing" value={all.filter((a) => a.status === "interviewing").length} />
        <Tile label="Upcoming rounds" value={upcoming} />
        <Tile label="Follow-ups due" value={due} tone={due ? "warn" : ""} />
        <Tile label="Offers" value={all.filter((a) => a.status === "offer" || a.status === "accepted").length} />
      </div>

      <div className="filters">
        <input placeholder="Search company or role" value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="select">
          Show
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="active">Active</option>
            <option value="all">All</option>
            {Object.entries(meta.data?.statuses ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="select">
          Applied via
          <select value={channel} onChange={(e) => setChannel(e.target.value)}>
            <option value="">Any</option>
            {Object.entries(meta.data?.channels ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="select">
          Sort
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            {Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
      </div>

      {apps.isError && <div className="callout error">{(apps.error as Error).message}</div>}
      {apps.data && shown.length === 0 && (
        <p className="muted">
          {all.length === 0 ? "No applications logged yet. After you apply somewhere, log it here." : "Nothing in this view."}
        </p>
      )}
      {shown.length > 0 && meta.data && (
        <div className="table-wrap">
          <table className="jobs-table">
            <thead>
              <tr><th>Role</th><th>Status</th><th>Applied</th><th>Rounds</th><th>Next round</th><th>Follow-up</th></tr>
            </thead>
            <tbody>
              {shown.map((a) => (
                <tr key={a.id} className="clickable" onClick={() => open(a.id)}>
                  <td className="title-cell"><strong>{a.title}</strong><div className="muted small">{a.company}</div></td>
                  <td><span className={`badge ${APP_STATUS_TONE[a.status]}`}>{meta.data.statuses[a.status]}</span></td>
                  <td className="small">{fmtDate(a.applied_at)}<div className="muted tiny">{meta.data.channels[a.channel]}</div></td>
                  <td className="small">{a.rounds_total ? `${a.rounds_cleared} of ${a.rounds_total} cleared` : <span className="muted">—</span>}</td>
                  <td className="small">
                    {a.next_round
                      ? <>{fmtDateTime(a.next_round.scheduled_at)}<div className="muted tiny">Round {a.next_round.round_no} · {a.next_round.round_type_label}</div></>
                      : <span className="muted">—</span>}
                  </td>
                  <td className="small">
                    {a.follow_up_due ? <span className="badge warn">Due</span>
                      : a.follow_up_on && ACTIVE.includes(a.status) && a.status !== "interviewing" && a.status !== "offer"
                        ? fmtDate(a.follow_up_on) : <span className="muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {openId && meta.data && <ApplicationDrawer id={Number(openId)} meta={meta.data} onClose={() => open(null)} />}
    </>
  );
}

function Tile({ label, value, tone = "" }: { label: string; value: number; tone?: string }) {
  return (
    <div className="tile">
      <div className={`tile-value ${tone === "warn" ? "warn-text" : ""}`}>{value}</div>
      <div className="tile-label">{label}</div>
    </div>
  );
}

function NewApplicationForm({ meta, jobParam, onDone }: { meta: ApplicationsMeta; jobParam: string | null; onDone: (a: Application) => void }) {
  const invalidate = useInvalidate();
  const jobs = useQuery({ queryKey: ["prep-jobs"], queryFn: coachApi.prepJobs });
  const apps = useQuery({ queryKey: ["applications"], queryFn: () => appsApi.list() });
  const applied = new Set((apps.data ?? []).map((a) => a.job_id));
  // A job opened from the Jobs page may not be shortlisted, so it isn't in the prep list.
  const fromJob = useQuery({
    queryKey: ["job", Number(jobParam)], queryFn: () => jobsApi.get(Number(jobParam)),
    enabled: !!jobParam && !!jobs.data && !jobs.data.some((j) => String(j.id) === jobParam),
  });
  const [jobId, setJobId] = useState(jobParam ?? "");
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [channel, setChannel] = useState("company_site");
  const [resume, setResume] = useState(meta.main_resume || meta.resume_versions[0] || "");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState("");

  const create = useMutation({
    mutationFn: () => appsApi.create({
      job_id: jobId ? Number(jobId) : null,
      company: jobId ? undefined : company, title: jobId ? undefined : title, url: url || null,
      channel, resume_version: resume || null, applied_at: date, notes: notes || null,
    }),
    onSuccess: (a) => { invalidate(); onDone(a); },
  });

  return (
    <section className="card">
      <h2>Log an application</h2>
      <div className="form-grid">
        <label>
          Job
          <select value={jobId} onChange={(e) => setJobId(e.target.value)}>
            <option value="">Not in JobPilot (type it below)</option>
            {fromJob.data && <option value={fromJob.data.id}>{fromJob.data.title} · {fromJob.data.company}</option>}
            {jobs.data?.filter((j) => !applied.has(j.id) || String(j.id) === jobId)
              .map((j) => <option key={j.id} value={j.id}>{j.title} · {j.company}</option>)}
          </select>
        </label>
        {!jobId && (
          <>
            <label>Company<input type="text" value={company} onChange={(e) => setCompany(e.target.value)} /></label>
            <label>Role<input type="text" value={title} onChange={(e) => setTitle(e.target.value)} /></label>
            <label>Job link (optional)<input type="text" value={url} onChange={(e) => setUrl(e.target.value)} /></label>
          </>
        )}
        <label>
          Applied via
          <select value={channel} onChange={(e) => setChannel(e.target.value)}>
            {Object.entries(meta.channels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label>
          Resume sent
          <select value={resume} onChange={(e) => setResume(e.target.value)}>
            <option value="">Not recorded</option>
            {meta.resume_versions.map((r) => <option key={r} value={r}>{r === meta.main_resume ? `${r} (main)` : r}</option>)}
          </select>
        </label>
        <label>Applied on<input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        <label>Notes (optional)<input type="text" value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
      </div>
      <div className="row">
        <button onClick={() => create.mutate()} disabled={create.isPending || (!jobId && !(company.trim() && title.trim()))}>
          {create.isPending ? "Saving…" : "Save application"}
        </button>
        <span className="muted small">A follow-up reminder is set for 7 days later. You can change it.</span>
      </div>
      {create.isError && <div className="callout error">{(create.error as Error).message}</div>}
    </section>
  );
}

function ApplicationDrawer({ id, meta, onClose }: { id: number; meta: ApplicationsMeta; onClose: () => void }) {
  const invalidate = useInvalidate();
  const q = useQuery({ queryKey: ["application", id], queryFn: () => appsApi.get(id) });
  const a = q.data;
  const [status, setStatus] = useState("");
  const [statusNote, setStatusNote] = useState("");
  const [notes, setNotes] = useState<string | null>(null);

  const update = useMutation({
    mutationFn: (body: Record<string, unknown>) => appsApi.update(id, body),
    onSuccess: () => { invalidate(); setStatus(""); setStatusNote(""); setNotes(null); },
  });
  const remove = useMutation({ mutationFn: () => appsApi.remove(id), onSuccess: () => { invalidate(); onClose(); } });

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} aria-label="Application details">
        <button className="close" onClick={onClose} aria-label="Close">×</button>
        {q.isLoading && <p className="muted">Loading…</p>}
        {q.isError && <div className="callout error">{(q.error as Error).message}</div>}
        {a && (
          <>
            <div className="muted small">{a.company}</div>
            <h2 className="drawer-title">{a.title}</h2>
            <div className="chips-row">
              <span className={`badge ${APP_STATUS_TONE[a.status]}`}>{meta.statuses[a.status]}</span>
              <span className="chip">Applied {fmtDate(a.applied_at)} via {meta.channels[a.channel]}</span>
              {a.resume_version && <span className="chip">{a.resume_version}</span>}
            </div>
            <div className="drawer-actions">
              {a.url && <a className="button-link" href={a.url} target="_blank" rel="noreferrer">Open posting ↗</a>}
              {a.job_id && <Link className="button-link" to={`/coach?mode=readiness&job=${a.job_id}`}>Readiness check</Link>}
            </div>

            <h3>Status</h3>
            <div className="filters">
              <label className="select">
                Change to
                <select value={status} onChange={(e) => setStatus(e.target.value)}>
                  <option value="">—</option>
                  {Object.entries(meta.statuses).filter(([k]) => k !== a.status).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
              <label className="select">
                Why (optional)
                <input type="text" value={statusNote} placeholder="e.g. Rejection email on 20 Nov" onChange={(e) => setStatusNote(e.target.value)} />
              </label>
              <button disabled={!status || update.isPending} onClick={() => update.mutate({ status, status_note: statusNote || null })}>Update</button>
            </div>
            <div className="filters">
              <label className="select">
                Follow up on
                <input type="date" value={a.follow_up_on ?? ""} onChange={(e) => update.mutate({ follow_up_on: e.target.value || null })} />
              </label>
              {a.follow_up_due && <span className="badge warn">Follow-up due</span>}
            </div>
            {update.isError && <div className="callout error">{(update.error as Error).message}</div>}

            <h3>Interview rounds</h3>
            {!a.rounds?.length && <p className="muted small">No rounds yet. Add the first one when it gets scheduled.</p>}
            {a.rounds?.map((r) => <RoundCard key={r.id} round={r} jobId={a.job_id} meta={meta} />)}
            <AddRound appId={a.id} next={(a.rounds?.length ?? 0) + 1} meta={meta} />

            {!!a.emails?.length && (
              <>
                <h3>Emails</h3>
                {a.emails.map((e) => <EmailRow key={e.id} email={e} />)}
              </>
            )}

            <h3>Notes</h3>
            <textarea
              className="notes" rows={3} value={notes ?? a.notes ?? ""}
              placeholder="Recruiter name, salary discussed, anything to remember"
              onChange={(e) => setNotes(e.target.value)}
            />
            {notes !== null && notes !== (a.notes ?? "") && (
              <button onClick={() => update.mutate({ notes })} disabled={update.isPending}>Save notes</button>
            )}

            <h3>History</h3>
            <ul className="timeline">
              {a.events?.map((e) => (
                <li key={e.id}>
                  <span className="muted tiny">{fmtDateTime(e.at)}</span>{" "}
                  {e.from_status ? <>{meta.statuses[e.from_status]} → </> : null}<strong>{meta.statuses[e.to_status]}</strong>
                  <span className="muted small"> · {e.evidence_type === "email" ? "from an email" : "by you"}{e.note ? ` · ${e.note}` : ""}</span>
                </li>
              ))}
            </ul>

            <p>
              <button className="secondary danger" disabled={remove.isPending}
                onClick={() => { if (confirm(`Delete the application to ${a.company}, with its rounds and history? This can't be undone.`)) remove.mutate(); }}>
                Delete application
              </button>
            </p>
          </>
        )}
      </aside>
    </div>
  );
}

function RoundCard({ round: r, jobId, meta }: { round: InterviewRound; jobId: number | null; meta: ApplicationsMeta }) {
  const invalidate = useInvalidate();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState({
    label: r.label ?? "", interviewer: r.interviewer ?? "", questions: r.questions ?? "", feedback: r.feedback ?? "",
    scheduled_at: toLocalInput(r.scheduled_at), self_rating: r.self_rating ? String(r.self_rating) : "",
  });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => appsApi.updateRound(r.id, body),
    onSuccess: () => { invalidate(); setOpen(false); },
  });
  const remove = useMutation({ mutationFn: () => appsApi.removeRound(r.id), onSuccess: invalidate });
  const prep = new URLSearchParams({ mode: "mock", round: r.coach_round });
  if (jobId) prep.set("job", String(jobId));
  if (r.scheduled_at) prep.set("date", r.scheduled_at.slice(0, 10));

  return (
    <div className="round-card">
      <div className="round-head">
        <div>
          <strong>Round {r.round_no} · {r.round_type_label}</strong>{r.label && <span className="muted"> · {r.label}</span>}
          <div className="muted small">
            {fmtDateTime(r.scheduled_at)}{r.mode && ` · ${r.mode}`}{r.interviewer && ` · with ${r.interviewer}`}
          </div>
        </div>
        <select aria-label={`Status of round ${r.round_no}`} value={r.status} disabled={save.isPending}
          className={`badge-select ${ROUND_STATUS_TONE[r.status]}`}
          onChange={(e) => save.mutate({ status: e.target.value })}>
          {Object.entries(meta.round_statuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
      {!open && (r.questions || r.feedback) && (
        <div className="small">
          {r.questions && <p><span className="muted">Asked: </span>{r.questions}</p>}
          {r.feedback && <p><span className="muted">Feedback: </span>{r.feedback}</p>}
        </div>
      )}
      <div className="row">
        {r.status === "scheduled" && <Link className="button-link primary" to={`/coach?${prep}`}>Prepare with Coach</Link>}
        <button className="secondary" onClick={() => setOpen(!open)}>{open ? "Cancel" : "Edit details"}</button>
        <button className="secondary danger" disabled={remove.isPending}
          onClick={() => { if (confirm(`Delete round ${r.round_no}?`)) remove.mutate(); }}>Delete</button>
      </div>
      {open && (
        <div className="form-grid">
          <label>Date and time<input type="datetime-local" value={draft.scheduled_at} onChange={(e) => setDraft({ ...draft, scheduled_at: e.target.value })} /></label>
          <label>Title (optional)<input type="text" value={draft.label} placeholder="e.g. DSA with team lead" onChange={(e) => setDraft({ ...draft, label: e.target.value })} /></label>
          <label>Interviewer<input type="text" value={draft.interviewer} onChange={(e) => setDraft({ ...draft, interviewer: e.target.value })} /></label>
          <label>
            How it went (1-5)
            <select value={draft.self_rating} onChange={(e) => setDraft({ ...draft, self_rating: e.target.value })}>
              <option value="">—</option>
              {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <label className="wide">Questions they asked<textarea rows={3} value={draft.questions} onChange={(e) => setDraft({ ...draft, questions: e.target.value })} /></label>
          <label className="wide">Feedback you got<textarea rows={2} value={draft.feedback} onChange={(e) => setDraft({ ...draft, feedback: e.target.value })} /></label>
          <div className="row">
            <button disabled={save.isPending} onClick={() => save.mutate({
              label: draft.label || null, interviewer: draft.interviewer || null, questions: draft.questions || null,
              feedback: draft.feedback || null, scheduled_at: draft.scheduled_at || null,
              self_rating: draft.self_rating ? Number(draft.self_rating) : null,
            })}>Save round</button>
          </div>
        </div>
      )}
      {(save.isError || remove.isError) && <div className="callout error">{((save.error ?? remove.error) as Error).message}</div>}
    </div>
  );
}

function AddRound({ appId, next, meta }: { appId: number; next: number; meta: ApplicationsMeta }) {
  const invalidate = useInvalidate();
  const [open, setOpen] = useState(false);
  const [type, setType] = useState(next === 1 ? "hr_screen" : "technical_ai");
  const [when, setWhen] = useState("");
  const [mode, setMode] = useState("video");
  const [interviewer, setInterviewer] = useState("");
  const add = useMutation({
    mutationFn: () => appsApi.addRound(appId, {
      round_type: type, scheduled_at: when || null, mode, interviewer: interviewer || null,
    }),
    onSuccess: () => { invalidate(); setOpen(false); setWhen(""); setInterviewer(""); },
  });
  if (!open) {
    return <button onClick={() => { setType(next === 1 ? "hr_screen" : "technical_ai"); setOpen(true); }}>+ Add round {next}</button>;
  }
  return (
    <div className="round-card">
      <strong>Round {next}</strong>
      <div className="form-grid">
        <label>
          Type
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {Object.entries(meta.round_types).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </label>
        <label>Date and time (optional)<input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} /></label>
        <label>
          Mode
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            {meta.round_modes.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
        <label>Interviewer (optional)<input type="text" value={interviewer} onChange={(e) => setInterviewer(e.target.value)} /></label>
      </div>
      <div className="row">
        <button onClick={() => add.mutate()} disabled={add.isPending}>{add.isPending ? "Adding…" : "Add round"}</button>
        <button className="secondary" onClick={() => setOpen(false)}>Cancel</button>
      </div>
      {add.isError && <div className="callout error">{(add.error as Error).message}</div>}
    </div>
  );
}

function PendingEmails({ onOpen }: { onOpen: (id: number) => void }) {
  const q = useQuery({ queryKey: ["pending-emails"], queryFn: appsApi.pendingEmails });
  if (!q.data?.length) return null;
  return (
    <section className="card">
      <h2>Waiting for your reply ({q.data.length})</h2>
      <p className="muted small">Found by the inbox check. Replies are always yours to send.</p>
      {q.data.map((e) => (
        <EmailRow key={e.id} email={e} onOpen={e.application ? () => onOpen(e.application!.id) : undefined} />
      ))}
    </section>
  );
}

function EmailRow({ email: e, onOpen }: { email: JobEmail; onOpen?: () => void }) {
  const invalidate = useInvalidate();
  const done = useMutation({ mutationFn: (handled: boolean) => appsApi.setEmailHandled(e.id, handled), onSuccess: invalidate });
  return (
    <div className="round-card">
      <div className="round-head">
        <div>
          <strong>{EMAIL_CATEGORY[e.category]}</strong>
          {e.application && <span className="muted"> · {e.application.company}</span>}
          <div className="muted small">{fmtDateTime(e.received_at)} · {e.sender}</div>
        </div>
        {e.needs_reply && !e.handled && <span className="badge warn">Needs reply</span>}
      </div>
      <p className="small">{e.subject && <strong>{e.subject}. </strong>}{e.summary}</p>
      <div className="row">
        {e.view_url && <a className="button-link" href={e.view_url} target="_blank" rel="noreferrer">Open in Gmail ↗</a>}
        {onOpen && <button className="secondary" onClick={onOpen}>Open application</button>}
        {e.needs_reply && !e.handled && <button className="secondary" onClick={() => done.mutate(true)}>Mark replied</button>}
      </div>
    </div>
  );
}
