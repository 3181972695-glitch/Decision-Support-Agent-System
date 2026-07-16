interface AgentMessageProps {
  role: string;
  label?: string;
  content: string;
}

const DEFAULT_LABELS: Record<string, string> = {
  pro: "Pro (FOR)",
  "pro-opening": "Pro — Opening Argument",
  "pro-rebuttal": "Pro — Rebuttal",
  "pro-ask": "Pro — Cross-Examination Question",
  "pro-answer": "Pro — Cross-Examination Answer",
  con: "Con (AGAINST)",
  "con-opening": "Con — Opening Argument",
  "con-rebuttal": "Con — Rebuttal",
  "con-ask": "Con — Cross-Examination Question",
  "con-answer": "Con — Cross-Examination Answer",
  moderator: "Moderator",
  "moderator-intro": "Moderator — Round Introduction",
  "moderator-summary": "Moderator — Round Summary",
  "moderator_intro": "Moderator — Round Introduction",
  "moderator_summary": "Moderator — Round Summary",
  judge: "Judge",
};

function resolveBaseRole(role: string): string {
  if (role.startsWith("pro")) return "pro";
  if (role.startsWith("con")) return "con";
  if (role.startsWith("moderator")) return "moderator";
  if (role.startsWith("judge")) return "judge";
  return role;
}

const ROLE_BADGE: Record<string, { bg: string; fg: string; label: string }> = {
  pro: { bg: "#dcfce7", fg: "#15803d", label: "Pro" },
  con: { bg: "#fee2e2", fg: "#b91c1c", label: "Con" },
  moderator: { bg: "#ede9fe", fg: "#6d28d9", label: "Moderator" },
  judge: { bg: "#fef9c3", fg: "#a16207", label: "Judge" },
};

function AgentMessage({ role, label, content }: AgentMessageProps) {
  const displayLabel = label ?? DEFAULT_LABELS[role] ?? role;
  const baseRole = resolveBaseRole(role);
  const badge = ROLE_BADGE[baseRole] ?? {
    bg: "#f3f4f6",
    fg: "#374151",
    label: baseRole,
  };

  return (
    <article className={`message message--${baseRole}`}>
      <header className="message__header">
        <span
          className="message__badge"
          style={{ backgroundColor: badge.bg, color: badge.fg }}
        >
          {badge.label}
        </span>
        <span className="message__label">{displayLabel}</span>
      </header>
      <p>{content}</p>
    </article>
  );
}

export default AgentMessage;
