interface ReplayControlsProps {
  onPlay: () => void;
  onPause: () => void;
  onNext: () => void;
  onPrev: () => void;
  isPlaying: boolean;
  currentStep: number;
  totalSteps: number;
  speed: number;
  onSpeedChange: (speed: number) => void;
}

const SPEEDS = [0.5, 1, 2, 3, 5];

function ReplayControls({
  onPlay,
  onPause,
  onNext,
  onPrev,
  isPlaying,
  currentStep,
  totalSteps,
  speed,
  onSpeedChange,
}: ReplayControlsProps) {
  return (
    <div className="replay-controls">
      <button onClick={onPrev} disabled={currentStep <= 0} title="Previous">
        ⏮
      </button>
      <button onClick={isPlaying ? onPause : onPlay} title={isPlaying ? "Pause" : "Play"}>
        {isPlaying ? "⏸" : "▶️"}
      </button>
      <button onClick={onNext} disabled={currentStep >= totalSteps - 1} title="Next">
        ⏭
      </button>
      <span style={{ fontSize: "0.8rem", color: "#6b7280" }}>
        {currentStep + 1} / {totalSteps}
      </span>
      <div className="replay-controls__speed">
        <label>Speed:</label>
        <select value={speed} onChange={(e) => onSpeedChange(Number(e.target.value))}>
          {SPEEDS.map((s) => (
            <option key={s} value={s}>{s}x</option>
          ))}
        </select>
      </div>
    </div>
  );
}

export default ReplayControls;
