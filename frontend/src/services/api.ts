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
