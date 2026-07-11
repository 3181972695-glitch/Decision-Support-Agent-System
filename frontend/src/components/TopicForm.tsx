import { useState, type FormEvent } from "react";

interface TopicFormProps {
  onSubmit: (topic: string) => void;
  loading: boolean;
}

function TopicForm({ onSubmit, loading }: TopicFormProps) {
  const [topic, setTopic] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (topic.trim()) {
      onSubmit(topic.trim());
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <label htmlFor="topic">What decision do you need help with?</label>
      <input
        id="topic"
        type="text"
        value={topic}
        onChange={(e) => setTopic(e.target.value)}
        placeholder='e.g. "Should I pursue graduate school?"'
        disabled={loading}
        required
      />
      <button type="submit" disabled={loading || !topic.trim()}>
        {loading ? "Starting debate..." : "Start Debate"}
      </button>
    </form>
  );
}

export default TopicForm;
