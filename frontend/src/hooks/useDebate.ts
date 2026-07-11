import { useState, useEffect, useCallback, useRef } from "react";
import { createDebateApi, startDebateApi, getDebateApi } from "../services/api";
import type { DebateResponse } from "../types/debate";

interface UseDebateResult {
  debate: DebateResponse | null;
  loading: boolean;
  error: string | null;
  createDebate: (topic: string) => Promise<DebateResponse | null>;
}

export function useDebate(debateId?: string): UseDebateResult {
  const [debate, setDebate] = useState<DebateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startedRef = useRef(false);

  // ── DebatePage flow: start the debate, then poll for progress ──
  useEffect(() => {
    if (!debateId) return;
    if (startedRef.current) return;
    startedRef.current = true;

    const startAndPoll = async () => {
      setLoading(true);
      setError(null);

      try {
        // Start the debate (non-blocking — returns IN_PROGRESS immediately)
        const started = await startDebateApi(debateId);
        setDebate(started);

        // Poll every 1.5s while the debate is in progress
        pollingRef.current = setInterval(async () => {
          try {
            const data = await getDebateApi(debateId);
            setDebate(data);
            if (data.status !== "in_progress") {
              if (pollingRef.current) clearInterval(pollingRef.current);
              setLoading(false);
            }
          } catch {
            // Silently retry on next interval
          }
        }, 1500);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to start debate");
        setLoading(false);
      }
    };

    startAndPoll();

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [debateId]);

  // ── HomePage flow: create a new debate ──
  const createDebate = useCallback(
    async (topic: string): Promise<DebateResponse | null> => {
      setLoading(true);
      setError(null);
      try {
        const created = await createDebateApi(topic);
        setDebate(created);
        return created;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create debate");
        return null;
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  return { debate, loading, error, createDebate };
}
