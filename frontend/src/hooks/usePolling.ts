import { useEffect, useRef } from "react";

/**
 * Generic interval-based poller.
 *
 * Calls `callback` every `intervalMs` while `enabled` is true.
 * The callback receives an `abort` signal to cleanly stop polling
 * from inside the callback (e.g. when a target status is reached).
 */
export function usePolling(
  callback: (signal: AbortSignal) => void | Promise<void>,
  intervalMs: number = 1500,
  enabled: boolean = true,
) {
  const savedCallback = useRef(callback);
  savedCallback.current = callback;

  useEffect(() => {
    if (!enabled) return;

    const controller = new AbortController();
    const tick = async () => {
      if (!controller.signal.aborted) {
        await savedCallback.current(controller.signal);
      }
    };

    // Fire immediately, then on interval
    tick();
    const id = setInterval(tick, intervalMs);

    return () => {
      controller.abort();
      clearInterval(id);
    };
  }, [intervalMs, enabled]);
}
