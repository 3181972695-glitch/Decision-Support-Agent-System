import { useState, useRef, useCallback, useEffect } from "react";
import type { ExpertDebateResponse } from "../services/api";

export interface StreamingState {
  /** Current phase label */
  phase: "idle" | "expert_generation" | "analysis" | "debate" | "judge" | "complete" | "error";
  /** Accumulated streaming text per expert (keyed by role) */
  expertTexts: Record<string, string>;
  /** Key arguments per expert (set when expert_done fires) */
  expertArguments: Record<string, string[]>;
  /** Streamed debate round text (keyed by "speaker→target") */
  debateTexts: Record<string, string>;
  /** Judge text being streamed */
  judgeText: string;
  /** Parsed generated experts (dynamic mode) */
  generatedExperts: Array<{ role: string; expertise: string }>;
  /** Expert order (to preserve insertion order in UI) */
  expertOrder: string[];
  /** Debate round order */
  debateOrder: string[];
  /** Final structured result (set when result event fires) */
  result: ExpertDebateResponse | null;
  /** Error message */
  error: string | null;
  /** Expert that is currently streaming */
  currentExpert: string | null;
  /** Current debate pair streaming */
  currentDebate: { speaker: string; response_to: string } | null;
  /** Whether judge is streaming */
  judgeStreaming: boolean;
  /** Tool execution log */
  toolCalls: Array<{
    expert: string;
    tool: string;
    status: "running" | "complete";
    arguments?: Record<string, string>;
    result?: string;
  }>;
}

const INITIAL: StreamingState = {
  phase: "idle",
  expertTexts: {},
  expertArguments: {},
  debateTexts: {},
  judgeText: "",
  generatedExperts: [],
  expertOrder: [],
  debateOrder: [],
  result: null,
  error: null,
  currentExpert: null,
  currentDebate: null,
  judgeStreaming: false,
  toolCalls: [],
};

interface UseExpertDebateStreamResult {
  state: StreamingState;
  startDebate: (mode: string, question: string) => void;
  reset: () => void;
}

export function useExpertDebateStream(): UseExpertDebateStreamResult {
  const [state, setState] = useState<StreamingState>(INITIAL);
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    setState(INITIAL);
  }, []);

  const startDebate = useCallback((mode: string, question: string) => {
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setState({ ...INITIAL, phase: "idle" });

    const body = JSON.stringify({ mode, question });

    fetch("/api/expert/debate/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) {
        const errBody = await response.json().catch(() => null);
        setState((s) => ({
          ...s,
          phase: "error",
          error: errBody?.detail ?? `HTTP ${response.status}`,
        }));
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        let currentEvent = "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("event:")) {
            currentEvent = trimmed.slice(6).trim();
          } else if (trimmed.startsWith("data:")) {
            const raw = trimmed.slice(5).trim();
            try {
              const data = JSON.parse(raw);
              processEvent(currentEvent, data);
            } catch {
              // skip malformed JSON
            }
          }
        }
      }
    }).catch((err) => {
      if (err.name !== "AbortError") {
        setState((s) => ({ ...s, phase: "error", error: err.message }));
      }
    });

    function processEvent(eventType: string, data: Record<string, unknown>) {
      setState((prev) => {
        switch (eventType) {
          case "error":
            return { ...prev, phase: "error", error: (data.message as string) ?? "Unknown error" };

          case "expert_generation":
            if (data.status === "started") return { ...prev, phase: "expert_generation" };
            if (data.status === "complete") return prev; // stays on this phase until next phase event
            return prev;

          case "expert_generated": {
            const role = data.role as string;
            const expertise = data.expertise as string;
            if (prev.generatedExperts.some((e) => e.role === role)) return prev;
            return {
              ...prev,
              generatedExperts: [...prev.generatedExperts, { role, expertise }],
            };
          }

          case "phase":
            if (data.status === "complete") return { ...prev, phase: "complete" };
            return { ...prev, phase: data.status as StreamingState["phase"] };

          case "expert_start": {
            const role = data.role as string;
            const order = prev.expertOrder.includes(role) ? prev.expertOrder : [...prev.expertOrder, role];
            return {
              ...prev,
              currentExpert: role,
              currentDebate: null,
              judgeStreaming: false,
              expertOrder: order,
            };
          }

          case "analysis_chunk": {
            const role = data.role as string;
            const content = data.content as string;
            const current = prev.expertTexts[role] ?? "";
            return {
              ...prev,
              expertTexts: { ...prev.expertTexts, [role]: current + content },
            };
          }

          case "expert_done": {
            const role = data.role as string;
            const args = (data.arguments as string[]) ?? [];
            return {
              ...prev,
              currentExpert: null,
              expertArguments: { ...prev.expertArguments, [role]: args },
            };
          }

          case "debate_start": {
            const speaker = data.speaker as string;
            const target = data.response_to as string;
            const key = `${speaker}→${target}`;
            const order = prev.debateOrder.includes(key) ? prev.debateOrder : [...prev.debateOrder, key];
            return {
              ...prev,
              currentDebate: { speaker, response_to: target },
              currentExpert: null,
              judgeStreaming: false,
              debateOrder: order,
            };
          }

          case "debate_chunk": {
            const speaker = data.speaker as string;
            const target = data.response_to as string;
            const key = `${speaker}→${target}`;
            const content = data.content as string;
            // For debate_start we need to set currentDebate
            return {
              ...prev,
              currentDebate: prev.currentDebate ?? { speaker, response_to: target },
              debateTexts: {
                ...prev.debateTexts,
                [key]: (prev.debateTexts[key] ?? "") + content,
              },
            };
          }

          case "debate_done":
            return { ...prev, currentDebate: null };

          case "tool_call": {
            const expert = data.expert as string;
            const tool = data.tool as string;
            const args = data.arguments as Record<string, string> | undefined;
            return {
              ...prev,
              toolCalls: [...prev.toolCalls, { expert, tool, status: "running" as const, arguments: args }],
            };
          }

          case "tool_result": {
            const expert = data.expert as string;
            const tool = data.tool as string;
            const result = data.result as string;
            return {
              ...prev,
              toolCalls: prev.toolCalls.map((tc) =>
                tc.expert === expert && tc.tool === tool && tc.status === "running"
                  ? { ...tc, status: "complete" as const, result }
                  : tc
              ),
            };
          }

          case "judge_start":
            return { ...prev, judgeStreaming: true, currentExpert: null, currentDebate: null };

          case "judge_chunk": {
            const content = data.content as string;
            return { ...prev, judgeText: prev.judgeText + content };
          }

          case "judge_done": {
            // After judge_done we expect a result event with full data
            return { ...prev, judgeStreaming: false };
          }

          case "result": {
            const result = data as unknown as ExpertDebateResponse;
            return { ...prev, result, phase: "complete" };
          }

          default:
            return prev;
        }
      });
    }
  }, []);

  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  return { state, startDebate, reset };
}
