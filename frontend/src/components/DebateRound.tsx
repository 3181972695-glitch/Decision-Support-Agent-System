import AgentMessage from "./AgentMessage";
import type { RoundResponse } from "../types/debate";

interface DebateRoundProps {
  round: RoundResponse;
}

function DebateRound({ round }: DebateRoundProps) {
  const hasCrossExam = round.cross_examination.length > 0;
  const hasUserQuestions = round.user_questions.length > 0;
  const hasRebuttals = round.pro_rebuttal || round.con_rebuttal;

  return (
    <section className="round">
      <details open>
        <summary>
          <h2>Round {round.round_number}</h2>
          {round.round_focus && (
            <span className="round__focus">{round.round_focus}</span>
          )}
        </summary>

        <div className="round__content">
          {/* 1. Moderator Introduction */}
          {round.moderator_intro && (
            <div className="round__section">
              <AgentMessage
                role="moderator-intro"
                content={round.moderator_intro}
              />
            </div>
          )}

          {/* 2. Opening Arguments */}
          <div className="round__section round__section--openings">
            <h3>Opening Arguments</h3>
            {round.pro_opening && (
              <AgentMessage
                role="pro-opening"
                content={round.pro_opening.content}
              />
            )}
            {round.con_opening && (
              <AgentMessage
                role="con-opening"
                content={round.con_opening.content}
              />
            )}
          </div>

          {/* 3. Cross-Examination */}
          {hasCrossExam && (
            <div className="round__section round__section--cross">
              <h3>Cross-Examination</h3>
              {round.cross_examination.map((qa, idx) => {
                console.log(
                  "[XDIAG] RENDER R" + round.round_number + "_CE" + idx,
                  "q_role=" + qa.question_role,
                  "q_len=" + (qa.question?.length || 0),
                  "q_type=" + typeof qa.question,
                  "q_preview=" + (qa.question || "").substring(0, 60),
                  "a_role=" + qa.answer_role,
                  "a_len=" + (qa.answer?.length || 0),
                  "a_preview=" + (qa.answer || "").substring(0, 60),
                );
                return (
                <div key={idx} className="cross-qa">
                  <div className="cross-qa__pair">
                    <AgentMessage
                      role={`${qa.question_role}-ask`}
                      content={qa.question}
                    />
                    <AgentMessage
                      role={`${qa.answer_role}-answer`}
                      content={qa.answer}
                    />
                  </div>
                </div>
                );
              })}
            </div>
          )}

          {/* 4. Rebuttals */}
          {hasRebuttals && (
            <div className="round__section round__section--rebuttals">
              <h3>Rebuttals</h3>
              {round.pro_rebuttal && (
                <AgentMessage
                  role="pro-rebuttal"
                  content={round.pro_rebuttal.content}
                />
              )}
              {round.con_rebuttal && (
                <AgentMessage
                  role="con-rebuttal"
                  content={round.con_rebuttal.content}
                />
              )}
            </div>
          )}

          {/* 5. User Questions */}
          {hasUserQuestions && (
            <div className="round__section round__section--user-questions">
              <h3>Your Questions</h3>
              {round.user_questions.map((uq, idx) => (
                <div key={idx} className="user-qa">
                  <div className="user-qa__question">
                    <strong>You asked {uq.target_role === "pro" ? "Pro" : uq.target_role === "con" ? "Con" : "Moderator"}:</strong>
                    <p>{uq.question}</p>
                  </div>
                  <AgentMessage
                    role={uq.target_role}
                    content={uq.answer}
                  />
                </div>
              ))}
            </div>
          )}

          {/* 6. Moderator Summary */}
          {round.moderator_summary && (
            <div className="round__section round__section--summary">
              <h3>Moderator Summary</h3>
              <AgentMessage
                role="moderator-summary"
                content={round.moderator_summary}
              />
            </div>
          )}
        </div>
      </details>
    </section>
  );
}

export default DebateRound;
