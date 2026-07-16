import AgentMessage from "./AgentMessage";
import type { VerdictResponse } from "../types/debate";

interface VerdictCardProps {
  verdict: VerdictResponse;
}

const SCORE_LABELS: Record<string, string> = {
  logic: "Logic",
  evidence: "Evidence",
  rebuttal: "Rebuttal",
  consistency: "Consistency",
  clarity: "Clarity",
};

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="score-bar">
      <span className="score-bar__label">{label}</span>
      <div className="score-bar__track">
        <div
          className="score-bar__fill"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="score-bar__value">{pct}</span>
    </div>
  );
}

function VerdictCard({ verdict }: VerdictCardProps) {
  const eval_ = verdict.evaluation;
  const winnerLabel = eval_?.winner === "pro" ? "Pro Wins" : eval_?.winner === "con" ? "Con Wins" : null;

  return (
    <section className="verdict">
      <h2>Final Verdict</h2>

      {winnerLabel && (
        <div className={`verdict__winner-badge verdict__winner-badge--${eval_!.winner}`}>
          <span className="verdict__trophy">{eval_!.winner === "pro" ? "🏆" : "🏆"}</span>
          {winnerLabel}
          {eval_?.confidence != null && (
            <span className="verdict__confidence">
              — {Math.round(eval_!.confidence * 100)}% confidence
            </span>
          )}
        </div>
      )}

      <AgentMessage role="judge" content={verdict.summary} />

      {eval_?.scores && Object.keys(eval_.scores).length > 0 && (
        <div className="verdict__scores">
          <h3>Scores</h3>
          {Object.entries(eval_.scores).map(([key, value]) => (
            <ScoreBar
              key={key}
              label={SCORE_LABELS[key] ?? key}
              value={value}
            />
          ))}
        </div>
      )}

      {eval_?.strengths && eval_.strengths.length > 0 && (
        <div className="verdict__strengths">
          <h3>Strengths</h3>
          <ul>
            {eval_.strengths.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}

      {eval_?.weaknesses && eval_.weaknesses.length > 0 && (
        <div className="verdict__weaknesses">
          <h3>Weaknesses</h3>
          <ul>
            {eval_.weaknesses.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="verdict__recommendation">
        <strong>Recommendation:</strong>
        <p>{verdict.recommendation}</p>
      </div>
    </section>
  );
}

export default VerdictCard;
