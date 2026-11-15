import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import Markdown from "react-markdown";
import { coachApi, type Assessment, type CoachMessage, type CoachSession } from "../api";
import { COACH_MODES, MODE_LABEL, ago, scoreClass } from "../format";

export default function Coach() {
  const { id } = useParams();
  const sessions = useQuery({ queryKey: ["coach-sessions"], queryFn: coachApi.sessions });
  return (
    <div className="coach">
      <aside className="coach-list">
        <Link className={`coach-item ${id ? "" : "active"}`} to="/coach">+ New session</Link>
        {sessions.data?.map((s) => (
          <Link key={s.id} to={`/coach/${s.id}`} className={`coach-item ${String(s.id) === id ? "active" : ""}`}>
            <div>{MODE_LABEL[s.mode]}{s.status === "active" && <span className="dot warn inline" title="In progress" />}</div>
            <div className="muted tiny">{s.job ? s.job.company : s.topic_label ?? "General"} · {ago(s.started_at)}</div>
          </Link>
        ))}
      </aside>
      <section className="coach-main">
        {id ? <Chat key={id} sessionId={Number(id)} /> : <NewSession />}
      </section>
    </div>
  );
}

function NewSession() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ["coach-meta"], queryFn: coachApi.meta });
  const jobs = useQuery({ queryKey: ["prep-jobs"], queryFn: coachApi.prepJobs });
  const [mode, setMode] = useState(params.get("mode") ?? "readiness");
  const [jobId, setJobId] = useState(params.get("job") ?? "");
  const [round, setRound] = useState(params.get("round") ?? "technical_ai");
  const [topic, setTopic] = useState("");
  const [date, setDate] = useState(params.get("date") ?? "");
  const [project, setProject] = useState("");
  const projects = meta.data?.projects ?? {};
  const projectDoc = project || Object.keys(projects)[0] || "";

  const create = useMutation({
    mutationFn: () => coachApi.create({
      mode, job_id: jobId ? Number(jobId) : null, round_type: mode === "mock" ? round : null,
      topic: (mode === "quiz" || mode === "learn") && topic ? topic : null, interview_date: date || null,
      project_doc: mode === "project" ? projectDoc : null,
    }),
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ["coach-sessions"] });
      qc.setQueryData(["coach-session", s.id], s);
      navigate(`/coach/${s.id}`);
    },
  });

  return (
    <>
      <h1>Coach</h1>
      <p className="muted">Each session is saved, so you can come back to it. Scored answers update your topic proficiency and readiness.</p>
      <div className="mode-grid">
        {COACH_MODES.map((m) => (
          <button key={m.key} className={`mode-card ${mode === m.key ? "active" : ""}`} onClick={() => setMode(m.key)}>
            <strong>{m.label}</strong>
            <span className="muted small">{m.hint}</span>
          </button>
        ))}
      </div>
      <div className="filters">
        <label className="select">
          Job
          <select value={jobId} onChange={(e) => setJobId(e.target.value)}>
            <option value="">General practice (no job)</option>
            {jobs.data?.map((j) => <option key={j.id} value={j.id}>{j.title} · {j.company}</option>)}
          </select>
        </label>
        {mode === "project" && (
          <label className="select">
            Project
            <select value={projectDoc} onChange={(e) => setProject(e.target.value)}>
              {Object.entries(projects).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        )}
        {mode === "mock" && (
          <label className="select">
            Round
            <select value={round} onChange={(e) => setRound(e.target.value)}>
              {Object.entries(meta.data?.round_types ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        )}
        {(mode === "quiz" || mode === "learn") && (
          <label className="select">
            Topic
            <select value={topic} onChange={(e) => setTopic(e.target.value)}>
              <option value="">{jobId ? "The job's main topics" : "Any"}</option>
              {Object.entries(meta.data?.topics ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        )}
        {(mode === "readiness" || mode === "mock") && (
          <label className="select">
            Interview date (optional)
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
        )}
        <button onClick={() => create.mutate()} disabled={create.isPending || (mode === "project" && !projectDoc)}>
          {create.isPending ? "Coach is preparing…" : "Start session"}
        </button>
      </div>
      {jobs.data?.length === 0 && <p className="muted small">Shortlist jobs on the <Link to="/jobs">Jobs</Link> page to practise for a specific role.</p>}
      {create.isError && <div className="callout error">{(create.error as Error).message}</div>}
    </>
  );
}

function Chat({ sessionId }: { sessionId: number }) {
  const qc = useQueryClient();
  const key = ["coach-session", sessionId];
  const session = useQuery({ queryKey: key, queryFn: () => coachApi.session(sessionId) });
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  const send = useMutation({
    mutationFn: (content: string) => coachApi.send(sessionId, content),
    onMutate: (content) => { setPending(content); setDraft(""); },
    onSuccess: (r) => {
      qc.setQueryData<CoachSession>(key, (s) => s && { ...s, messages: [...(s.messages ?? []), r.user, r.coach] });
      setDone(r.done);
      qc.invalidateQueries({ queryKey: ["coach-sessions"] });
    },
    onError: (_e, content) => setDraft(content),  // keep what you typed so you can retry
    onSettled: () => setPending(null),
  });
  const end = useMutation({
    mutationFn: () => coachApi.end(sessionId),
    onSuccess: (s) => {
      qc.setQueryData(key, s);
      for (const k of ["coach-sessions", "prep-jobs", "prep-topics", "jobs", "job", "top-picks"]) qc.invalidateQueries({ queryKey: [k] });
    },
  });

  const msgs = session.data?.messages ?? [];
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs.length, pending]);

  if (session.isLoading) return <p className="muted">Loading…</p>;
  if (session.isError) return <div className="callout error">{(session.error as Error).message}</div>;
  const s = session.data!;
  const active = s.status === "active";
  const answered = msgs.some((m) => m.role === "user");

  const submit = () => { if (draft.trim() && !send.isPending) send.mutate(draft.trim()); };

  return (
    <>
      <div className="page-head">
        <div>
          <h1 style={{ marginBottom: 2 }}>{MODE_LABEL[s.mode]}{s.round_label ? ` · ${s.round_label}` : ""}{s.topic_label ? ` · ${s.topic_label}` : ""}{s.project_label ? ` · ${s.project_label}` : ""}</h1>
          <div className="muted small">
            {s.job ? <>{s.job.title} · {s.job.company}</> : "General practice"}
            {s.interview_date && <> · interview on {s.interview_date}</>}
          </div>
        </div>
        {active && (
          <button className={done ? "" : "secondary"} onClick={() => end.mutate()} disabled={end.isPending || send.isPending}>
            {end.isPending ? (answered ? "Writing your report…" : "Ending…") : "End session"}
          </button>
        )}
      </div>

      <div className="chat">
        {msgs.map((m) => <Message key={m.id} m={m} />)}
        {pending && (
          <>
            <div className="msg user"><div className="bubble">{pending}</div></div>
            <div className="msg coach"><div className="bubble muted typing">Coach is thinking…</div></div>
          </>
        )}
        <div ref={bottom} />
      </div>

      {send.isError && <div className="callout error">{(send.error as Error).message}</div>}
      {end.isError && <div className="callout error">{(end.error as Error).message}</div>}
      {done && active && <div className="callout ok">That round is complete. Press <strong>End session</strong> for your report.</div>}

      {active ? (
        <div className="composer">
          <textarea
            value={draft}
            placeholder={s.mode === "learn" ? "Ask anything…" : "Type your answer. Paste code in ``` fences. ⌘/Ctrl+Enter to send."}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submit(); } }}
            rows={4}
            disabled={send.isPending}
          />
          <button onClick={submit} disabled={!draft.trim() || send.isPending}>Send</button>
        </div>
      ) : s.summary && <Summary s={s} />}
    </>
  );
}

function Message({ m }: { m: CoachMessage }) {
  return (
    <>
      <div className={`msg ${m.role}`}>
        <div className="bubble">
          {m.role === "coach" ? <div className="md"><Markdown>{m.content}</Markdown></div> : m.content}
        </div>
      </div>
      {m.assessment && <Rubric a={m.assessment} />}
    </>
  );
}

const CRITERIA: [keyof Assessment, string][] = [
  ["correctness", "Correctness"], ["depth", "Depth"], ["structure", "Structure"], ["example", "Example"], ["follow_up", "Follow-up"],
];

function Rubric({ a }: { a: Assessment }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rubric">
      <button className="rubric-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className={`rubric-score ${scoreClass(a.score)}`}>{a.score}</span>
        <span className="small">
          {CRITERIA.filter(([k]) => a[k] != null).map(([k, label]) => `${label} ${a[k]}/5`).join(" · ")}
        </span>
        <span className="muted tiny">{open ? "Hide feedback" : "Feedback"}</span>
      </button>
      {open && (
        <div className="small rubric-body">
          <p><strong>Question:</strong> {a.question}</p>
          <p><strong>What went well:</strong> {a.went_well}</p>
          <p><strong>Say instead:</strong> {a.say_instead}</p>
          <div><strong>Model answer:</strong><div className="md"><Markdown>{a.model_answer}</Markdown></div></div>
        </div>
      )}
    </div>
  );
}

function Summary({ s }: { s: CoachSession }) {
  const sum = s.summary!;
  const meta = useQuery({ queryKey: ["coach-meta"], queryFn: coachApi.meta });
  const label = (topic: string) => meta.data?.topics[topic] ?? topic;
  return (
    <section className="card summary">
      <div className="page-head">
        <h2>Session report</h2>
        {s.job && (
          <span className="small">
            Readiness: <strong>{s.readiness_before ?? "—"}</strong> → <strong className={scoreClass(s.readiness_after)}>{s.readiness_after ?? "—"}</strong>
          </span>
        )}
      </div>
      {sum.overview ? <div className="md"><Markdown>{sum.overview}</Markdown></div> : <p className="muted">No answers were scored in this session.</p>}
      {!!sum.topic_scores.length && (
        <>
          <h3>Scores by topic</h3>
          <table className="breakdown">
            <tbody>
              {sum.topic_scores.map((t) => (
                <tr key={t.topic}>
                  <td>{t.label}<div className="muted tiny">{t.answers} answer{t.answers > 1 ? "s" : ""}</div></td>
                  <td className="bar-cell"><div className="bar"><div className="bar-fill" style={{ width: `${t.score}%` }} /></div></td>
                  <td className="num">{t.score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {!!sum.strengths.length && (<><h3>Strengths</h3><ul className="tight">{sum.strengths.map((x) => <li key={x}>{x}</li>)}</ul></>)}
      {!!sum.gaps.length && (
        <>
          <h3>Top gaps</h3>
          <ol className="tight">{sum.gaps.map((g, i) => <li key={i}><strong>{label(g.topic)}</strong>: {g.why}</li>)}</ol>
        </>
      )}
      {!!sum.study_plan.length && (
        <>
          <h3>Study plan</h3>
          <div className="table-wrap">
            <table>
              <thead><tr><th>When</th><th>Topic</th><th>Task</th><th className="num">Hours</th></tr></thead>
              <tbody>
                {sum.study_plan.map((p, i) => (
                  <tr key={i}><td className="nowrap">{p.when}</td><td className="small">{label(p.topic)}</td><td>{p.task}</td><td className="num">{p.hours}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <div className="row">
        <Link className="button-link" to={s.job ? `/coach?mode=mock&job=${s.job.id}` : "/coach"}>Start another session</Link>
        <Link className="button-link" to="/prep">See readiness</Link>
      </div>
    </section>
  );
}
