import { useEffect, useRef } from "react";

export interface ActivityEntry {
  kind?: string;
  turn?: number;
  action?: string;
  message?: string;
  thinking?: string;
  content?: string;
  args?: Record<string, unknown>;
  result?: string;
  tool_calls?: Array<{ name: string; arguments: Record<string, unknown> }>;
}

interface Props {
  activity: ActivityEntry[];
  isRunning: boolean;
}

function kindLabel(kind: string | undefined, action: string | undefined) {
  switch (kind) {
    case "phase":
      return action === "model_request" ? "Waiting for model" : action || "Phase";
    case "model":
      return "Model response";
    case "tool_call":
      return `Tool call: ${action}`;
    case "tool_result":
      return `Tool result: ${action}`;
    case "system":
      return "System";
    case "note":
      return "Note";
    case "error":
      return "Error";
    default:
      return action || "Activity";
  }
}

function kindClass(kind: string | undefined) {
  switch (kind) {
    case "model":
      return "trace-model";
    case "tool_call":
      return "trace-tool-call";
    case "tool_result":
      return "trace-tool-result";
    case "phase":
      return "trace-phase";
    case "error":
      return "trace-error";
    case "system":
      return "trace-system";
    default:
      return "trace-default";
  }
}

export default function AgentTrace({ activity, isRunning }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activity.length]);

  if (activity.length === 0) {
    return (
      <div className="agent-trace empty">
        {isRunning ? (
          <div className="trace-entry trace-phase">
            <div className="trace-header">
              <span className="trace-kind">Starting</span>
            </div>
            <div className="trace-body">Preparing scan — indexing repository and contacting the model...</div>
          </div>
        ) : (
          <div className="trace-empty">No agent activity recorded.</div>
        )}
      </div>
    );
  }

  return (
    <div className="agent-trace">
      {activity.map((entry, i) => (
        <div key={i} className={`trace-entry ${kindClass(entry.kind)}`}>
          <div className="trace-header">
            <span className="trace-kind">{kindLabel(entry.kind, entry.action)}</span>
            {entry.turn != null && entry.turn > 0 && (
              <span className="trace-turn">Turn {entry.turn}</span>
            )}
          </div>

          {entry.message && <div className="trace-body">{entry.message}</div>}

          {entry.thinking && (
            <details className="trace-block" open>
              <summary>Thinking</summary>
              <pre>{entry.thinking}</pre>
            </details>
          )}

          {entry.content && (
            <details className="trace-block" open={entry.kind === "model"}>
              <summary>{entry.kind === "model" ? "Response" : "Content"}</summary>
              <pre>{entry.content}</pre>
            </details>
          )}

          {entry.tool_calls && entry.tool_calls.length > 0 && (
            <details className="trace-block" open>
              <summary>Planned tool calls</summary>
              {entry.tool_calls.map((tc, j) => (
                <div key={j} className="trace-tool">
                  <div className="trace-tool-name">{tc.name}</div>
                  <pre>{JSON.stringify(tc.arguments, null, 2)}</pre>
                </div>
              ))}
            </details>
          )}

          {entry.args && Object.keys(entry.args).length > 0 && entry.kind === "tool_call" && (
            <details className="trace-block" open>
              <summary>Arguments</summary>
              <pre>{JSON.stringify(entry.args, null, 2)}</pre>
            </details>
          )}

          {entry.result && (
            <details className="trace-block" open>
              <summary>Result</summary>
              <pre>{entry.result}</pre>
            </details>
          )}
        </div>
      ))}
      {isRunning && (
        <div className="trace-entry trace-phase trace-live">
          <div className="trace-header">
            <span className="trace-kind">Live</span>
            <span className="status-dot" />
          </div>
          <div className="trace-body">Agent is working...</div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
