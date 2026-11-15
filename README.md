# JobPilot

A personal AI job-search assistant I'm building and using for my own job search. It finds fresh
jobs, scores how well each one fits, tracks applications through interview rounds, and coaches me
for interviews with an LLM. It doesn't take an outside action (like applying or emailing)
without my approval.

## What it does today
- **Discovery:** pulls jobs from 78 company career boards (Greenhouse/Lever-style ATS APIs) plus
  remote job boards, dedupes them, sorts them into India onsite/hybrid, India remote, international
  remote and relocation, and hides postings older than 30 days.
- **Scoring:** explainable rule-based fit score (skills, location, compensation, seniority,
  difficulty) with the reasons and risks shown for every job.
- **Application tracker:** status history and any number of interview rounds per application.
- **Interview coach:** chat-based coach with 5 modes (learn, quiz, mock interview, project
  deep-dive, readiness) and rubric scoring. Prompt guardrails treat job descriptions as untrusted
  input and never invent experience you haven't confirmed.
- **Facts store:** your experience lives in one YAML file. Only confirmed facts are ever used by the AI.
- **LLM gateway:** model tiers, a daily call cap, and a usage ledger for every call.

## Stack
Python 3.13 · FastAPI · SQLAlchemy + Alembic · PostgreSQL · React + Vite + TypeScript · pytest
(135 tests). LLM engine: Claude via the local Claude Code CLI, or a fake engine for offline tests.

## Roadmap: the AI engineering layer
Built in public, one step at a time:
- [ ] Provider-agnostic LLM layer (Anthropic / OpenAI / local) with structured outputs
- [ ] Observability: traces for every LLM call (prompt, tokens, cost, latency, errors) + dashboard
- [ ] Embeddings in Postgres with pgvector
- [ ] Semantic resume ↔ job matching
- [ ] RAG for the coach: answers grounded in your notes and the JD, with citations
- [ ] Evals: golden set of jobs, scoring accuracy, LLM-as-judge for coach answers, CI regression gate
- [ ] Guardrails enforced in code (no invented experience, prompt-injection checks)
- [ ] Streaming coach replies (SSE)
- [ ] Caching, retries with backoff, rate limiting
- [ ] LangGraph agent: company research with tools and human-in-the-loop approval
- [ ] MCP server exposing jobs and applications as tools
- [ ] Model routing and versioned prompts linked to eval results

## Layout
```
backend/app/        FastAPI app, scoring, coach, prefs, facts
backend/app/discovery/  job sources, classification, salary/FX parsing
backend/app/llm/    engines (Claude Code CLI, fake) and gateway
backend/migrations/ Alembic migrations
backend/tests/      pytest (uses database jobpilot_test)
frontend/           React dashboard
infra/              docker-compose (Postgres)
data/               your personal files, git-ignored (facts, resumes, notes)
```

## Run it
Prerequisites: Docker, Python 3.13, Node 20+, and the Claude Code CLI signed in (`claude`, then
`/login`). Or set `LLM_ENGINE=fake` to try it without an LLM.
```bash
make setup && make db && make migrate
cp .env.example .env
mkdir -p data && cp examples/profile_facts.example.yaml data/profile_facts.yaml   # then edit with your own experience
make facts
make build && make api   # http://127.0.0.1:8000
```

## Test
```bash
make test
```

## License
MIT
