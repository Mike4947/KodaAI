import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { client, Finding, ScanEvent, subscribeScan } from "../api/client";
import AgentTrace, { ActivityEntry } from "../components/AgentTrace";
import FindingsPanel from "../components/FindingsPanel";

export default function Scan() {
  const { scanId } = useParams<{ scanId: string }>();
  const [status, setStatus] = useState("pending");
  const [summary, setSummary] = useState("");
  const [findings, setFindings] = useState<Finding[]>([]);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [error, setError] = useState("");

  const refreshScan = async () => {
    if (!scanId) return;
    const scan = await client.getScan(scanId);
    setStatus(scan.status);
    setSummary(scan.summary || "");
    setFindings(scan.findings || []);
    setActivity((scan.activity_log as ActivityEntry[]) || []);
  };

  useEffect(() => {
    if (!scanId) return;

    refreshScan().catch((e) => setError(e.message));

    const unsub = subscribeScan(scanId, (event: ScanEvent) => {
      if (event.type === "snapshot") {
        const data = event.data;
        setStatus(data.status as string);
        if (data.summary) setSummary(data.summary as string);
        setFindings((data.findings as Finding[]) || []);
        setActivity((data.activity_log as ActivityEntry[]) || []);
      } else if (event.type === "finding") {
        setFindings((prev) => [...prev, event.data as unknown as Finding]);
      } else if (event.type === "activity") {
        setActivity((prev) => [...prev, event.data as ActivityEntry]);
      } else if (event.type === "status") {
        setStatus(event.data.status as string);
        if (event.data.summary) setSummary(event.data.summary as string);
        if (event.data.message) setError(event.data.message as string);
      } else if (event.type === "done") {
        setStatus(event.data.status as string);
        refreshScan().catch(() => {});
      }
    });

    const poll = setInterval(() => {
      refreshScan().catch(() => {});
    }, 4000);

    return () => {
      unsub();
      clearInterval(poll);
    };
  }, [scanId]);

  const handleCancel = async () => {
    if (!scanId) return;
    await client.cancelScan(scanId);
    await refreshScan();
  };

  const handleExport = async () => {
    if (!scanId) return;
    const md = await client.getReportMarkdown(scanId);
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `kodaai-report-${scanId.slice(0, 8)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const isRunning = ["pending", "indexing", "running"].includes(status);

  return (
    <div>
      <div className="scan-header">
        <div>
          <h2 className="page-title">Scan Results</h2>
          <p className="page-subtitle" style={{ marginBottom: 0 }}>
            Status: <strong>{status}</strong>
            {isRunning && " — analysis in progress..."}
          </p>
        </div>
        <div className="scan-actions">
          {isRunning && (
            <button className="btn-danger" onClick={handleCancel}>
              Cancel
            </button>
          )}
          {status === "completed" && (
            <button className="btn-secondary" onClick={handleExport}>
              Export Markdown
            </button>
          )}
          <Link to="/pentests" className="btn-secondary">
            All Pentests
          </Link>
          <Link to="/" className="btn-secondary">
            New Scan
          </Link>
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}

      {summary && (
        <div className="card" style={{ marginBottom: "1.5rem" }}>
          <h3 className="section-title">Executive Summary</h3>
          <p className="summary-text">{summary}</p>
        </div>
      )}

      <div className="scan-layout">
        <div className="scan-trace-panel">
          <h3 className="section-title">Agent Trace</h3>
          <p className="section-desc">Everything the model thinks, says, and does during the scan.</p>
          <AgentTrace activity={activity} isRunning={isRunning} />
        </div>
        <div className="scan-findings-panel">
          <h3 className="section-title">Findings ({findings.length})</h3>
          <FindingsPanel findings={findings} />
        </div>
      </div>
    </div>
  );
}
