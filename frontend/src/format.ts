import type { Salary } from "./api";

export const SEGMENTS: { key: string; label: string; hint: string }[] = [
  { key: "IN_ONSITE_HYBRID", label: "India · Onsite/Hybrid", hint: "Office-based or hybrid roles in India." },
  { key: "IN_REMOTE", label: "India · Remote", hint: "Remote from India. Office-visit and city limits are labelled; hybrid never appears here." },
  { key: "INTL_REMOTE", label: "International · Remote", hint: "Only jobs where hiring from India is verified in the posting." },
  { key: "INTL_RELOCATION", label: "International · Relocation", hint: "Only jobs that explicitly mention visa sponsorship." },
  { key: "UNVERIFIED", label: "Unverified", hint: "Remote eligibility or visa support couldn't be confirmed from the posting. Check before applying." },
];

export const ARRANGEMENT: Record<string, string> = {
  onsite: "Onsite", hybrid: "Hybrid", remote_occasional_office: "Remote + office visits",
  remote_city_restricted: "Remote (city-limited)", remote_first: "Remote-first", fully_remote: "Fully remote", unknown: "Not stated",
};

export const DIFFICULTY: Record<string, string> = {
  beginner_friendly: "Beginner-friendly", medium: "Medium", difficult: "Difficult", highly_competitive: "Highly competitive",
};

export const RECOMMENDATION: Record<string, string> = {
  apply_now: "Apply now", prep_then_apply: "Prep, then apply", stretch: "Stretch", skip: "Skip",
};

export const ROLE: Record<string, string> = {
  ai_engineer: "AI engineer", ai_backend: "AI backend", java_backend: "Java backend", backend: "Backend",
};

export const CATEGORY: Record<number, string> = { 1: "Medium", 2: "Large", 3: "Highly competitive" };

export const PROVENANCE: Record<string, { icon: string; label: string }> = {
  verified_posting: { icon: "✓", label: "From the job posting" },
  employee_reported: { icon: "👥", label: "Reported by employees" },
  estimated: { icon: "≈", label: "Estimated" },
  not_disclosed: { icon: "—", label: "Not disclosed" },
};

export function lpa(inr: number | null | undefined): string {
  if (!inr) return "";
  const v = inr / 100_000;
  return v >= 100 ? v.toFixed(0) : v.toFixed(1).replace(/\.0$/, "");
}

export function salaryShort(s: Salary): string {
  if (!s || s.provenance === "not_disclosed" || !s.inr_max) return "—";
  const range = s.inr_min && s.inr_min !== s.inr_max ? `${lpa(s.inr_min)}–${lpa(s.inr_max)}` : lpa(s.inr_max);
  return `${range} LPA${s.currency && s.currency !== "INR" ? " ≈" : ""}`;
}

export function money(n: number | undefined, currency: string | undefined): string {
  if (n === undefined || !currency) return "";
  try {
    return new Intl.NumberFormat("en", { style: "currency", currency, maximumFractionDigits: 0 }).format(n);
  } catch {
    return `${currency} ${Math.round(n).toLocaleString()}`;
  }
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "—";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "1d";
  if (days < 30) return `${days}d`;
  return `${Math.floor(days / 30)}mo`;
}

export function scoreClass(n: number | null | undefined): string {
  if (n == null) return "";
  return n >= 80 ? "score-high" : n >= 60 ? "score-mid" : "score-low";
}

export const COACH_MODES: { key: string; label: string; hint: string }[] = [
  { key: "project", label: "Project deep-dive", hint: "An interviewer grills you on one of your real projects, using the study guide built from your repos." },
  { key: "readiness", label: "Readiness check", hint: "20-30 min diagnostic across the job's topics. Updates your readiness score and builds a study plan." },
  { key: "mock", label: "Mock round", hint: "The coach plays the interviewer for one round. No hints unless you ask." },
  { key: "quiz", label: "Quiz", hint: "Short questions on one topic, adapting to your answers." },
  { key: "learn", label: "Learn", hint: "Ask anything. Explanations use Java/Spring analogies and end with the interview-ready answer. Not scored." },
  { key: "story", label: "Story builder", hint: "Turn your real experience into STAR answers. The coach asks for details instead of inventing them." },
];
export const MODE_LABEL: Record<string, string> = Object.fromEntries(COACH_MODES.map((m) => [m.key, m.label]));

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "Not scheduled";
  return new Date(iso).toLocaleString("en-IN", {
    weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit",
  });
}

/** ISO timestamp → value for <input type="datetime-local"> in the browser's zone. */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export const APP_STATUS_TONE: Record<string, string> = {
  applied: "", viewed: "", screening: "warn", interviewing: "warn", offer: "ok", accepted: "ok",
  rejected: "bad", withdrawn: "", no_response: "",
};
export const ROUND_STATUS_TONE: Record<string, string> = {
  scheduled: "warn", completed: "", cleared: "ok", not_cleared: "bad", cancelled: "",
};

export const EMAIL_CATEGORY: Record<string, string> = {
  application_confirmation: "Application received", recruiter_reply: "Recruiter reply", interview_invite: "Interview invite",
  assessment: "Assessment", rejection: "Rejection", offer: "Offer", other: "Other",
};
