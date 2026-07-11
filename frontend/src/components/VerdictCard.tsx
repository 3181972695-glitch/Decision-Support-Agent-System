import AgentMessage from "./AgentMessage";
import type { VerdictResponse } from "../types/debate";

interface VerdictCardProps {
  verdict: VerdictResponse;
}

function VerdictCard({ verdict }: VerdictCardProps) {
  return (
    <section className="verdict">
      <h2>Final Verdict</h2>
      <AgentMessage role="judge" content={verdict.summary} />
      <div className="verdict__recommendation">
        <strong>Recommendation:</strong>
        <p>{verdict.recommendation}</p>
      </div>
    </section>
  );
}

export default VerdictCard;
