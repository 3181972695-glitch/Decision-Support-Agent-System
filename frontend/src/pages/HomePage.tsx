import { useNavigate } from "react-router-dom";
import TopicForm from "../components/TopicForm";
import { useDebate } from "../hooks/useDebate";
import type { DebateConfig } from "../types/debate";

function HomePage() {
  const navigate = useNavigate();
  const { createDebate, loading, error } = useDebate();

  const handleSubmit = async (config: DebateConfig) => {
    const debate = await createDebate(config);
    if (debate) {
      sessionStorage.setItem(
        `debate-config-${debate.id}`,
        JSON.stringify({ enable_user_questions: config.enable_user_questions }),
      );
      navigate(`/debate/${debate.id}`);
    }
  };

  return (
    <main className="home-page">
      <div className="hero">
        <h1>Decision Support Agent System</h1>
        <p className="hero__subtitle">
          Enter a decision you're facing, and let our AI agents debate both sides
          to help you make a better choice.
        </p>
      </div>
      <TopicForm onSubmit={handleSubmit} loading={loading} />
      {error && <p className="error">{error}</p>}
    </main>
  );
}

export default HomePage;
