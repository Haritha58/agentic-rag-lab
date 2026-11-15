export type Health = { status: string; db: string; llm_engine: string };

export type Fact = {
  id: string;
  kind: string;
  employer: string | null;
  text: string;
  skills: string[];
  metric: string | null;
  needs_confirmation: boolean;
  note: string | null;
};
export type FactsResponse = { facts: Fact[]; usable: number };

export type SettingsMap = Record<string, Record<string, number | string | boolean>>;

export type Usage = {
  calls_today: number;
  daily_limit: number;
  last_30_days: { task: string; calls: number; input_tokens: number; output_tokens: number; cost_usd_equiv: number; errors: number }[];
};

export type Ping = { ok: boolean; model: string | null; reply: unknown; error: string | null };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = body?.detail;
    const message = Array.isArray(detail)
      ? detail.map((d: { msg: string }) => d.msg).join("; ")
      : detail ?? res.statusText;
    throw new Error(message);
  }
  return body as T;
}

export const api = {
  health: () => request<Health>("/health"),
  facts: () => request<FactsResponse>("/facts"),
  syncFacts: () => request<{ facts: number; needs_confirmation: number; removed: number }>("/facts/sync", { method: "POST" }),
  settings: () => request<SettingsMap>("/settings"),
  saveSettings: (section: string, value: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/settings/${section}`, { method: "PUT", body: JSON.stringify(value) }),
  usage: () => request<Usage>("/llm/usage"),
  ping: () => request<Ping>("/llm/ping", { method: "POST" }),
};

// ---------- Phase 2 ----------

export type Salary = {
  provenance: "verified_posting" | "employee_reported" | "estimated" | "not_disclosed";
  currency?: string; min?: number; max?: number;
  inr_min?: number | null; inr_max?: number | null; fx_rate?: number | null; fx_date?: string | null;
  source_text?: string;
};

export type JobSummary = {
  id: number; title: string; company: string; company_id: number;
  category: number | null; category_source: string; size_band: string | null; wlb_rating: string;
  segment: string; arrangement: string; location: string | null; cities: string[]; countries: string[];
  role_family: string; seniority: string | null; exp_min: number | null; exp_max: number | null;
  salary: Salary; posted_at: string | null; first_seen_at: string; status: string; user_status: string;
  url: string; apply_url: string | null; source: string; source_label: string; applied?: boolean;
  suitability: number | null; opportunity: number | null; readiness: number | null; data_coverage: number | null;
  difficulty: string | null; recommendation: string | null; pick_reason?: string;
};

export type ScorePart = { score: number; weight: number; known: boolean; note: string };

export type JobDetail = JobSummary & {
  description: string; evidence: Record<string, unknown>; skills: string[];
  suitability_breakdown?: Record<string, ScorePart>; opportunity_breakdown?: Record<string, ScorePart>;
  difficulty_evidence?: string[]; existing_skills?: string[]; learning_skills?: string[]; missing_skills?: string[];
  rejection_risks?: string[]; scored_at?: string; score_method?: string;
  readiness_breakdown?: ReadinessBreakdown | null;
};

export type JobsResponse = { jobs: JobSummary[]; segment_counts: Record<string, number> };

export type Company = {
  id: number; name: string; category: number | null; category_source: string; size_band: string | null;
  size_source: string; ats: string | null; on_watchlist: boolean; wlb_rating: string; open_jobs: number;
};

export type Run = {
  id: number; status: string; started_at: string; finished_at: string | null;
  stats: Record<string, number>; errors: { feed: string; error: string }[];
};

export type Overview = Record<string, number>;

export const jobsApi = {
  list: (params: Record<string, string | number | boolean | undefined>) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") qs.set(k, String(v));
    return request<JobsResponse>(`/jobs?${qs}`);
  },
  get: (id: number) => request<JobDetail>(`/jobs/${id}`),
  setStatus: (id: number, user_status: string) =>
    request<{ id: number; user_status: string }>(`/jobs/${id}`, { method: "PATCH", body: JSON.stringify({ user_status }) }),
  topPicks: (n = 10) => request<JobSummary[]>(`/jobs/top-picks?n=${n}`),
  companies: () => request<Company[]>("/companies"),
  setCompany: (id: number, body: { category?: number | null; size_band?: string | null }) =>
    request<Company>(`/companies/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  runDiscovery: () => request<Run>("/discovery/run", { method: "POST" }),
  runs: () => request<Run[]>("/discovery/runs?limit=5"),
  overview: () => request<Overview>("/overview"),
  recompute: () => request<{ scored: number }>("/scores/recompute", { method: "POST" }),
};

// ---------- Phase 5a ----------

export type ReadinessTopic = {
  topic: string; label: string; weight: number; score: number; known: boolean; evidence: number; gap_hours: number;
};
export type ReadinessBreakdown = { topics: ReadinessTopic[]; coverage: number; top_gaps: string[]; prep_hours_est: number };
export type TopicProficiency = {
  topic: string; label: string; score: number | null; evidence: number; self_rating: number | null; last_at: string | null;
};
export type PrepJob = {
  id: number; title: string; company: string; status: string; suitability: number | null; opportunity: number | null;
  readiness: number | null; readiness_breakdown: ReadinessBreakdown;
};
export type Assessment = {
  topic: string; question: string; correctness: number; depth: number; structure: number; example: number;
  follow_up: number | null; went_well: string; say_instead: string; model_answer: string; score: number;
};
export type CoachMessage = { id: number; role: "user" | "coach"; content: string; assessment: Assessment | null; at: string };
export type TopicScore = { topic: string; label: string; answers: number; score: number };
export type CoachSummary = {
  topic_scores: TopicScore[]; overview: string; strengths: string[];
  gaps: { topic: string; why: string }[]; study_plan: { when: string; topic: string; task: string; hours: number }[];
};
export type CoachSession = {
  id: number; mode: string; round_type: string | null; round_label: string | null; topic: string | null;
  topic_label: string | null; interview_date: string | null; project_doc: string | null; project_label: string | null; status: "active" | "ended"; started_at: string;
  ended_at: string | null; summary: CoachSummary | null; readiness_before: number | null; readiness_after: number | null;
  job: { id: number; title: string; company: string } | null;
  messages?: CoachMessage[]; topic_scores?: TopicScore[]; answers?: number;
};
export type NewSession = {
  mode: string; job_id?: number | null; round_type?: string | null; topic?: string | null;
  interview_date?: string | null; project_doc?: string | null;
};

export const coachApi = {
  topics: () => request<TopicProficiency[]>("/prep/topics"),
  setSelfRating: (topic: string, rating: number | null) =>
    request<TopicProficiency>(`/prep/topics/${topic}`, { method: "PUT", body: JSON.stringify({ rating }) }),
  prepJobs: () => request<PrepJob[]>("/prep/jobs"),
  meta: () => request<{ round_types: Record<string, string>; topics: Record<string, string>; projects: Record<string, string> }>("/coach/meta"),
  sessions: () => request<CoachSession[]>("/coach/sessions"),
  session: (id: number) => request<CoachSession>(`/coach/sessions/${id}`),
  create: (body: NewSession) => request<CoachSession>("/coach/sessions", { method: "POST", body: JSON.stringify(body) }),
  send: (id: number, content: string) =>
    request<{ user: CoachMessage; coach: CoachMessage; done: boolean }>(`/coach/sessions/${id}/messages`, {
      method: "POST", body: JSON.stringify({ content }),
    }),
  end: (id: number) => request<CoachSession>(`/coach/sessions/${id}/end`, { method: "POST" }),
};

// ---------- Application tracking ----------

export type InterviewRound = {
  id: number; round_no: number; round_type: string; round_type_label: string; coach_round: string;
  label: string | null; scheduled_at: string | null; mode: string | null; interviewer: string | null;
  status: string; questions: string | null; feedback: string | null; self_rating: number | null;
};
export type StatusEvent = {
  id: number; from_status: string | null; to_status: string; evidence_type: string;
  evidence_ref: string | null; note: string | null; at: string;
};
export type JobEmail = {
  id: number; gmail_msg_id: string; thread_id: string | null; application_id: number | null; category: string;
  sender: string; subject: string; summary: string; needs_reply: boolean; handled: boolean;
  view_url: string | null; received_at: string;
  application?: { id: number; company: string; title: string } | null;
};
export type Application = {
  id: number; job_id: number | null; company: string; title: string; url: string | null; channel: string;
  resume_version: string | null; status: string; applied_at: string; follow_up_on: string | null;
  notes: string | null; updated_at: string; follow_up_due: boolean; rounds_total: number; rounds_cleared: number;
  next_round: InterviewRound | null; rounds?: InterviewRound[]; events?: StatusEvent[]; emails?: JobEmail[];
};
export type ApplicationsMeta = {
  statuses: Record<string, string>; channels: Record<string, string>;
  round_types: Record<string, { label: string; coach_round: string }>;
  round_statuses: Record<string, string>; round_modes: string[]; resume_versions: string[]; main_resume: string;
};
export type NewApplication = {
  job_id?: number | null; company?: string; title?: string; url?: string | null; channel?: string;
  resume_version?: string | null; applied_at?: string | null; notes?: string | null;
};
export type RoundInput = Partial<Omit<InterviewRound, "id" | "round_type_label" | "coach_round">>;

export const appsApi = {
  meta: () => request<ApplicationsMeta>("/applications/meta"),
  list: (params: { status?: string; job_id?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set("status", params.status);
    if (params.job_id !== undefined) qs.set("job_id", String(params.job_id));
    return request<Application[]>(`/applications?${qs}`);
  },
  get: (id: number) => request<Application>(`/applications/${id}`),
  create: (body: NewApplication) => request<Application>("/applications", { method: "POST", body: JSON.stringify(body) }),
  update: (id: number, body: Record<string, unknown>) =>
    request<Application>(`/applications/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: number) => fetch(`/api/applications/${id}`, { method: "DELETE" }).then((r) => {
    if (!r.ok) throw new Error(r.statusText);
  }),
  addRound: (id: number, body: RoundInput) =>
    request<Application>(`/applications/${id}/rounds`, { method: "POST", body: JSON.stringify(body) }),
  updateRound: (id: number, body: RoundInput) =>
    request<Application>(`/rounds/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  removeRound: (id: number) => request<Application>(`/rounds/${id}`, { method: "DELETE" }),
  pendingEmails: () => request<JobEmail[]>("/emails?pending=true"),
  setEmailHandled: (id: number, handled: boolean) =>
    request<JobEmail>(`/emails/${id}`, { method: "PATCH", body: JSON.stringify({ handled }) }),
};
