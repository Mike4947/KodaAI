interface Props {
  health: { reachable: boolean; message: string };
  onRefresh: () => void;
  loading: boolean;
}

export default function ModelEmptyState({ health, onRefresh, loading }: Props) {
  return (
    <div className="card empty-state">
      <h3>No Gemma 4 models detected</h3>
      <p>{health.message}</p>
      <ol>
        <li>
          Install Ollama 0.22+:{" "}
          <a href="https://ollama.com" target="_blank" rel="noreferrer">
            ollama.com
          </a>
        </li>
        <li>
          Pull a Gemma 4 model: <code className="mono">ollama pull gemma4:e4b</code>
        </li>
        <li>
          (Recommended) Create 32K context variant:{" "}
          <code className="mono">ollama create koda-gemma4 -f Modelfile</code>
        </li>
        <li>Click Refresh to scan again</li>
      </ol>
      <button className="btn-primary" onClick={onRefresh} disabled={loading}>
        {loading ? "Scanning..." : "Refresh models"}
      </button>
    </div>
  );
}
