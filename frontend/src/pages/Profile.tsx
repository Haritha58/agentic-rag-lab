import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Fact } from "../api";

const KIND_ORDER = ["professional", "personal_project", "learning", "certification", "education", "publication", "award"];

export default function Profile() {
  const qc = useQueryClient();
  const facts = useQuery({ queryKey: ["facts"], queryFn: api.facts });
  const sync = useMutation({
    mutationFn: api.syncFacts,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["facts"] }),
  });

  const groups = new Map<string, Fact[]>();
  for (const f of facts.data?.facts ?? []) groups.set(f.kind, [...(groups.get(f.kind) ?? []), f]);

  return (
    <>
      <div className="page-head">
        <h1>Profile facts</h1>
        <button onClick={() => sync.mutate()} disabled={sync.isPending}>
          {sync.isPending ? "Reloading…" : "Reload from file"}
        </button>
      </div>
      <p className="muted">
        Source of truth: <code>data/profile_facts.yaml</code>. Edit that file, then reload. Facts marked{" "}
        <span className="badge warn">needs confirmation</span> are never used by agents.
      </p>
      {sync.isError && <div className="callout error">{(sync.error as Error).message}</div>}
      {sync.isSuccess && (
        <div className="callout ok">
          Loaded {sync.data.facts} facts ({sync.data.needs_confirmation} need confirmation, {sync.data.removed} removed).
        </div>
      )}
      {facts.isError && <div className="callout error">{(facts.error as Error).message}</div>}

      {KIND_ORDER.filter((k) => groups.has(k)).map((kind) => (
        <section key={kind}>
          <h2>{kind[0].toUpperCase() + kind.slice(1).replace("_", " ")}</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>ID</th><th>Fact</th><th>Skills</th><th>Status</th></tr>
              </thead>
              <tbody>
                {groups.get(kind)!.map((f) => (
                  <tr key={f.id}>
                    <td className="mono">{f.id}</td>
                    <td>
                      {f.employer && <div className="muted small">{f.employer}</div>}
                      {f.text}
                      {f.note && <div className="note">{f.note}</div>}
                    </td>
                    <td>{f.skills.map((s) => <span key={s} className="chip">{s}</span>)}</td>
                    <td>
                      {f.needs_confirmation
                        ? <span className="badge warn">needs confirmation</span>
                        : <span className="badge ok">usable</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </>
  );
}
