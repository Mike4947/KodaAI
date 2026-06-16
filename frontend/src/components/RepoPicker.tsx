import { useEffect, useState } from "react";
import { client, GitHubRepo } from "../api/client";

interface Props {
  onSelect: (repo: GitHubRepo) => void;
  connected: boolean;
  configured: boolean;
  username?: string;
  onConnect: () => void;
  onDisconnect: () => void;
}

export default function RepoPicker({
  onSelect,
  connected,
  configured,
  username,
  onConnect,
  onDisconnect,
}: Props) {
  const [repos, setRepos] = useState<GitHubRepo[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!connected) return;
    setLoading(true);
    client
      .githubRepos(search)
      .then((r) => setRepos(r.repos))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [connected, search]);

  if (!configured) {
    return (
      <div className="card">
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          GitHub OAuth is not configured. Add <code className="mono">GITHUB_CLIENT_ID</code> and{" "}
          <code className="mono">GITHUB_CLIENT_SECRET</code> to <code className="mono">.env</code> to
          access private repos.
        </p>
      </div>
    );
  }

  if (!connected) {
    return (
      <div className="card">
        <p style={{ marginBottom: "1rem", fontSize: "0.875rem", color: "var(--text-muted)" }}>
          Connect your GitHub account to browse and clone private repositories.
        </p>
        <button className="btn-primary" onClick={onConnect}>
          Connect GitHub
        </button>
      </div>
    );
  }

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <span style={{ fontSize: "0.875rem" }}>
          Connected as <strong>{username}</strong>
        </span>
        <button className="btn-secondary" onClick={onDisconnect} style={{ padding: "0.25rem 0.75rem" }}>
          Disconnect
        </button>
      </div>

      <div className="form-group">
        <label>Search repositories</label>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter by name..."
        />
      </div>

      {error && <div className="error-box">{error}</div>}

      {loading ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Loading repos...</p>
      ) : (
        <div style={{ maxHeight: 240, overflowY: "auto" }}>
          {repos.length === 0 ? (
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>No repositories found.</p>
          ) : (
            repos.map((r) => (
              <button
                key={r.id}
                className="btn-secondary"
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  marginBottom: "0.5rem",
                  padding: "0.625rem 0.75rem",
                }}
                onClick={() => onSelect(r)}
              >
                <span style={{ fontWeight: 500 }}>{r.full_name}</span>
                {r.private && (
                  <span className="badge badge-info" style={{ marginLeft: "0.5rem" }}>
                    private
                  </span>
                )}
                {r.description && (
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>
                    {r.description.slice(0, 80)}
                  </div>
                )}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
