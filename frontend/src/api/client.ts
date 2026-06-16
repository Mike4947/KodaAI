export interface OllamaHealth {
  reachable: boolean;
  message: string;
}

export interface GemmaModel {
  name: string;
  size?: number;
  modified_at?: string;
}

export interface SystemPrompt {
  id: number;
  name: string;
  body: string;
  is_active: number;
  created_at: string;
  updated_at: string;
}

export interface Repo {
  id: string;
  owner: string;
  name: string;
  full_name: string;
  is_private?: number;
  cloned_at?: string;
  local_path?: string;
}

export interface GitHubRepo {
  id: number;
  full_name: string;
  owner: string;
  name: string;
  private: boolean;
  description?: string;
  html_url?: string;
}

export interface Finding {
  severity: string;
  title: string;
  description: string;
  file?: string;
  line?: number;
}

export interface Scan {
  id: string;
  repo_id: string;
  model: string;
  status: string;
  summary?: string;
  findings: Finding[];
  activity_log: unknown[];
}

export interface ScanListItem {
  id: string;
  repo_id: string;
  repo_full_name?: string;
  repo_owner?: string;
  repo_name?: string;
  model: string;
  status: string;
  summary?: string;
  findings_count: number;
  prompt_id?: number;
  prompt_name?: string;
  created_at: string;
  updated_at: string;
}

export interface ScanListResponse {
  scans: ScanListItem[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  ongoing_count: number;
}

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail;
    const message = Array.isArray(detail)
      ? detail.map((d: { msg?: string }) => d.msg).join(", ")
      : detail || res.statusText;
    throw new Error(message);
  }
  if (res.headers.get("content-type")?.includes("text/markdown")) {
    return (await res.text()) as T;
  }
  return res.json();
}

export const client = {
  ollamaHealth: () => api<{ health: OllamaHealth; models: GemmaModel[] }>("/api/ollama/models"),

  githubStatus: () => api<{ configured: boolean; connected: boolean; username?: string }>("/api/github/status"),
  githubLogin: () => api<{ url: string }>("/api/github/login"),
  githubRepos: (search = "") => api<{ repos: GitHubRepo[] }>(`/api/github/repos?search=${encodeURIComponent(search)}`),
  githubDisconnect: () => api<{ ok: boolean }>("/api/github/disconnect", { method: "POST" }),

  cloneUrl: (url: string) => api<Repo>("/api/repos/clone", { method: "POST", body: JSON.stringify({ url }) }),
  cloneSelected: (owner: string, name: string, isPrivate: boolean) =>
    api<Repo>("/api/repos/clone-selected", {
      method: "POST",
      body: JSON.stringify({ owner, name, private: isPrivate }),
    }),

  listPrompts: () => api<{ prompts: SystemPrompt[]; active: SystemPrompt | null }>("/api/prompts"),
  createPrompt: (name: string, body: string, setActive = false) =>
    api<SystemPrompt>("/api/prompts", { method: "POST", body: JSON.stringify({ name, body, set_active: setActive }) }),
  updatePrompt: (id: number, data: { name?: string; body?: string; set_active?: boolean }) =>
    api<SystemPrompt>(`/api/prompts/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deletePrompt: (id: number) => api<{ ok: boolean }>(`/api/prompts/${id}`, { method: "DELETE" }),

  startScan: (repoId: string, model: string, promptId?: number) =>
    api<{ id: string; status: string }>("/api/scan", {
      method: "POST",
      body: JSON.stringify({ repo_id: repoId, model, prompt_id: promptId }),
    }),
  listScans: (page = 1, perPage = 10, status = "ongoing") =>
    api<ScanListResponse>(
      `/api/scans?page=${page}&per_page=${perPage}&status=${encodeURIComponent(status)}`
    ),
  getScan: (id: string) => api<Scan>(`/api/scan/${id}`),
  cancelScan: (id: string) => api<{ ok: boolean }>(`/api/scan/${id}/cancel`, { method: "POST" }),
  getReportMarkdown: (id: string) => api<string>(`/api/scan/${id}/report?format=markdown`),
};

export type ScanEvent = {
  type: string;
  data: Record<string, unknown>;
  ts: string;
};

export function subscribeScan(scanId: string, onEvent: (event: ScanEvent) => void): () => void {
  const es = new EventSource(`/api/scan/${scanId}/stream`);
  es.onmessage = (e) => {
    const event = JSON.parse(e.data) as ScanEvent;
    onEvent(event);
    if (event.type === "done") {
      es.close();
    }
  };
  es.onerror = () => es.close();
  return () => es.close();
}
