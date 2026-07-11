import { useParams } from "react-router-dom";
import DebateRound from "../components/DebateRound";
import ProgressIndicator from "../components/ProgressIndicator";
import VerdictCard from "../components/VerdictCard";
import ErrorBoundary from "../components/ErrorBoundary";
import { useDebate } from "../hooks/useDebate";

function DebatePage() {
  const { debateId } = useParams<{ debateId: string }>();
  const { debate, loading, error } = useDebate(debateId);
  const roundCount = debate?.rounds.length ?? 0;

  if (!debateId) {
    return (
      <main className="debate-page">
        <p className="error">No debate ID provided.</p>
      </main>
    );
  }

  if (error && !debate) {
    return (
      <main className="debate-page">
        <h1>Debate</h1>
        <div className="error-card">
          <p className="error">{error}</p>
          <a href="/" className="btn-link">Start a new debate</a>
        </div>
      </main>
    );
  }

  const isInProgress = debate?.status === "in_progress";
  const isCompleted = debate?.status === "completed";
  const isError = debate?.status === "error";
  const isPending = debate?.status === "pending";
  const showSkeleton = loading && !debate;

  return (
    <ErrorBoundary>
      <main className="debate-page">
        <h1>{debate?.topic ?? "Loading..."}</h1>

        <ProgressIndicator
          current={roundCount}
          total={3}
          status={debate?.status ?? "pending"}
        />

        {/* Skeleton while waiting for initial data */}
        {showSkeleton && (
          <div className="skeleton-list">
            <div className="skeleton skeleton--title" />
            <div className="skeleton skeleton--text" />
            <div className="skeleton skeleton--text skeleton--short" />
          </div>
        )}

        {/* Loading indicator during in_progress */}
        {isPending && (
          <div className="status-banner status-banner--pending">
            <span className="spinner" />
            <span>Initializing debate...</span>
          </div>
        )}

        {isInProgress && (
          <div className="status-banner status-banner--live">
            <span className="spinner" />
            <span>Debate in progress — new arguments appear as they're generated</span>
          </div>
        )}

        {/* Completed rounds */}
        {debate?.rounds.map((round) => (
          <DebateRound key={round.round_number} round={round} />
        ))}

        {/* Waiting indicator when debate is running but no rounds yet */}
        {isInProgress && roundCount === 0 && (
          <div className="waiting-card">
            <p>Waiting for the first round to complete...</p>
          </div>
        )}

        {/* Error state */}
        {isError && (
          <div className="error-card">
            <h2>Debate Encountered an Error</h2>
            <p>Something went wrong during the debate. Please try again.</p>
            <a href="/" className="btn-link">Start a new debate</a>
          </div>
        )}

        {/* Verdict */}
        {isCompleted && debate?.verdict && (
          <VerdictCard verdict={debate.verdict} />
        )}
      </main>
    </ErrorBoundary>
  );
}

export default DebatePage;
