import type { AgentStatus } from "../types/debate";

interface AgentStatusBadgeProps {
  role: string;
  status: AgentStatus;
}

const ROLE_BADGE: Record<string, { bg: string; fg: string; label: string }> = {
  pro: { bg: "#dcfce7", fg: "#15803d", label: "Pro" },
  con: { bg: "#fee2e2", fg: "#b91c1c", label: "Con" },
  moderator: { bg: "#ede9fe", fg: "#6d28d9", label: "Moderator" },
  judge: { bg: "#fef9c3", fg: "#a16207", label: "Judge" },
};

const STATUS_LABELS: Record<AgentStatus, string> = {
  waiting: "",
  thinking: "thinking…",
  finished: "done",
};

function AgentStatusBadge({ role, status }: AgentStatusBadgeProps) {
  const badge = ROLE_BADGE[role] ?? { bg: "#f3f4f6", fg: "#374151", label: role };
  const statusLabel = STATUS_LABELS[status];

  return (
    <span className="agent-status-badge" style={{ backgroundColor: badge.bg, color: badge.fg }}>
      <span className="agent-status-badge__name">{badge.label}</span>
      {statusLabel && (
        <span className="agent-status-badge__status">
          {status === "thinking" && <span className="agent-status-badge__spinner" />}
          {statusLabel}
        </span>
      )}
    </span>
  );
}

export default AgentStatusBadge;
