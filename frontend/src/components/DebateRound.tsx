import AgentMessage from "./AgentMessage";
import type { RoundResponse } from "../types/debate";

interface DebateRoundProps {
  round: RoundResponse;
}

function DebateRound({ round }: DebateRoundProps) {
  return (
    <section>
      <h2>Round {round.round_number}</h2>

      {round.moderator_steer && (
        <AgentMessage role="moderator" content={round.moderator_steer} />
      )}

      {round.pro_argument && (
        <AgentMessage role="pro" content={round.pro_argument.content} />
      )}

      {round.con_argument && (
        <AgentMessage role="con" content={round.con_argument.content} />
      )}
    </section>
  );
}

export default DebateRound;
