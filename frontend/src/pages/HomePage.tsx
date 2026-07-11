import { useNavigate } from "react-router-dom";
import TopicForm from "../components/TopicForm";
import { useDebate } from "../hooks/useDebate";

function HomePage() {
  const navigate = useNavigate();
  const { createDebate, loading, error } = useDebate();

  const handleSubmit = async (topic: string) => {
    const debate = await createDebate(topic);
    if (debate) {
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
