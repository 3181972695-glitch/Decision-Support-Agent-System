import { useState, type FormEvent } from "react";
import { expertDebateApi } from "../services/api";
import type { ExpertDebateResponse } from "../services/api";

const EXPERT_MODES = [
  {
    value: "software",
    label: "Software Architecture Debate",
    desc: "Architect vs Security vs Performance",
  },
  {
    value: "career",
    label: "Career Strategy Debate",
    desc: "Coach vs Analyst vs Hiring Manager",
  },
  {
    value: "dynamic",
    label: "Dynamic Expert Debate",
    desc: "AI generates the expert panel for your question",
  },
];

const ROLE_COLORS: Record<string, { bg: string; fg: string }> = {
  "Architect": { bg: "#eef2ff", fg: "#4338ca" },
  "Security Engineer": { bg: "#fef2f2", fg: "#b91c1c" },
  "Performance Engineer": { bg: "#fefce8", fg: "#a16207" },
  "Career Coach": { bg: "#eef2ff", fg: "#4338ca" },
  "Industry Analyst": { bg: "#f0fdf4", fg: "#15803d" },
  "Hiring Manager": { bg: "#fefce8", fg: "#a16207" },
};

function getRoleColor(role: string) {
  return ROLE_COLORS[role] ?? { bg: "#f3f4f6", fg: "#374151" };
}

function ExpertDebatePage() {
  const [mode, setMode] = useState("software");
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExpertDebateResponse | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await expertDebateApi({ mode, question: question.trim() });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  const isDynamic = mode === "dynamic";
  const hasGeneratedExperts = result?.generated_experts && result.generated_experts.length > 0;

  return (
    <main>
      <h1>Expert Debate</h1>
      <p>
        Experts independently analyse your question, then challenge each
        other's positions. A judge synthesises the final decision.
      </p>

      <form onSubmit={handleSubmit}>
        <label htmlFor="ed-mode">Expert Panel</label>
        <select
          id="ed-mode"
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

        <label htmlFor="ed-question">Question</label>
        <textarea
          id="ed-question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. Should we migrate our monolithic application to microservices?"
          rows={3}
          disabled={loading}
          className="question-panel__input"
          required
        />

        <button type="submit" disabled={loading || !question.trim()}>
          {loading ? "Running debate..." : "Start Expert Debate"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {loading && (
        <div className="status-banner status-banner--live">
          <span className="spinner" />
          <span>
            {isDynamic
              ? "Phase 0: Generating expert team... Phase 1: Expert analysis... Phase 2: Cross-critique... Phase 3: Judge deliberation..."
              : "Phase 1: Expert analysis... Phase 2: Cross-critique... Phase 3: Judge deliberation..."
            }
          </span>
        </div>
      )}

      {result && (
        <div className="expert-debate-result">
          {/* ── Header ── */}
          <div className="expert-debate-result__header">
            <h2>{result.mode}</h2>
          </div>

          {/* ── Generated Expert Panel (dynamic only) ── */}
          {hasGeneratedExperts && (
            <section className="ed-section">
              <h3 className="ed-section__title ed-section__title--generated">
                Generated Expert Panel
              </h3>
              <div className="ed-generated-panel">
                {result.generated_experts.map((ge, idx) => {
                  const c = getRoleColor(ge.role);
                  return (
                    <div key={idx} className="ed-generated-card" style={{ borderLeftColor: c.fg }}>
                      <span className="ed-generated-card__role" style={{ color: c.fg }}>{ge.role}</span>
                      {ge.expertise && <span className="ed-generated-card__exp">{ge.expertise}</span>}
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {/* ── Phase 1: Expert Analyses ── */}
          <section className="ed-section">
            <h3 className="ed-section__title ed-section__title--analysis">
              Expert Analyses
            </h3>
            {result.experts.map((expert, idx) => {
              const c = getRoleColor(expert.role);
              return (
                <div
                  key={idx}
                  className="message ed-message"
                  style={{ background: c.bg, borderLeftColor: c.fg }}
                >
                  <div className="message__header">
                    <span
                      className="message__badge"
                      style={{ background: c.fg, color: "#fff" }}
                    >
                      {expert.role}
                    </span>
                    <span className="message__label">Analysis</span>
                  </div>
                  <p>{expert.analysis}</p>
                  {expert.arguments.length > 0 && (
                    <div className="ed-arguments">
                      <strong>Key arguments:</strong>
                      <ul>
                        {expert.arguments.map((arg, ai) => (
                          <li key={ai}>{arg}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })}
          </section>

          {/* ── Phase 2: Debate Rounds ── */}
          {result.debate_rounds.length > 0 && (
            <section className="ed-section">
              <h3 className="ed-section__title ed-section__title--debate">
                Cross-Critique
              </h3>
              {result.debate_rounds.map((dr, idx) => {
                const c = getRoleColor(dr.speaker);
                return (
                  <div
                    key={idx}
                    className="message ed-message ed-message--small"
                    style={{ background: c.bg, borderLeftColor: c.fg }}
                  >
                    <div className="message__header">
                      <span
                        className="message__badge"
                        style={{ background: c.fg, color: "#fff" }}
                      >
                        {dr.speaker}
                      </span>
                      <span className="message__label">
                        responds to {dr.response_to}
                      </span>
                    </div>
                    <p>{dr.content}</p>
                  </div>
                );
              })}
            </section>
          )}

          {/* ── Phase 3: Judge Decision ── */}
          <section className="ed-section">
            <h3 className="ed-section__title ed-section__title--judge">
              Final Decision
            </h3>
            <div className="ed-judge">
              <div className="ed-judge__decision">
                <p>{result.final_decision}</p>
              </div>

              <div className="ed-judge__meta">
                <div className="ed-judge__confidence">
                  <span className="ed-judge__confidence-label">
                    Confidence
                  </span>
                  <div className="ed-judge__confidence-bar">
                    <div
                      className="ed-judge__confidence-fill"
                      style={{ width: `${result.confidence}%` }}
                    />
                  </div>
                  <span className="ed-judge__confidence-value">
                    {result.confidence}%
                  </span>
                </div>

                {result.confidence_reason && result.confidence_reason.length > 0 && (
                  <div className="ed-judge__reasons">
                    <strong>Confidence reasons:</strong>
                    <ul>
                      {result.confidence_reason.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {result.uncertainties && result.uncertainties.length > 0 && (
                  <div className="ed-judge__uncertainties">
                    <strong>Remaining uncertainties:</strong>
                    <ul>
                      {result.uncertainties.map((u, i) => (
                        <li key={i}>{u}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {result.key_tradeoffs && result.key_tradeoffs.length > 0 && (
                  <div className="ed-judge__tradeoffs">
                    <strong>Key trade-offs:</strong>
                    <ul>
                      {result.key_tradeoffs.map((t, i) => (
                        <li key={i}>{t}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}

export default ExpertDebatePage;
