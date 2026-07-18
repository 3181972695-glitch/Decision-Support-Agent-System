import { useState, type FormEvent } from "react";
import { useExpertDebateStream } from "../hooks/useExpertDebateStream";
import type { StreamingState } from "../hooks/useExpertDebateStream";

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

function getColor(role: string) {
  return ROLE_COLORS[role] ?? { bg: "#f3f4f6", fg: "#374151" };
}

function PhaseTimeline({ state }: { state: StreamingState }) {
  const phases = [
    { key: "expert_generation", label: "Generating Expert Panel" },
    { key: "analysis", label: "Expert Analysis" },
    { key: "debate", label: "Cross-Critique" },
    { key: "judge", label: "Judge Deliberation" },
    { key: "complete", label: "Final Decision" },
  ] as const;

  const phaseOrder = ["expert_generation", "analysis", "debate", "judge", "complete"];
  const currentIdx = phaseOrder.indexOf(state.phase);

  return (
    <div className="st-timeline">
      {phases.map((p, i) => {
        let status: "done" | "active" | "pending" = "pending";
        if (i < currentIdx) status = "done";
        else if (i === currentIdx) status = "active";

        return (
          <div key={p.key} className={`st-timeline__step st-timeline__step--${status}`}>
            <span className="st-timeline__icon">
              {status === "done" ? "✓" : status === "active" ? "●" : "○"}
            </span>
            <span className="st-timeline__label">{p.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function ExpertDebateStreamPage() {
  const [mode, setMode] = useState("software");
  const [question, setQuestion] = useState("");
  const { state, startDebate, reset } = useExpertDebateStream();
  const isStreaming = state.phase !== "idle" && state.phase !== "complete" && state.phase !== "error";
  const hasResult = state.phase === "complete" && state.result;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    startDebate(mode, question.trim());
  };

  return (
    <main>
      <h1>Expert Debate <span className="st-badge">Live</span></h1>
      <p>Watch the debate unfold in real time as experts analyse, challenge, and reach a decision.</p>

      {/* ── Form (hidden once streaming) ── */}
      {!isStreaming && !hasResult && (
        <form onSubmit={handleSubmit}>
          <label htmlFor="st-mode">Expert Panel</label>
          <select
            id="st-mode"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            disabled={isStreaming}
            className="expert-select"
          >
            {EXPERT_MODES.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label} — {m.desc}
              </option>
            ))}
          </select>

          <label htmlFor="st-question">Question</label>
          <textarea
            id="st-question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. Should we migrate our monolithic application to microservices?"
            rows={3}
            disabled={isStreaming}
            className="question-panel__input"
            required
          />

          <button type="submit" disabled={isStreaming || !question.trim()}>
            Start Live Debate
          </button>
        </form>
      )}

      {state.error && <p className="error">{state.error}</p>}

      {/* ── Re-run button (after complete or error) ── */}
      {(hasResult || state.phase === "error") && (
        <button onClick={reset} className="btn btn--secondary" style={{ marginBottom: "1rem" }}>
          Start New Debate
        </button>
      )}

      {/* ── Streaming UI ── */}
      {(isStreaming || hasResult) && (
        <div className="st-container">
          <PhaseTimeline state={state} />

          {/* ── Generated Expert Panel (dynamic mode) ── */}
          {state.generatedExperts.length > 0 && (
            <section className="st-section">
              <h3 className="st-section__title">Expert Panel</h3>
              <div className="st-panel">
                {state.generatedExperts.map((ge) => {
                  const c = getColor(ge.role);
                  return (
                    <div key={ge.role} className="st-panel__card" style={{ borderLeftColor: c.fg }}>
                      <span className="st-panel__role" style={{ color: c.fg }}>{ge.role}</span>
                      {ge.expertise && <span className="st-panel__exp">{ge.expertise}</span>}
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {/* ── Tool Activity Panel ── */}
          {state.toolCalls.length > 0 && (
            <section className="st-section">
              <h3 className="st-section__title">Tool Execution</h3>
              <div className="st-tools">
                {state.toolCalls.map((tc, idx) => (
                  <div key={idx} className="st-tool-item">
                    <span className="st-tool-icon">
                      {tc.status === "running" ? "⏳" : "✓"}
                    </span>
                    <span className="st-tool-name">{tc.tool}</span>
                    <span className="st-tool-expert">by {tc.expert}</span>
                    {tc.status === "running" && <span className="st-tool-status st-tool-status--active">running...</span>}
                    {tc.status === "complete" && <span className="st-tool-status st-tool-status--done">done</span>}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* ── Phase 1: Expert Analyses ── */}
          {state.expertOrder.length > 0 && (
            <section className="st-section">
              <h3 className="st-section__title">Expert Analyses</h3>
              {state.expertOrder.map((role) => {
                const text = state.expertTexts[role] ?? "";
                const args = state.expertArguments[role] ?? [];
                const isActive = state.currentExpert === role;
                const c = getColor(role);
                return (
                  <div
                    key={role}
                    className={`message st-message ${isActive ? "st-message--active" : ""}`}
                    style={{ background: c.bg, borderLeftColor: c.fg }}
                  >
                    <div className="message__header">
                      <span className="message__badge" style={{ background: c.fg, color: "#fff" }}>
                        {role}
                      </span>
                      <span className="message__label">
                        {isActive ? "Analyzing..." : "Analysis"}
                      </span>
                    </div>
                    <p>{text || (isActive ? "Waiting for response..." : "")}</p>
                    {args.length > 0 && (
                      <div className="ed-arguments">
                        <strong>Key arguments:</strong>
                        <ul>
                          {args.map((a, i) => <li key={i}>{a}</li>)}
                        </ul>
                      </div>
                    )}
                  </div>
                );
              })}
            </section>
          )}

          {/* ── Phase 2: Debate ── */}
          {state.debateOrder.length > 0 && (
            <section className="st-section">
              <h3 className="st-section__title">Cross-Critique</h3>
              {state.debateOrder.map((key) => {
                const text = state.debateTexts[key] ?? "";
                const [speaker, target] = key.split("→");
                const isActive =
                  state.currentDebate?.speaker === speaker &&
                  state.currentDebate?.response_to === target;
                const c = getColor(speaker);
                return (
                  <div
                    key={key}
                    className={`message st-message st-message--small ${isActive ? "st-message--active" : ""}`}
                    style={{ background: c.bg, borderLeftColor: c.fg }}
                  >
                    <div className="message__header">
                      <span className="message__badge" style={{ background: c.fg, color: "#fff" }}>
                        {speaker}
                      </span>
                      <span className="message__label">
                        responds to {target}
                        {isActive ? " (challenging...)" : ""}
                      </span>
                    </div>
                    <p>{text || (isActive ? "Writing challenge..." : "")}</p>
                  </div>
                );
              })}
            </section>
          )}

          {/* ── Phase 3: Judge ── */}
          {(state.judgeText || state.judgeStreaming || hasResult) && (
            <section className="st-section">
              <h3 className="st-section__title">Final Decision</h3>
              <div className="ed-judge">
                <div className="ed-judge__decision">
                  <p>{state.judgeText || (state.judgeStreaming ? "Deliberating..." : "")}</p>
                </div>

                {hasResult && state.result && (
                  <div className="ed-judge__meta">
                    <div className="ed-judge__confidence">
                      <span className="ed-judge__confidence-label">Confidence</span>
                      <div className="ed-judge__confidence-bar">
                        <div className="ed-judge__confidence-fill" style={{ width: `${state.result.confidence}%` }} />
                      </div>
                      <span className="ed-judge__confidence-value">{state.result.confidence}%</span>
                    </div>

                    {state.result.confidence_reason?.length > 0 && (
                      <div className="ed-judge__reasons">
                        <strong>Confidence reasons:</strong>
                        <ul>
                          {state.result.confidence_reason.map((r, i) => <li key={i}>{r}</li>)}
                        </ul>
                      </div>
                    )}

                    {state.result.uncertainties?.length > 0 && (
                      <div className="ed-judge__uncertainties">
                        <strong>Remaining uncertainties:</strong>
                        <ul>
                          {state.result.uncertainties.map((u, i) => <li key={i}>{u}</li>)}
                        </ul>
                      </div>
                    )}

                    {state.result.key_tradeoffs?.length > 0 && (
                      <div className="ed-judge__tradeoffs">
                        <strong>Key trade-offs:</strong>
                        <ul>
                          {state.result.key_tradeoffs.map((t, i) => <li key={i}>{t}</li>)}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </section>
          )}
        </div>
      )}
    </main>
  );
}

export default ExpertDebateStreamPage;
