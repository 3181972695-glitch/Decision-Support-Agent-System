import { useState, type FormEvent } from "react";
import { expertAnalyzeApi } from "../services/api";
import type { ExpertResponse } from "../services/api";

const EXPERT_MODES = [
  { value: "software", label: "Software Architecture Expert", desc: "Architect, Security, Performance" },
  { value: "career", label: "Career Strategy Expert", desc: "Coach, Analyst, Hiring Manager" },
];

function ExpertPage() {
  const [mode, setMode] = useState("software");
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExpertResponse | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await expertAnalyzeApi({ mode, question: question.trim() });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main>
      <h1>Expert Analysis</h1>
      <p>Select an expert panel and ask a question. Each expert provides their perspective, then a final decision is synthesized.</p>

      <form onSubmit={handleSubmit}>
        <label htmlFor="expert-mode">Expert Mode</label>
        <select
          id="expert-mode"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          disabled={loading}
          className="expert-select"
        >
          {EXPERT_MODES.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label} — {m.desc}
            </option>
          ))}
        </select>

        <label htmlFor="expert-question">Question</label>
        <textarea
          id="expert-question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. Should we migrate our monolithic application to microservices?"
          rows={3}
          disabled={loading}
          className="question-panel__input"
          required
        />

        <button type="submit" disabled={loading || !question.trim()}>
          {loading ? "Analyzing..." : "Run Analysis"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {loading && (
        <div className="status-banner status-banner--live">
          <span className="spinner" />
          <span>Running expert analysis...</span>
        </div>
      )}

      {result && (
        <div className="expert-result">
          <div className="expert-result__header">
            <h2>{result.mode}</h2>
          </div>

          <div className="expert-result__experts">
            {result.experts.map((expert, idx) => (
              <div key={idx} className={`message message--expert message--expert-${idx}`}>
                <div className="message__header">
                  <span className="message__badge" style={{
                    background: EXPERT_COLORS[idx % EXPERT_COLORS.length].bg,
                    color: EXPERT_COLORS[idx % EXPERT_COLORS.length].fg,
                  }}>
                    {expert.role}
                  </span>
                  <span className="message__label">Expert Analysis</span>
                </div>
                <p>{expert.analysis}</p>
              </div>
            ))}
          </div>

          <div className="expert-decision">
            <h3>Final Decision</h3>
            <p>{result.final_decision}</p>
          </div>
        </div>
      )}
    </main>
  );
}

const EXPERT_COLORS = [
  { bg: "#eef2ff", fg: "#4338ca" },  // indigo
  { bg: "#f0fdf4", fg: "#15803d" },  // green
  { bg: "#fefce8", fg: "#a16207" },  // yellow
  { bg: "#fef2f2", fg: "#b91c1c" },  // red
  { bg: "#f5f3ff", fg: "#6d28d9" },  // violet
];

export default ExpertPage;
