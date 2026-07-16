import { useState, type FormEvent } from "react";
import type { DebateConfig } from "../types/debate";

export interface TopicFormConfig extends DebateConfig {
  moderator_model?: string;
  argument_model?: string;
  judge_model?: string;
}

interface TopicFormProps {
  onSubmit: (config: TopicFormConfig) => void;
  loading: boolean;
}

const ROUND_OPTIONS = [1, 2, 3, 5, 7];

function TopicForm({ onSubmit, loading }: TopicFormProps) {
  const [topic, setTopic] = useState("");
  const [maxRounds, setMaxRounds] = useState(3);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [enableCrossExam, setEnableCrossExam] = useState(true);
  const [enableModerator, setEnableModerator] = useState(true);
  const [moderatorModel, setModeratorModel] = useState("");
  const [argumentModel, setArgumentModel] = useState("");
  const [judgeModel, setJudgeModel] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (topic.trim()) {
      onSubmit({
        topic: topic.trim(),
        max_rounds: maxRounds,
        enable_cross_exam: enableCrossExam,
        enable_moderator: enableModerator,
        moderator_model: moderatorModel || undefined,
        argument_model: argumentModel || undefined,
        judge_model: judgeModel || undefined,
      });
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

      <div className="form-row">
        <label htmlFor="rounds">Rounds:</label>
        <select
          id="rounds"
          value={maxRounds}
          onChange={(e) => setMaxRounds(Number(e.target.value))}
          disabled={loading}
          className="round-select"
        >
          {ROUND_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n} {n === 1 ? "round" : "rounds"}
            </option>
          ))}
        </select>
      </div>

      <button
        type="button"
        className="btn-link btn-link--small"
        onClick={() => setShowAdvanced(!showAdvanced)}
      >
        {showAdvanced ? "▾ Hide advanced" : "▸ Advanced options"}
      </button>

      {showAdvanced && (
        <div className="advanced-panel">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={enableCrossExam}
              onChange={(e) => setEnableCrossExam(e.target.checked)}
              disabled={loading}
            />
            <span>Cross-examination</span>
            <small>Pro and Con question each other between arguments</small>
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={enableModerator}
              onChange={(e) => setEnableModerator(e.target.checked)}
              disabled={loading}
            />
            <span>Moderator</span>
            <small>Introductions and summaries for each round</small>
          </label>

          <div className="model-selector">
            <div className="model-selector__row">
              <label>Moderator:</label>
              <input
                type="text"
                value={moderatorModel}
                onChange={(e) => setModeratorModel(e.target.value)}
                placeholder="default (fast)"
                disabled={loading}
              />
            </div>
            <div className="model-selector__row">
              <label>Pro / Con:</label>
              <input
                type="text"
                value={argumentModel}
                onChange={(e) => setArgumentModel(e.target.value)}
                placeholder="default (reasoning)"
                disabled={loading}
              />
            </div>
            <div className="model-selector__row">
              <label>Judge:</label>
              <input
                type="text"
                value={judgeModel}
                onChange={(e) => setJudgeModel(e.target.value)}
                placeholder="default (fast)"
                disabled={loading}
              />
            </div>
          </div>
        </div>
      )}

      <button type="submit" disabled={loading || !topic.trim()}>
        {loading ? "Starting debate..." : "Start Debate"}
      </button>
    </form>
  );
}

export default TopicForm;
