"use client";

import { useEffect } from "react";
import { pingDashboardHeartbeat } from "@/lib/api";

const HEARTBEAT_INTERVAL_MS = 5_000;

/**
 * Pings the backend's heartbeat endpoint every few seconds while the
 * dashboard tab is visible.  The system tray (running inside the launcher)
 * uses the heartbeat to suppress OS-native toasts when the user is already
 * looking at the in-browser activity feed.
 *
 * The hook deliberately *stops* sending heartbeats when the tab is hidden
 * (background tab, minimised window, locked screen) so the tray correctly
 * promotes the user into "tray-only" mode.
 */
export function useDashboardHeartbeat(enabled: boolean = true): void {
  useEffect(() => {
    if (!enabled) return;
    if (typeof document === "undefined") return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = () => {
      if (cancelled) return;
      if (document.visibilityState === "visible") {
        pingDashboardHeartbeat().catch(() => {
          /* backend transient error — try again next tick */
        });
      }
      timer = setTimeout(tick, HEARTBEAT_INTERVAL_MS);
    };

    // Fire immediately so the tray sees us within ~one heartbeat of mount.
    tick();

    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        pingDashboardHeartbeat().catch(() => {
          /* noop */
        });
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [enabled]);
}
