import type { DebateResponse } from "../types/debate";

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

export function createDebateApi(topic: string): Promise<DebateResponse> {
  return request("/debates/", {
    method: "POST",
    body: JSON.stringify({ topic }),
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
