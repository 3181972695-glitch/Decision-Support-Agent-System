/* eslint-disable no-console */
import { useState, useEffect, useRef, useCallback } from "react";
import { startDebateApi, getDebateApi } from "../services/api";
import type { DebateResponse } from "../types/debate";

// ═══════════════════════════════════════════════════════════════
//  TRACE helpers
// ═══════════════════════════════════════════════════════════════

const T = (...args: unknown[]) => console.log("[TRACE]", ...args);

function stateSnapshot(debate: DebateResponse | null, label: string, extra: Record<string, unknown> = {}) {
  if (!debate) {
    T(`[STATE ${label}]`, "debate=null", extra);
    return;
  }
  const r = debate.rounds;
  const last = r.length > 0 ? r[r.length - 1] : null;
  T(`[STATE ${label}]`, {
    status: debate.status,
    rounds: r.length,
    maxRounds: debate.max_rounds,
    awaiting_input: debate.awaiting_input,
    lastRound: last?.round_number ?? null,
    hasModIntro: !!last?.moderator_intro,
    hasProOpening: !!last?.pro_opening?.content,
    hasConOpening: !!last?.con_opening?.content,
    xExamCount: last?.cross_examination?.length ?? 0,
    hasProRebuttal: !!last?.pro_rebuttal?.content,
    hasConRebuttal: !!last?.con_rebuttal?.content,
    hasModSummary: !!last?.moderator_summary,
    hasVerdict: !!debate.verdict,
    ...extra,
  });
}

interface UseDebateSSEResult {
  debate: DebateResponse | null;
  loading: boolean;
  error: string | null;
  updateDebate: (updater: DebateResponse | ((prev: DebateResponse | null) => DebateResponse | null)) => void;
}

export function useDebateSSE(debateId: string): UseDebateSSEResult {
  const [debate, setDebate] = useState<DebateResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startedRef = useRef<string | null>(null);
  const mountedRef = useRef(true);
  const sseActiveRef = useRef(false);
  // Track last received seq for gap detection
  const lastSeqRef = useRef(0);
  const lastEventRef = useRef("");
  const requestIdRef = useRef(0);
  const lastAppliedRef = useRef(0);
  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Polling (fallback) ────────────────────────────────────────

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      T("[POLLING] stop");
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    if (pollingRef.current) return;
    T("[POLLING] start SSE_active=", sseActiveRef.current);
    sseActiveRef.current = false;
    let pollCount = 0;
    pollingRef.current = setInterval(async () => {
      pollCount++;
      if (!mountedRef.current) return;
      T(`[POLLING] fired #${pollCount} SSE_active=${sseActiveRef.current}`);
      if (sseActiveRef.current) {
        T("[POLLING] skipped reason=SSE_active");
        return;
      }
      try {
        const data = await getDebateApi(debateId);
        if (!mountedRef.current) return;
        T(`[POLLING] GET ${debateId} → status=${data.status} rounds=${data.rounds.length} awaiting_input=${data.awaiting_input}`);
        setDebate((prev) => {
          if (!prev) { T("[POLLING] applied reason=prev_null"); return data; }
          if (sseActiveRef.current) { T("[POLLING] skipped reason=SSE_reactivated"); return prev; }
          T("[POLLING] applied");
          return data;
        });
        if (data.status !== "in_progress") {
          stopPolling();
          setLoading(false);
        }
      } catch {
        T("[POLLING] error retrying");
      }
    }, 1500);
  }, [debateId, stopPolling]);

  // ── Mount tracking ────────────────────────────────────────────

  useEffect(() => {
    mountedRef.current = true;
    T("[MOUNT] true");
    return () => {
      mountedRef.current = false;
      T("[MOUNT] false");
    };
  }, []);

  // ── Main connection effect ────────────────────────────────────

  useEffect(() => {
    if (!debateId) return;
    if (startedRef.current !== debateId) {
      T(`[CONNECT] new debateId=${debateId}`);
      startedRef.current = debateId;
    } else {
      T(`[CONNECT] already connected debateId=${debateId}`);
      return;
    }

    setLoading(true);
    setError(null);
    sseActiveRef.current = false;
    lastSeqRef.current = 0;
    lastEventRef.current = "";

    const connect = async () => {
      try {
        // First, GET the current debate state. If it's already in progress
        // or completed, subscribe to SSE without calling /start again.
        // This prevents 400 errors on page refresh.
        T("[CONNECT] fetching current debate state");
        let current: DebateResponse;
        try {
          current = await getDebateApi(debateId);
        } catch {
          // Debate not found — try creating/starting it
          T("[CONNECT] debate not found, calling startDebateApi");
          current = await startDebateApi(debateId);
        }
        if (!mountedRef.current) { T("[CONNECT] unmounted after fetch"); return; }

        if (current.status === "pending") {
          T("[CONNECT] debate is pending, calling startDebateApi");
          current = await startDebateApi(debateId);
          if (!mountedRef.current) { T("[CONNECT] unmounted after start"); return; }
        }

        T(`[CONNECT] current status=${current.status}`);
        setDebate(current);
        stateSnapshot(current, "AFTER connect");

        const sseUrl = `/api/debates/${debateId}/stream`;
        T(`[CONNECT] opening EventSource url=${sseUrl}`);
        const es = new EventSource(sseUrl);
        eventSourceRef.current = es;
        sseActiveRef.current = true;

        // ── Periodic refresh alongside SSE ─────────────────────────
        // Safety net: if SSE events were emitted before the queue
        // existed (race at startup), the frontend never advances past
        // "Waiting for the first round to complete...". This timer
        // catches up by checking if the API has more rounds than the
        // current React state. Unlike polling, this runs regardless
        // of sseActiveRef — it only updates when progress is detected.
        refreshTimerRef.current = setInterval(async () => {
          if (!mountedRef.current) return;
          try {
            const data = await getDebateApi(debateId);
            if (!mountedRef.current) return;
            setDebate((prev) => {
              if (!prev) return data;
              // Only replace when API shows more rounds or has reached
              // a terminal state — never overwrite live streaming.
              if (data.rounds.length > prev.rounds.length) {
                T("[REFRESH] more rounds, updating", prev.rounds.length, "→", data.rounds.length);
                return data;
              }
              if (data.status !== "in_progress" && prev.status === "in_progress") {
                T("[REFRESH] terminal state, updating", data.status);
                return data;
              }
              return prev;
            });
          } catch {
            // Silently retry
          }
        }, 2000);

        // ═════════════════════════════════════════════════════════
        //  SSE event handlers
        // ═════════════════════════════════════════════════════════

        es.addEventListener("agent_chunk", (event) => {
          if (!mountedRef.current) { T("[EVENT] agent_chunk ignored=unmounted"); return; }
          try {
            const data = JSON.parse(event.data);
            const seq = data.seq ?? 0;
            const gap = lastSeqRef.current > 0 && seq !== lastSeqRef.current + 1;
            if (gap) T(`[EVENT] agent_chunk SEQ_GAP prev=${lastSeqRef.current} current=${seq} gap=${seq - lastSeqRef.current - 1}`);
            lastSeqRef.current = seq;
            lastEventRef.current = "agent_chunk";
            T(`[EVENT] agent_chunk seq=${seq} role=${data.role} round=${data.round_number} chars=${data.content?.length ?? 0}`);
            setDebate((prev) => {
              if (!prev) { T("[EVENT] agent_chunk skipped reason=prev_null"); return prev; }
              const before = prev.rounds.length;
              const result = applyChunk(prev, data);
              const after = result.rounds.length;
              T(`[CHUNK] applied role=${data.role} rounds=${before}→${after} chars=${data.content?.length ?? 0}`);
              return result;
            });
          } catch {
            T("[EVENT] agent_chunk PARSE_ERROR");
          }
        });

        es.addEventListener("agent_done", (event) => {
          if (!mountedRef.current) { T("[EVENT] agent_done ignored=unmounted"); return; }
          try {
            const data = JSON.parse(event.data);
            const seq = data.seq ?? 0;
            lastSeqRef.current = seq;
            lastEventRef.current = "agent_done";
            T(`[EVENT] agent_done seq=${seq} role=${data.role} round=${data.round_number}`);
          } catch {
            T("[EVENT] agent_done role=unknown");
          }
          // PURE UI SIGNAL — no state mutation
        });

        es.addEventListener("agent_start", (event) => {
          if (!mountedRef.current) return;
          try {
            const data = JSON.parse(event.data);
            const seq = data.seq ?? 0;
            lastSeqRef.current = seq;
            lastEventRef.current = "agent_start";
            T(`[EVENT] agent_start seq=${seq} role=${data.role} round=${data.round_number}`);
          } catch {
            T("[EVENT] agent_start role=unknown");
          }
        });

        es.addEventListener("round_start", (event) => {
          if (!mountedRef.current) return;
          try {
            const data = JSON.parse(event.data);
            const seq = data.seq ?? 0;
            lastSeqRef.current = seq;
            lastEventRef.current = "round_start";
            T(`[EVENT] round_start seq=${seq} round=${data.round_number}`);
          } catch {
            T("[EVENT] round_start");
          }
        });

        es.addEventListener("round_done", (event) => {
          if (!mountedRef.current) { T("[EVENT] round_done ignored=unmounted"); return; }
          try {
            const data = JSON.parse(event.data);
            const seq = data.seq ?? 0;
            lastSeqRef.current = seq;
            lastEventRef.current = "round_done";
            T(`[EVENT] round_done seq=${seq} round=${data.round_number} -> calling getDebateApi`);
          } catch {
            T("[EVENT] round_done -> calling getDebateApi");
          }
          const reqId = ++requestIdRef.current;
          console.log("[XDIAG] REQ-" + reqId + " START round_done refresh");
          getDebateApi(debateId)
            .then((data) => {
              if (!mountedRef.current) { console.log("[XDIAG] REQ-" + reqId + " DISCARD unmounted"); return; }
              console.log("[XDIAG] REQ-" + reqId + " FINISHED status=" + data.status + " rounds=" + data.rounds.length);
              // Dump EVERY cross_exam item
              for (const rd of data.rounds) {
                for (let i = 0; i < (rd.cross_examination || []).length; i++) {
                  const ce = rd.cross_examination[i];
                  console.log(
                    "[XDIAG] REQ-" + reqId + " API_RESPONSE R" + rd.round_number + "_CE" + i,
                    "q_role=" + ce.question_role,
                    "q_len=" + (ce.question?.length || 0),
                    "q_type=" + typeof ce.question,
                    "q_preview=" + (ce.question || "NULL").substring(0, 60),
                    "a_role=" + ce.answer_role,
                    "a_len=" + (ce.answer?.length || 0),
                    "a_preview=" + (ce.answer || "NULL").substring(0, 60),
                  );
                }
              }
              // Check if a newer request already applied
              if (reqId < lastAppliedRef.current) {
                console.log("[XDIAG] REQ-" + reqId + " DISCARD newer=" + lastAppliedRef.current + " already applied");
                return;
              }
              console.log("[XDIAG] REQ-" + reqId + " BEFORE setDebate");
              setDebate(data);
              lastAppliedRef.current = reqId;
              console.log("[XDIAG] REQ-" + reqId + " APPLIED");
              // Safety net: setLoading(false) here in case SSE drops
              // before awaiting_input fires. If awaiting_input already
              // fired this is a no-op.
              setLoading(false);
            })
            .catch((err) => {
              console.error("[XDIAG] REQ-" + reqId + " FAILED", {
                message: err instanceof Error ? err.message : String(err),
                timestamp: new Date().toISOString(),
                debateId: debateId,
              });
              setLoading(false);
            });
        });

        es.addEventListener("awaiting_input", (event) => {
          if (!mountedRef.current) { T("[EVENT] awaiting_input ignored=unmounted"); return; }
          try {
            const data = JSON.parse(event.data);
            const seq = data.seq ?? 0;
            lastSeqRef.current = seq;
            lastEventRef.current = "awaiting_input";
            T(`[EVENT] awaiting_input seq=${seq}`);
          } catch {
            T("[EVENT] awaiting_input");
          }
          T("[EVENT] awaiting_input → setLoading(false)");
          setLoading(false);
        });

        es.addEventListener("debate_complete", (event) => {
          if (!mountedRef.current) { T("[EVENT] debate_complete ignored=unmounted"); return; }
          try {
            const data = JSON.parse(event.data);
            const seq = data.seq ?? 0;
            lastSeqRef.current = seq;
            lastEventRef.current = "debate_complete";
            T(`[EVENT] debate_complete seq=${seq}`);
          } catch {
            T("[EVENT] debate_complete");
          }
          getDebateApi(debateId)
            .then((data) => {
              if (!mountedRef.current) { T("[EVENT] debate_complete refresh ignored=unmounted"); return; }
              T(`[EVENT] debate_complete refresh status=${data.status} rounds=${data.rounds.length}`);
              console.log("[XDIAG] debate_complete refresh debate.awaiting_input=", data.awaiting_input);
              for (const rd of data.rounds) {
                for (let i = 0; i < (rd.cross_examination || []).length; i++) {
                  const ce = rd.cross_examination[i];
                  console.log("[XDIAG] debate_complete refresh R" + rd.round_number + "_CE" + i,
                    "q_role=" + ce.question_role, "q_len=" + (ce.question?.length || 0), "q_preview=" + (ce.question || "").substring(0, 40),
                    "a_role=" + ce.answer_role, "a_len=" + (ce.answer?.length || 0), "a_preview=" + (ce.answer || "").substring(0, 40));
                }
              }
              stateSnapshot(data, "BEFORE debate_complete setDebate");
              setDebate(data);
              setLoading(false);
              stateSnapshot(data, "AFTER debate_complete setDebate");
            })
            .catch((err) => {
              T("[EVENT] debate_complete refresh ERROR", err);
              setLoading(false);
            });
          T("[EVENT] debate_complete → closing EventSource");
          es.close();
          eventSourceRef.current = null;
          sseActiveRef.current = false;
        });

        es.addEventListener("debate_error", (event) => {
          if (!mountedRef.current) { T("[EVENT] debate_error ignored=unmounted"); return; }
          try {
            const data = JSON.parse(event.data);
            const seq = data.seq ?? 0;
            lastSeqRef.current = seq;
            lastEventRef.current = "debate_error";
            T(`[EVENT] debate_error seq=${seq} message=${data.message}`);
            setError(data.message || "Debate encountered an error");
          } catch {
            T("[EVENT] debate_error");
            setError("Debate encountered an error");
          }
          setLoading(false);
          T("[EVENT] debate_error → closing EventSource");
          es.close();
          eventSourceRef.current = null;
          sseActiveRef.current = false;
        });

        es.addEventListener("debate_started", (event) => {
          if (!mountedRef.current) return;
          try {
            const data = JSON.parse(event.data);
            const seq = data.seq ?? 0;
            lastSeqRef.current = seq;
            lastEventRef.current = "debate_started";
            T(`[EVENT] snapshot seq=${seq} status=${data.status} rounds=${data.rounds}`);
          } catch {
            T("[EVENT] snapshot");
          }
        });

        es.addEventListener("verdict_start", (event) => {
          if (!mountedRef.current) return;
          try {
            const data = JSON.parse(event.data);
            const seq = data.seq ?? 0;
            lastSeqRef.current = seq;
            lastEventRef.current = "verdict_start";
            T(`[EVENT] verdict_start seq=${seq}`);
          } catch {
            T("[EVENT] verdict_start");
          }
        });

        es.addEventListener("verdict_done", (event) => {
          if (!mountedRef.current) return;
          try {
            const data = JSON.parse(event.data);
            const seq = data.seq ?? 0;
            lastSeqRef.current = seq;
            lastEventRef.current = "verdict_done";
            T(`[EVENT] verdict_done seq=${seq}`);
          } catch {
            T("[EVENT] verdict_done");
          }
        });

        es.onerror = () => {
          T("[EVENT] SSE onerror → closing and falling back to polling");
          es.close();
          eventSourceRef.current = null;
          sseActiveRef.current = false;
          if (!pollingRef.current) {
            startPolling();
          }
        };
      } catch (err) {
        T("[CONNECT] startDebateApi FAILED", err);
        if (!mountedRef.current) return;
        setError(err instanceof Error ? err.message : "Failed to start debate");
        setLoading(false);
      }
    };

    connect();

    return () => {
      T("[CLEANUP] effect unmounting");
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
      sseActiveRef.current = false;
      stopPolling();
      startedRef.current = null;
    };
  }, [debateId, startPolling, stopPolling]);

  return { debate, loading, error, updateDebate: setDebate };
}

// ═══════════════════════════════════════════════════════════════
//  applyChunk — fully instrumented
// ═══════════════════════════════════════════════════════════════

function applyChunk(
  debate: DebateResponse,
  chunk: { role: string; round_number: number; content: string },
): DebateResponse {
  const rounds = [...debate.rounds];
  let round = rounds.find((r) => r.round_number === chunk.round_number);

  if (!round) {
    if (chunk.round_number < 1) {
      T(`[CHUNK] IGNORED role=${chunk.role} reason=round_number_lt_1 rn=${chunk.round_number}`);
      return debate;
    }
    T(`[CHUNK] NEW_ROUND role=${chunk.role} round=${chunk.round_number}`);
    round = {
      round_number: chunk.round_number,
      round_focus: null,
      moderator_intro: null,
      pro_opening: null,
      con_opening: null,
      cross_examination: [],
      pro_rebuttal: null,
      con_rebuttal: null,
      user_questions: [],
      moderator_summary: null,
      moderator_steer: null,
    };
    rounds.push(round);
  }

  const role = chunk.role;
  const existing = (() => {
    switch (role) {
      case "moderator_intro":  return round.moderator_intro ?? "";
      case "moderator_summary": return round.moderator_summary ?? "";
      case "pro":              return round.pro_opening?.content ?? "";
      case "con":              return round.con_opening?.content ?? "";
      case "pro-rebuttal":     return round.pro_rebuttal?.content ?? "";
      case "con-rebuttal":     return round.con_rebuttal?.content ?? "";
      case "pro-question":
      case "con-question":
      case "pro-answer":
      case "con-answer":
        return ""; // accumulated below in cross_examination array
      case "judge":
        return ""; // canonical state from round_done/debate_complete refresh
      default:
        return "";
    }
  })();

  const updated = existing + chunk.content;
  const chars = chunk.content?.length ?? 0;

  switch (role) {
    case "moderator_intro":
      round = { ...round, moderator_intro: updated };
      T(`[CHUNK] role=${role} target=round.moderator_intro chars=${chars} total=${updated.length}`);
      break;
    case "moderator_summary":
      round = { ...round, moderator_summary: updated };
      T(`[CHUNK] role=${role} target=round.moderator_summary chars=${chars} total=${updated.length}`);
      break;
    case "pro":
      round = { ...round, pro_opening: { role: "pro", content: updated, created_at: null } };
      T(`[CHUNK] role=${role} target=round.pro_opening chars=${chars} total=${updated.length}`);
      break;
    case "con":
      round = { ...round, con_opening: { role: "con", content: updated, created_at: null } };
      T(`[CHUNK] role=${role} target=round.con_opening chars=${chars} total=${updated.length}`);
      break;
    case "pro-rebuttal":
      round = { ...round, pro_rebuttal: { role: "pro", content: updated, created_at: null } };
      T(`[CHUNK] role=${role} target=round.pro_rebuttal chars=${chars} total=${updated.length}`);
      break;
    case "con-rebuttal":
      round = { ...round, con_rebuttal: { role: "con", content: updated, created_at: null } };
      T(`[CHUNK] role=${role} target=round.con_rebuttal chars=${chars} total=${updated.length}`);
      break;
    case "pro-question": {
      // Accumulate Pro's cross-exam question into cross_examination[0]
      while (round.cross_examination.length < 1) {
        round.cross_examination.push({ question_role: "pro", question: "", answer_role: "con", answer: "" });
      }
      round = { ...round, cross_examination: round.cross_examination.map((qa, i) =>
        i === 0 ? { ...qa, question: qa.question + chunk.content } : qa
      )};
      T(`[CHUNK] role=${role} target=cross_exam[0].question chars=${chars} total=${round.cross_examination[0]?.question.length ?? 0}`);
      break;
    }
    case "con-question": {
      // Accumulate Con's cross-exam question into cross_examination[1]
      while (round.cross_examination.length < 2) {
        round.cross_examination.push({ question_role: "con", question: "", answer_role: "pro", answer: "" });
      }
      round = { ...round, cross_examination: round.cross_examination.map((qa, i) =>
        i === 1 ? { ...qa, question: qa.question + chunk.content } : qa
      )};
      T(`[CHUNK] role=${role} target=cross_exam[1].question chars=${chars} total=${round.cross_examination[1]?.question.length ?? 0}`);
      break;
    }
    case "con-answer": {
      // Accumulate Con's answer to Pro's question into cross_examination[0]
      while (round.cross_examination.length < 1) {
        round.cross_examination.push({ question_role: "pro", question: "", answer_role: "con", answer: "" });
      }
      round = { ...round, cross_examination: round.cross_examination.map((qa, i) =>
        i === 0 ? { ...qa, answer: qa.answer + chunk.content } : qa
      )};
      T(`[CHUNK] role=${role} target=cross_exam[0].answer chars=${chars} total=${round.cross_examination[0]?.answer.length ?? 0}`);
      break;
    }
    case "pro-answer": {
      // Accumulate Pro's answer to Con's question into cross_examination[1]
      while (round.cross_examination.length < 2) {
        round.cross_examination.push({ question_role: "con", question: "", answer_role: "pro", answer: "" });
      }
      round = { ...round, cross_examination: round.cross_examination.map((qa, i) =>
        i === 1 ? { ...qa, answer: qa.answer + chunk.content } : qa
      )};
      T(`[CHUNK] role=${role} target=cross_exam[1].answer chars=${chars} total=${round.cross_examination[1]?.answer.length ?? 0}`);
      break;
    }
    case "judge":
      T(`[CHUNK] IGNORED role=${role} reason=canonical_from_refresh chars=${chars}`);
      break;
    default:
      T(`[CHUNK] IGNORED role=${role} reason=unknown_role chars=${chars}`);
      break;
  }

  const newRounds = rounds.map((r) =>
    r.round_number === chunk.round_number ? round : r,
  );

  return {
    ...debate,
    rounds: newRounds.sort((a, b) => a.round_number - b.round_number),
  };
}
