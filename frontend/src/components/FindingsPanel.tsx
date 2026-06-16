import { Finding } from "../api/client";

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];

interface Props {
  findings: Finding[];
}

export default function FindingsPanel({ findings }: Props) {
  const sorted = [...findings].sort(
    (a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity)
  );

  if (sorted.length === 0) {
    return (
      <div className="card">
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>No findings yet.</p>
      </div>
    );
  }

  return (
    <div>
      {sorted.map((f, i) => (
        <div key={i} className={`finding-card severity-${f.severity}`}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
            <span className={`badge badge-${f.severity}`}>{f.severity}</span>
            <span className="finding-title">{f.title}</span>
          </div>
          {f.file && (
            <div className="finding-location">
              {f.file}
              {f.line ? `:${f.line}` : ""}
            </div>
          )}
          <div className="finding-desc">{f.description}</div>
        </div>
      ))}
    </div>
  );
}
