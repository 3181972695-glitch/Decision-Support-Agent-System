import { useEffect, useState } from "react";
import { getPerformanceApi, type PerformanceSummary } from "../services/api";

interface AnalyticsPanelProps {
  debateId: string;
}

const ROLE_LABELS: Record<string, string> = {
  moderator: "Moderator",
  moderator_intro: "Moderator Intro",
  moderator_summary: "Moderator Summary",
  pro: "Pro",
  con: "Con",
  judge: "Judge",
};

/** Safely format cost value from backend (string or number). */
function formatCost(value: unknown): string {
  if (value === null || value === undefined) return "--";
  if (typeof value === "string") return value;
  if (typeof value === "number") return `$${value.toFixed(4)}`;
  return "--";
}

function AnalyticsPanel({ debateId }: AnalyticsPanelProps) {
  const [data, setData] = useState<PerformanceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      try {
        setLoading(true);
        const result = await getPerformanceApi(debateId);
        if (!cancelled) setData(result);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load analytics");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchData();
    return () => { cancelled = true; };
  }, [debateId]);

  if (loading) return <div className="analytics-panel"><p>Loading analytics...</p></div>;
  if (error) return <div className="analytics-panel"><p className="error">{error}</p></div>;
  if (!data) return null;

  return (
    <div className="analytics-panel">
      <h3>📊 Debate Analytics</h3>
      <table className="analytics-table">
        <thead>
          <tr>
            <th>Agent</th>
            <th>Model</th>
            <th>Duration</th>
            <th>Input</th>
            <th>Output</th>
            <th>Reasoning</th>
            <th>Retries</th>
          </tr>
        </thead>
        <tbody>
          {(data.calls ?? []).map((call, i) => (
            <tr key={i}>
              <td>{ROLE_LABELS[call.role] ?? call.role}</td>
              <td>{call.model}</td>
              <td>{call.duration.toFixed(1)}s</td>
              <td>{call.input_tokens.toLocaleString()}</td>
              <td>{call.output_tokens.toLocaleString()}</td>
              <td>{(call.reasoning_tokens ?? 0).toLocaleString()}</td>
              <td>{call.retry_count ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="analytics-totals">
        <span>Total calls: <strong>{data.total_llm_calls}</strong></span>
        <span>Total tokens: <strong>{(data.total_input_tokens + data.total_output_tokens).toLocaleString()}</strong></span>
        <span>Total duration: <strong>{data.total_duration_s?.toFixed(1) ?? "0.0"}s</strong></span>
        <span>Slowest call: <strong>{data.slowest_call_s?.toFixed(1) ?? "0.0"}s</strong></span>
        {data.estimated_cost != null && data.estimated_cost !== undefined && (
          <span>Est. cost: <strong>{formatCost(data.estimated_cost)}</strong></span>
        )}
      </div>
    </div>
  );
}

export default AnalyticsPanel;
