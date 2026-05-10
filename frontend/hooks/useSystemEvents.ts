"use client";

import { useEffect, useRef } from "react";
import { fetchSystemEvents } from "@/lib/api";
import type { SystemEvent } from "@/lib/types";

const POLL_INTERVAL = 4_000; // 4 seconds — slightly faster than the jobs poll

/**
 * Polls the backend for runtime system events (drive insertions, Auto-Wake
 * triggers, etc.) and dispatches them to *onEvent* in chronological order.
 *
 * The hook tracks the highest event id seen so each event is delivered
 * exactly once across re-renders within the same session.
 */
export function useSystemEvents(
  onEvent: (event: SystemEvent) => void,
  enabled: boolean = true,
): void {
  const lastIdRef = useRef<number>(0);
  // Stable callback ref so consumers can pass inline functions safely.
  const callbackRef = useRef(onEvent);
  useEffect(() => {
    callbackRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        const { events, last_id } = await fetchSystemEvents(lastIdRef.current);
        if (cancelled) return;
        if (events.length > 0) {
          for (const event of events) {
            callbackRef.current(event);
          }
        }
        // Use the server's reported last_id even when no events were returned
        // so we stay aligned across browser sleeps and clock skews.
        if (last_id > lastIdRef.current) {
          lastIdRef.current = last_id;
        }
      } catch {
        // Backend unavailable / network blip — silently retry next tick.
      } finally {
        if (!cancelled) {
          timer = setTimeout(tick, POLL_INTERVAL);
        }
      }
    };

    // Prime the cursor without firing toasts for events that occurred before
    // the page mounted.
    fetchSystemEvents(0)
      .then(({ last_id }) => {
        if (!cancelled) lastIdRef.current = last_id;
      })
      .catch(() => {
        /* noop */
      })
      .finally(() => {
        if (!cancelled) timer = setTimeout(tick, POLL_INTERVAL);
      });

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [enabled]);
}
