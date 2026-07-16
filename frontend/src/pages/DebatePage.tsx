/* eslint-disable no-console */
import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import DebateRound from "../components/DebateRound";
import ProgressIndicator from "../components/ProgressIndicator";
import ProgressTimeline from "../components/ProgressTimeline";
import VerdictCard from "../components/VerdictCard";
import AnalyticsPanel from "../components/AnalyticsPanel";
import ReplayControls from "../components/ReplayControls";
import ErrorBoundary from "../components/ErrorBoundary";
import { continueDebateApi } from "../services/api";
import { useDebateSSE } from "../hooks/useDebateSSE";
import type { ProgressStep } from "../types/debate";

/** Build a progress timeline from the current debate state. */
function buildTimeline(debate: {
  max_rounds: number;
  rounds: Array<{
    round_number: number;
    round_focus: string | null;
    moderator_intro: string | null;
    pro_opening: { content: string } | null;
    con_opening: { content: string } | null;
    cross_examination: Array<unknown>;
    pro_rebuttal: { content: string } | null;
    con_rebuttal: { content: string } | null;
    moderator_summary: string | null;
  }>;
  status: string;
}, currentStep: { role: string; round_number: number } | null): ProgressStep[] {
  const steps: ProgressStep[] = [];
  const isCompleted = debate.status === "completed";

  const ROUND_TEMPLATE = [
    { key: "moderator_intro", label: "Moderator intro", role: "moderator" },
    { key: "pro_opening", label: "Pro argument", role: "pro" },
    { key: "con_opening", label: "Con argument", role: "con" },
    { key: "cross_exam", label: "Cross-examination", role: "moderator" },
    { key: "pro_rebuttal", label: "Pro rebuttal", role: "pro" },
    { key: "con_rebuttal", label: "Con rebuttal", role: "con" },
    { key: "moderator_summary", label: "Moderator summary", role: "moderator" },
  ];

  for (let r = 1; r <= debate.max_rounds; r++) {
    const round = debate.rounds.find((rd) => rd.round_number === r);
    for (const tpl of ROUND_TEMPLATE) {
      let status: "waiting" | "thinking" | "finished" = "waiting";

      if (round) {
        const hasContent = (() => {
          switch (tpl.key) {
            case "moderator_intro": return !!round.moderator_intro;
            case "pro_opening": return !!round.pro_opening;
            case "con_opening": return !!round.con_opening;
            case "cross_exam": return round.cross_examination.length > 0;
            case "pro_rebuttal": return !!round.pro_rebuttal;
            case "con_rebuttal": return !!round.con_rebuttal;
            case "moderator_summary": return !!round.moderator_summary;
            default: return false;
          }
        })();
        if (hasContent) {
          status = "finished";
        } else if (
          !isCompleted &&
          currentStep &&
          currentStep.round_number === r &&
          currentStep.role === tpl.role
        ) {
          status = "thinking";
        }
      } else if (r === debate.rounds.length + 1 && !isCompleted) {
        status = "waiting";
      }

      if (round || r === debate.rounds.length + 1) {
        steps.push({
          round_number: r,
          round_focus: round?.round_focus ?? null,
          step: tpl.key,
          role: tpl.role,
          label: tpl.label,
          status,
        });
      }
    }
  }

  return steps;
}

function DebatePage() {
  const { debateId } = useParams<{ debateId: string }>();
  const { debate, loading } = useDebateSSE(debateId!);
  const roundCount = debate?.rounds.length ?? 0;
  const maxRounds = debate?.max_rounds ?? 3;

  // Replay state
  const [replayMode, setReplayMode] = useState(false);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replayStep, setReplayStep] = useState(0);
  const [replaySpeed, setReplaySpeed] = useState(1);
  const replayTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);



  const currentStep = useMemo(() => {
    if (!debate) return null;
    const activeRound = debate.rounds[debate.rounds.length - 1];
    if (!activeRound) return null;
    if (!activeRound.moderator_intro) return { role: "moderator", round_number: activeRound.round_number };
    if (!activeRound.pro_opening) return { role: "pro", round_number: activeRound.round_number };
    if (!activeRound.con_opening) return { role: "con", round_number: activeRound.round_number };
    if (activeRound.cross_examination.length < 2) return { role: "moderator", round_number: activeRound.round_number };
    if (!activeRound.pro_rebuttal) return { role: "pro", round_number: activeRound.round_number };
    if (!activeRound.con_rebuttal) return { role: "con", round_number: activeRound.round_number };
    if (!activeRound.moderator_summary) return { role: "moderator", round_number: activeRound.round_number };
    return null;
  }, [debate]);

  const timeline = useMemo(() => {
    if (!debate) return [];
    return buildTimeline(debate, currentStep);
  }, [debate, currentStep]);

  // Replay
  const replayTotalSteps = timeline.length;
  const replayDone = replayStep >= replayTotalSteps - 1;

  useEffect(() => {
    if (!replayPlaying || replayDone) {
      if (replayTimerRef.current) {
        clearInterval(replayTimerRef.current);
        replayTimerRef.current = null;
      }
      return;
    }
    const interval = 800 / replaySpeed;
    replayTimerRef.current = setInterval(() => {
      setReplayStep((prev) => {
        if (prev >= replayTotalSteps - 1) {
          setReplayPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, interval);
    return () => {
      if (replayTimerRef.current) {
        clearInterval(replayTimerRef.current);
        replayTimerRef.current = null;
      }
    };
  }, [replayPlaying, replayDone, replaySpeed, replayTotalSteps]);

  const replayTimeline = useMemo(() => {
    if (!replayMode) return timeline;
    return timeline.slice(0, replayStep + 1);
  }, [replayMode, timeline, replayStep]);

  const handleReplayPlay = useCallback(() => {
    if (replayDone) setReplayStep(0);
    setReplayPlaying(true);
  }, [replayDone]);

  const handleReplayPause = useCallback(() => setReplayPlaying(false), []);
  const handleReplayNext = useCallback(() => {
    if (!replayDone) setReplayStep((p) => p + 1);
  }, [replayDone]);
  const handleReplayPrev = useCallback(() => {
    setReplayStep((p) => Math.max(0, p - 1));
  }, []);

  const isInProgress = debate?.status === "in_progress";
  const isCompleted = debate?.status === "completed";
  const isError = debate?.status === "error";
  const isPending = debate?.status === "pending";
  const isAwaitingInput = debate?.awaiting_input === true;

  const showSkeleton = loading && !debate;

  const [continuePending, setContinuePending] = useState(false);

  const handleContinue = async () => {
    const reqId = Date.now();
    console.log(
      "[XDIAG] CONTINUE_REQ-" + reqId + " CLICK",
      "debateId=" + debateId,
      "awaiting_input=" + debate?.awaiting_input,
      "isAwaitingInput=" + isAwaitingInput,
      "timestamp=" + new Date().toISOString(),
    );
    if (!debateId || continuePending) return;
    setContinuePending(true);
    try {
      console.log("[XDIAG] CONTINUE_REQ-" + reqId + " SENDING");
      await continueDebateApi(debateId);
      console.log("[XDIAG] CONTINUE_REQ-" + reqId + " SUCCESS");
    } catch (err) {
      console.error(
        "[XDIAG] CONTINUE_REQ-" + reqId + " FAILED",
        "message=" + (err instanceof Error ? err.message : String(err)),
      );
    } finally {
      setContinuePending(false);
    }
  };

  console.log(
    "[XDIAG] DebatePage render",
    "awaiting_input=", debate?.awaiting_input,
    "isAwaitingInput=", isAwaitingInput,
    "loading=", loading,
    "status=", debate?.status,
    "rounds=", debate?.rounds.length,
  );

  return (
    <ErrorBoundary>
      <main className="debate-page">
        <h1>{debate?.topic ?? "Loading..."}</h1>

        <ProgressIndicator
          current={roundCount}
          total={maxRounds}
          status={debate?.status ?? "pending"}
          debateId={debateId}
        />

        {isInProgress && timeline.length > 0 && (
          <ProgressTimeline steps={timeline} debateId={debateId} />
        )}

        {isCompleted && timeline.length > 0 && (
          <>
            <button
              type="button"
              className="btn-link btn-link--small"
              onClick={() => setReplayMode(!replayMode)}
              style={{ marginBottom: replayMode ? "0.5rem" : "1rem" }}
            >
              {replayMode ? "Exit Replay" : "▶ Replay Debate"}
            </button>
            {replayMode && (
              <>
                <ReplayControls
                  onPlay={handleReplayPlay}
                  onPause={handleReplayPause}
                  onNext={handleReplayNext}
                  onPrev={handleReplayPrev}
                  isPlaying={replayPlaying}
                  currentStep={replayStep}
                  totalSteps={replayTotalSteps}
                  speed={replaySpeed}
                  onSpeedChange={setReplaySpeed}
                />
                <ProgressTimeline steps={replayTimeline} debateId={debateId} />
              </>
            )}
          </>
        )}

        {showSkeleton && (
          <div className="skeleton-list">
            <div className="skeleton skeleton--title" />
            <div className="skeleton skeleton--text" />
            <div className="skeleton skeleton--text skeleton--short" />
          </div>
        )}

        {isPending && (
          <div className="status-banner status-banner--pending">
            <span className="spinner" />
            <span>Initializing debate...</span>
          </div>
        )}

        {isInProgress && !isAwaitingInput && (
          <div className="status-banner status-banner--live">
            <span className="spinner" />
            <span>Debate in progress — new arguments appear as they're generated</span>
          </div>
        )}

        {isAwaitingInput && (
          <div className="status-banner status-banner--awaiting">
            <span>⏸️ Round complete — ask a question or continue</span>
          </div>
        )}

        {debate?.rounds.map((round) => (
          <DebateRound key={round.round_number} round={round} />
        ))}

        {isInProgress && roundCount === 0 && (
          <div className="waiting-card">
            <p>Waiting for the first round to complete...</p>
          </div>
        )}

        {isAwaitingInput && (
          <div className="continue-panel">
            <button
              onClick={handleContinue}
              className="btn btn--primary btn--large"
              disabled={continuePending}
            >
              {continuePending ? "Starting next round..." : "Continue to Next Round →"}
            </button>
          </div>
        )}

        {isError && (
          <div className="error-card">
            <h2>Debate Encountered an Error</h2>
            <p>Something went wrong during the debate. Please try again.</p>
            <Link to="/" className="btn-link">Start a new debate</Link>
          </div>
        )}

        {isCompleted && debate?.verdict && (
          <VerdictCard verdict={debate.verdict} />
        )}

        {isCompleted && debateId && (
          <AnalyticsPanel debateId={debateId} />
        )}
      </main>
    </ErrorBoundary>
  );
}

export default DebatePage;
