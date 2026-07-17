/** Mirrors the backend Pydantic schemas (app/api/schemas.py). */

export type DebateStatus = "pending" | "in_progress" | "completed" | "error";

export interface DebateConfig {
  topic: string;
  max_rounds: number;
  enable_cross_exam: boolean;
  enable_moderator: boolean;
  enable_user_questions: boolean;
}

export interface ArgumentResponse {
  role: string;
  content: string;
  created_at: string | null;
}

export interface CrossExaminationResponse {
  question_role: string;
  question: string;
  answer_role: string;
  answer: string;
}

export interface UserQuestionResponse {
  target_role: string;
  question: string;
  answer: string;
}

export interface RoundResponse {
  round_number: number;
  round_focus: string | null;
  moderator_intro: string | null;
  pro_opening: ArgumentResponse | null;
  con_opening: ArgumentResponse | null;
  cross_examination: CrossExaminationResponse[];
  pro_rebuttal: ArgumentResponse | null;
  con_rebuttal: ArgumentResponse | null;
  user_questions: UserQuestionResponse[];
  moderator_summary: string | null;
  moderator_steer: string | null;
}


export interface JudgeEvaluationResponse {
  winner: string;
  scores: Record<string, number>;
  confidence: number;
  strengths: string[];
  weaknesses: string[];
}

export interface VerdictResponse {
  summary: string;
  recommendation: string;
  evaluation: JudgeEvaluationResponse | null;
  created_at: string | null;
}

export interface DebateResponse {
  id: string;
  topic: string;
  max_rounds: number;
  status: DebateStatus;
  rounds: RoundResponse[];
  verdict: VerdictResponse | null;
  awaiting_input?: boolean;
  created_at: string;
  updated_at: string | null;
}

/** Agent status for the progress timeline. */
export type AgentStatus = "waiting" | "thinking" | "finished";

/** Step in the debate progress timeline. */
export interface ProgressStep {
  round_number: number;
  round_focus: string | null;
  step: string;
  role: string;
  label: string;
  status: AgentStatus;
}
