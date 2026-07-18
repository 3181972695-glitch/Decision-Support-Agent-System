import type { DebateConfig, DebateResponse } from "../types/debate";

const BASE_URL = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${res.status})`);
  }

  return res.json() as Promise<T>;
}

export function createDebateApi(config: DebateConfig): Promise<DebateResponse> {
  return request("/debates/", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export function startDebateApi(debateId: string): Promise<DebateResponse> {
  return request(`/debates/${debateId}/start`, {
    method: "POST",
  });
}

export function getDebateApi(debateId: string): Promise<DebateResponse> {
  return request(`/debates/${debateId}`);
}

export function continueDebateApi(debateId: string): Promise<DebateResponse> {
  return request(`/debates/${debateId}/continue`, {
    method: "POST",
  });
}

export function submitQuestionsApi(
  debateId: string,
  proQuestion: string,
  conQuestion: string,
): Promise<DebateResponse> {
  return request(`/debates/${debateId}/questions`, {
    method: "POST",
    body: JSON.stringify({
      pro_question: proQuestion,
      con_question: conQuestion,
    }),
  });
}

export interface PerformanceSummary {
  debate_id: string;
  status: string;
  rounds_completed: number;
  total_llm_calls: number;
  total_duration_s: number;
  average_latency_s: number;
  slowest_call_s: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_reasoning_tokens: number;
  estimated_cost: string | number | null;
  calls: Array<{
    role: string;
    model: string;
    duration: number;
    input_tokens: number;
    output_tokens: number;
    reasoning_tokens: number;
    retry_count: number;
  }>;
}

export function getPerformanceApi(debateId: string): Promise<PerformanceSummary> {
  return request(`/debates/${debateId}/performance`);
}

// ── Expert Mode ───────────────────────────────────────────────────

export interface ExpertRequest {
  mode: string;
  question: string;
}

export interface ExpertAnalysis {
  role: string;
  analysis: string;
}

export interface ExpertResponse {
  mode: string;
  question: string;
  experts: ExpertAnalysis[];
  final_decision: string;
}

export function expertAnalyzeApi(payload: ExpertRequest): Promise<ExpertResponse> {
  return request("/expert/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── Expert Debate Mode ───────────────────────────────────────────

export interface ExpertDebateRequest {
  mode: string;
  question: string;
}

export interface ExpertDebateAnalysis {
  role: string;
  analysis: string;
  arguments: string[];
}

export interface DebateRound {
  speaker: string;
  response_to: string;
  content: string;
}

export interface GeneratedExpert {
  role: string;
  expertise: string;
}

export interface ExpertDebateResponse {
  mode: string;
  question: string;
  generated_experts: GeneratedExpert[];
  experts: ExpertDebateAnalysis[];
  debate_rounds: DebateRound[];
  final_decision: string;
  confidence: number;
  confidence_reason: string[];
  uncertainties: string[];
  key_tradeoffs: string[];
}

// ── Memory System ─────────────────────────────────────────────────

export interface MemoryItem {
  id: number;
  user_id: string;
  memory_type: string;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
  relevance?: number;
}

export interface MemoryListResponse {
  memories: MemoryItem[];
  total: number;
}

export function listMemoriesApi(
  memoryType?: string,
  limit?: number,
): Promise<MemoryListResponse> {
  const params = new URLSearchParams();
  if (memoryType) params.set("memory_type", memoryType);
  if (limit) params.set("limit", String(limit));
  return request(`/memory?${params.toString()}`);
}

export function createMemoryApi(
  content: string,
  memoryType: string = "decision",
  metadata?: Record<string, unknown>,
): Promise<MemoryItem> {
  return request("/memory", {
    method: "POST",
    body: JSON.stringify({
      content,
      memory_type: memoryType,
      metadata: metadata ?? {},
    }),
  });
}

export function deleteMemoryApi(memoryId: number): Promise<void> {
  return request(`/memory/${memoryId}`, { method: "DELETE" });
}

export function updateMemoryApi(
  memoryId: number,
  content: string,
  memoryType?: string,
): Promise<MemoryItem> {
  return request(`/memory/${memoryId}`, {
    method: "PUT",
    body: JSON.stringify({ content, memory_type: memoryType ?? "decision" }),
  });
}

export function clearAllMemoriesApi(): Promise<{ deleted: number }> {
  return request("/memory/clear", { method: "DELETE" });
}

export function expertDebateApi(payload: ExpertDebateRequest): Promise<ExpertDebateResponse> {
  return request("/expert/debate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
