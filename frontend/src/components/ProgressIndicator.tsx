import { useState, useEffect } from "react";

interface ProgressIndicatorProps {
  current: number;
  total: number;
  status: string;
  debateId?: string;
}

/** Known sub-steps in a round, in order. */
const ROUND_STEPS = [
  { key: "moderator_intro", label: "Moderator introduction", role: "moderator" },
  { key: "pro_opening", label: "Pro argument", role: "pro" },
  { key: "con_opening", label: "Con argument", role: "con" },
  { key: "cross_exam", label: "Cross-examination", role: "moderator" },
  { key: "pro_rebuttal", label: "Pro rebuttal", role: "pro" },
  { key: "con_rebuttal", label: "Con rebuttal", role: "con" },
  { key: "moderator_summary", label: "Moderator summary", role: "moderator" },
];

function ProgressIndicator({ current, total, status, debateId }: ProgressIndicatorProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (status !== "in_progress") return;
    const start = Date.now();
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [status, debateId]);

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  };

  const isCompleted = status === "completed";
  const isError = status === "error";

  return (
    <div className="progress-indicator">
      <div className="progress-indicator__header">
        <span className="progress-indicator__rounds">
          {isCompleted ? "✓ Complete" : isError ? "✗ Error" : `Round ${current} of ${total}`}
        </span>
        {status === "in_progress" && (
          <span className="progress-indicator__timer">
            <span className="spinner" />
            {formatTime(elapsed)}
          </span>
        )}
      </div>
      <div className="progress-indicator__bar">
        <div
          className="progress-indicator__fill"
          style={{
            width: isCompleted ? "100%" : `${Math.max((current / total) * 100, 5)}%`,
          }}
        />
      </div>
    </div>
  );
}

export default ProgressIndicator;
export { ROUND_STEPS };
