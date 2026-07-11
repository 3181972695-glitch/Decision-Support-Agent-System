import type { DebateStatus } from "../types/debate";

interface ProgressIndicatorProps {
  current: number;
  total: number;
  status: DebateStatus;
}

function ProgressIndicator({ current, total, status }: ProgressIndicatorProps) {
  const isComplete = status === "completed";
  const isError = status === "error";
  const isInProgress = status === "in_progress";

  const label = isComplete
    ? "Debate Complete"
    : isError
      ? "Debate Failed"
      : isInProgress
        ? `Round ${Math.min(current + 1, total)} of ${total}`
        : `Round ${Math.min(current, total)} of ${total}`;

  return (
    <div className={`progress progress--${status}`}>
      <span className="progress__label">{label}</span>
      <progress
        className="progress__bar"
        value={isError ? 0 : current}
        max={total}
      />
    </div>
  );
}

export default ProgressIndicator;
