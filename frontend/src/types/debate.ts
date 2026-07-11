/** Mirrors the backend Pydantic schemas (app/api/schemas.py). */

export type DebateStatus = "pending" | "in_progress" | "completed" | "error";

export interface ArgumentResponse {
  role: string;
  content: string;
  created_at: string | null;
}

export interface RoundResponse {
  round_number: number;
  moderator_summary: string | null;
  moderator_steer: string | null;
  pro_argument: ArgumentResponse | null;
  con_argument: ArgumentResponse | null;
}

export interface VerdictResponse {
  summary: string;
  recommendation: string;
  created_at: string | null;
}

export interface DebateResponse {
  id: string;
  topic: string;
  status: DebateStatus;
  rounds: RoundResponse[];
  verdict: VerdictResponse | null;
  created_at: string;
  updated_at: string | null;
}
