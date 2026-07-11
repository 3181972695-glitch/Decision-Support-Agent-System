interface AgentMessageProps {
  role: "pro" | "con" | "moderator" | "judge";
  content: string;
}

const LABELS: Record<string, string> = {
  pro: "Pro (FOR)",
  con: "Con (AGAINST)",
  moderator: "Moderator",
  judge: "Judge",
};

function AgentMessage({ role, content }: AgentMessageProps) {
  return (
    <article className={`message message--${role}`}>
      <strong>{LABELS[role] ?? role}</strong>
      <p>{content}</p>
    </article>
  );
}

export default AgentMessage;
