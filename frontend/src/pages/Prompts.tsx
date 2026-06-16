import { useEffect, useState } from "react";
import { client, SystemPrompt } from "../api/client";

export default function Prompts() {
  const [prompts, setPrompts] = useState<SystemPrompt[]>([]);
  const [selected, setSelected] = useState<SystemPrompt | null>(null);
  const [name, setName] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const data = await client.listPrompts();
    setPrompts(data.prompts);
    if (selected) {
      const updated = data.prompts.find((p) => p.id === selected.id);
      if (updated) selectPrompt(updated);
    } else if (data.active) {
      selectPrompt(data.active);
    }
  };

  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);

  const selectPrompt = (p: SystemPrompt) => {
    setSelected(p);
    setName(p.name);
    setBody(p.body);
  };

  const handleSave = async () => {
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      const updated = await client.updatePrompt(selected.id, { name, body });
      await load();
      if (updated) selectPrompt(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleSetActive = async () => {
    if (!selected) return;
    await client.updatePrompt(selected.id, { set_active: true });
    await load();
  };

  const handleCreate = async () => {
    setSaving(true);
    try {
      const p = await client.createPrompt("New Prompt", "Enter your analysis instructions here...", false);
      await load();
      selectPrompt(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selected || !confirm("Delete this prompt?")) return;
    await client.deletePrompt(selected.id);
    setSelected(null);
    setName("");
    setBody("");
    await load();
  };

  return (
    <div>
      <h2 className="page-title">System Prompts</h2>
      <p className="page-subtitle">
        Define what the model should look for. Prompts are saved locally and persist across sessions.
      </p>

      {error && <div className="error-box">{error}</div>}

      <div className="grid-2">
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "1rem" }}>
            <h3 style={{ fontSize: "1rem" }}>Saved Prompts</h3>
            <button className="btn-primary" onClick={handleCreate} disabled={saving} style={{ padding: "0.25rem 0.75rem" }}>
              + New
            </button>
          </div>
          {prompts.map((p) => (
            <button
              key={p.id}
              className="btn-secondary"
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                marginBottom: "0.5rem",
                padding: "0.625rem 0.75rem",
                borderColor: selected?.id === p.id ? "var(--accent)" : undefined,
              }}
              onClick={() => selectPrompt(p)}
            >
              {p.name}
              {p.is_active ? (
                <span className="badge badge-low" style={{ marginLeft: "0.5rem" }}>
                  active
                </span>
              ) : null}
            </button>
          ))}
        </div>

        <div className="card">
          {selected ? (
            <>
              <div className="form-group">
                <label>Name</label>
                <input value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="form-group">
                <label>Prompt body</label>
                <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={16} />
              </div>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <button className="btn-primary" onClick={handleSave} disabled={saving}>
                  {saving ? "Saving..." : "Save"}
                </button>
                {!selected.is_active && (
                  <button className="btn-secondary" onClick={handleSetActive}>
                    Set as active
                  </button>
                )}
                <button className="btn-danger" onClick={handleDelete}>
                  Delete
                </button>
              </div>
            </>
          ) : (
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
              Select a prompt to edit, or create a new one.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
