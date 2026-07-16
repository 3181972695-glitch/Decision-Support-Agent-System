import type { ProgressStep } from "../types/debate";

interface ProgressTimelineProps {
  steps: ProgressStep[];
  debateId?: string;
}

const ROLE_BADGE: Record<string, { bg: string; fg: string }> = {
  pro: { bg: "#dcfce7", fg: "#15803d" },
  con: { bg: "#fee2e2", fg: "#b91c1c" },
  moderator: { bg: "#ede9fe", fg: "#6d28d9" },
  judge: { bg: "#fef9c3", fg: "#a16207" },
};

const STATUS_ICON: Record<string, string> = {
  waiting: "○",
  thinking: "⏳",
  finished: "✓",
};

function ProgressTimeline({ steps }: ProgressTimelineProps) {
  if (steps.length === 0) return null;

  // Group steps by round
  const grouped: Record<number, ProgressStep[]> = {};
  for (const step of steps) {
    if (!grouped[step.round_number]) grouped[step.round_number] = [];
    grouped[step.round_number].push(step);
  }

  return (
    <div className="progress-timeline">
      {Object.entries(grouped).map(([roundNum, roundSteps]) => (
        <div key={roundNum} className="progress-timeline__round">
          <div className="progress-timeline__round-header">
            <span className="progress-timeline__round-num">
              Round {roundNum}
            </span>
            {roundSteps[0]?.round_focus && (
              <span className="progress-timeline__focus">
                {roundSteps[0].round_focus.slice(0, 60)}
              </span>
            )}
          </div>
          <div className="progress-timeline__steps">
            {roundSteps.map((step, i) => {
              const badge = ROLE_BADGE[step.role] ?? { bg: "#f3f4f6", fg: "#374151" };
              return (
                <div
                  key={`${step.round_number}-${i}`}
                  className={`progress-timeline__step progress-timeline__step--${step.status}`}
                >
                  <span className="progress-timeline__icon">
                    {STATUS_ICON[step.status]}
                  </span>
                  <span
                    className="progress-timeline__badge"
                    style={{ backgroundColor: badge.bg, color: badge.fg }}
                  >
                    {step.role}
                  </span>
                  <span className="progress-timeline__label">{step.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

export default ProgressTimeline;
