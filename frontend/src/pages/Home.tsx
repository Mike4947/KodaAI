import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  client,
  GemmaModel,
  GitHubRepo,
  SystemPrompt,
} from "../api/client";
import ModelEmptyState from "../components/ModelEmptyState";
import RepoPicker from "../components/RepoPicker";

export default function Home() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [models, setModels] = useState<GemmaModel[]>([]);
  const [health, setHealth] = useState({ reachable: false, message: "" });
  const [selectedModel, setSelectedModel] = useState("");
  const [loadingModels, setLoadingModels] = useState(true);

  const [repoUrl, setRepoUrl] = useState("");
  const [tab, setTab] = useState<"url" | "github">("url");
  const [cloning, setCloning] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [ghStatus, setGhStatus] = useState<{ configured: boolean; connected: boolean; username?: string }>({
    configured: false,
    connected: false,
  });
  const [prompts, setPrompts] = useState<SystemPrompt[]>([]);
  const [selectedPromptId, setSelectedPromptId] = useState<number | undefined>();

  const loadModels = async () => {
    setLoadingModels(true);
    try {
      const data = await client.ollamaHealth();
      setHealth(data.health);
      setModels(data.models);
      if (data.models.length > 0 && !selectedModel) {
        setSelectedModel(data.models[0].name);
      }
    } catch {
      setHealth({ reachable: false, message: "Failed to reach backend API" });
    } finally {
      setLoadingModels(false);
    }
  };

  useEffect(() => {
    loadModels();
    client.githubStatus().then(setGhStatus).catch(() => {});
    client.listPrompts().then((d) => {
      setPrompts(d.prompts);
      const active = d.active;
      if (active) setSelectedPromptId(active.id);
    }).catch(() => {});

    const connected = searchParams.get("github_connected");
    const ghError = searchParams.get("github_error");
    if (connected) {
      setSuccess(`Connected to GitHub as ${connected}`);
      setTab("github");
      setSearchParams({});
      client.githubStatus().then(setGhStatus);
    }
    if (ghError) {
      setError(`GitHub error: ${ghError}`);
      setSearchParams({});
    }
  }, []);

  const handleCloneUrl = async () => {
    if (!repoUrl.trim()) return;
    setCloning(true);
    setError("");
    try {
      const repo = await client.cloneUrl(repoUrl.trim());
      setSuccess(`Cloned ${repo.full_name}`);
      await startScan(repo.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Clone failed");
    } finally {
      setCloning(false);
    }
  };

  const handleSelectRepo = async (repo: GitHubRepo) => {
    setCloning(true);
    setError("");
    try {
      const cloned = await client.cloneSelected(repo.owner, repo.name, repo.private);
      setSuccess(`Cloned ${cloned.full_name}`);
      await startScan(cloned.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Clone failed");
    } finally {
      setCloning(false);
    }
  };

  const startScan = async (repoId: string) => {
    if (!selectedModel) {
      setError("Select a Gemma 4 model first");
      return;
    }
    setScanning(true);
    try {
      const scan = await client.startScan(repoId, selectedModel, selectedPromptId);
      navigate(`/scan/${scan.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed to start");
    } finally {
      setScanning(false);
    }
  };

  const handleGitHubConnect = async () => {
    try {
      const { url } = await client.githubLogin();
      window.location.href = url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "GitHub login failed");
    }
  };

  const handleGitHubDisconnect = async () => {
    await client.githubDisconnect();
    setGhStatus({ configured: ghStatus.configured, connected: false });
  };

  return (
    <div>
      <h2 className="page-title">Analyze a Repository</h2>
      <p className="page-subtitle">
        Clone a GitHub repo and scan it locally with Gemma 4 for bugs and security issues.
      </p>

      {error && <div className="error-box">{error}</div>}
      {success && <div className="success-box">{success}</div>}

      <div className="card" style={{ marginBottom: "1.5rem" }}>
        <h3 style={{ fontSize: "1rem", marginBottom: "1rem" }}>Gemma 4 Model</h3>
        {loadingModels ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Detecting models...</p>
        ) : models.length === 0 ? (
          <ModelEmptyState health={health} onRefresh={loadModels} loading={loadingModels} />
        ) : (
          <div className="form-group">
            <label>Select model</label>
            <select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}>
              {models.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name}
                </option>
              ))}
            </select>
            <button
              className="btn-secondary"
              style={{ marginTop: "0.5rem" }}
              onClick={loadModels}
              disabled={loadingModels}
            >
              Refresh models
            </button>
          </div>
        )}
      </div>

      <div className="card" style={{ marginBottom: "1.5rem" }}>
        <h3 style={{ fontSize: "1rem", marginBottom: "1rem" }}>System Prompt</h3>
        <div className="form-group">
          <label>Active prompt for this scan</label>
          <select
            value={selectedPromptId ?? ""}
            onChange={(e) => setSelectedPromptId(Number(e.target.value))}
          >
            {prompts.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} {p.is_active ? "(active)" : ""}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
        <button
          className={tab === "url" ? "btn-primary" : "btn-secondary"}
          onClick={() => setTab("url")}
        >
          Public URL
        </button>
        <button
          className={tab === "github" ? "btn-primary" : "btn-secondary"}
          onClick={() => setTab("github")}
        >
          GitHub Account
        </button>
      </div>

      {tab === "url" ? (
        <div className="card">
          <div className="form-group">
            <label>GitHub repository URL</label>
            <input
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              onKeyDown={(e) => e.key === "Enter" && handleCloneUrl()}
            />
          </div>
          <button
            className="btn-primary"
            onClick={handleCloneUrl}
            disabled={cloning || scanning || !selectedModel || models.length === 0}
          >
            {cloning ? "Cloning..." : scanning ? "Starting scan..." : "Clone & Analyze"}
          </button>
        </div>
      ) : (
        <RepoPicker
          connected={ghStatus.connected}
          configured={ghStatus.configured}
          username={ghStatus.username}
          onConnect={handleGitHubConnect}
          onDisconnect={handleGitHubDisconnect}
          onSelect={handleSelectRepo}
        />
      )}
    </div>
  );
}
