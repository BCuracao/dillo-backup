"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Plus,
  Trash2,
  Play,
  FlaskConical,
  CheckCircle,
  XCircle,
  Database,
  AlertCircle,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { fetchActivityLogs, type ActivityLogFilters } from "@/lib/api";
import type { ActivityLog } from "@/lib/types";

const POLL_INTERVAL = 5_000;
const DEFAULT_PAGE_SIZE = 15;

interface ActivityFeedProps {
  /** Maximum entries to display. Defaults to 15. */
  limit?: number;
  /** Whether to allow loading more entries beyond the limit. Defaults to false. */
  paginated?: boolean;
  /** Whether to show the section title. Defaults to true. */
  showTitle?: boolean;
  /** Increment to trigger an immediate refresh (e.g. after a job mutation). */
  refreshSignal?: number;
  /** External filters (from the logs page). */
  filters?: ActivityLogFilters;
}

/** Map event types to icons and colors. */
function eventMeta(eventType: ActivityLog["event_type"]) {
  switch (eventType) {
    case "JOB_CREATED":
      return { icon: <Plus size={14} />, color: "text-accent", bg: "bg-accent/10" };
    case "JOB_DELETED":
      return { icon: <Trash2 size={14} />, color: "text-error", bg: "bg-error/10" };
    case "JOB_RUN":
      return { icon: <Play size={14} />, color: "text-foreground", bg: "bg-white/5" };
    case "JOB_DRY_RUN":
      return { icon: <FlaskConical size={14} />, color: "text-yellow-400", bg: "bg-yellow-400/10" };
    case "JOB_COMPLETED":
      return { icon: <CheckCircle size={14} />, color: "text-success", bg: "bg-success/10" };
    case "JOB_FAILED":
      return { icon: <XCircle size={14} />, color: "text-error", bg: "bg-error/10" };
    default:
      return { icon: <Database size={14} />, color: "text-muted", bg: "bg-white/5" };
  }
}

/** Ensure an ISO string is interpreted as UTC even if the suffix is missing. */
function toSafeDate(iso: string): Date {
  if (iso.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(iso)) return new Date(iso);
  return new Date(iso + "Z");
}

/** Relative time label. */
function useRelativeTime(t: ReturnType<typeof useTranslations>) {
  return (iso: string) => {
    const diff = Date.now() - toSafeDate(iso).getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return t("timeAgo.justNow");
    if (mins < 60) return t("timeAgo.minutesAgo", { count: mins });
    const hours = Math.floor(mins / 60);
    if (hours < 24) return t("timeAgo.hoursAgo", { count: hours });
    const days = Math.floor(hours / 24);
    return t("timeAgo.daysAgo", { count: days });
  };
}

export default function ActivityFeed({
  limit = DEFAULT_PAGE_SIZE,
  paginated = false,
  showTitle = true,
  refreshSignal = 0,
  filters,
}: ActivityFeedProps = {}) {
  const pageSize = limit;
  const [logs, setLogs] = useState<ActivityLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(pageSize);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const t = useTranslations("activityFeed");
  const relativeTime = useRelativeTime(t);

  const load = useCallback(async () => {
    try {
      const data = await fetchActivityLogs(visibleCount, 0, filters);
      setLogs(data.logs);
      setTotal(data.total);
      setError(null);
    } catch {
      setError(t("loadError"));
    } finally {
      setLoading(false);
    }
  }, [visibleCount, t, filters]);

  useEffect(() => {
    load();
    intervalRef.current = setInterval(load, POLL_INTERVAL);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [load]);

  // Immediate refresh when parent signals a mutation
  useEffect(() => {
    if (refreshSignal > 0) {
      load();
    }
  }, [refreshSignal]); // eslint-disable-line react-hooks/exhaustive-deps

  // Reset visible count when filters change
  useEffect(() => {
    setVisibleCount(pageSize);
  }, [filters, pageSize]);

  const handleShowMore = () => {
    setVisibleCount((prev) => prev + pageSize);
  };

  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div>
      {showTitle && (
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">{t("title")}</h2>
          <span className="text-xs text-muted">
            {total > 0 ? `${logs.length} / ${total}` : ""}
          </span>
        </div>
      )}

      {error && (
        <div className="mb-3 flex items-center gap-2 rounded-lg bg-error/10 px-4 py-3 text-sm text-error">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {loading && logs.length === 0 && (
        <div className="flex h-32 items-center justify-center rounded-xl border border-dashed border-card-border">
          <p className="text-sm text-muted">{t("title")}...</p>
        </div>
      )}

      {!loading && logs.length === 0 && !error && (
        <div className="flex h-32 items-center justify-center rounded-xl border border-dashed border-card-border">
          <p className="text-sm text-muted">{t("empty")}</p>
        </div>
      )}

      {logs.length > 0 && (
        <div className="rounded-xl border border-card-border bg-card">
          <div className="divide-y divide-card-border">
            {logs.map((log) => {
              const meta = eventMeta(log.event_type);
              const isExpanded = expandedIds.has(log.id);
              const hasDetails = !!log.details;
              return (
                <div
                  key={log.id}
                  className={`px-4 py-3 transition-colors hover:bg-white/[0.02] ${hasDetails ? "cursor-pointer" : ""}`}
                  onClick={hasDetails ? () => toggleExpand(log.id) : undefined}
                >
                  <div className="flex items-start gap-3">
                    {/* Icon */}
                    <div
                      className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${meta.bg}`}
                    >
                      <span className={meta.color}>{meta.icon}</span>
                    </div>

                    {/* Content */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-medium ${meta.color}`}>
                          {t(`events.${log.event_type}`)}
                        </span>
                        <span className="text-[11px] text-muted">
                          {relativeTime(log.timestamp)}
                        </span>
                        <span className="text-[11px] text-muted/60">
                          {toSafeDate(log.timestamp).toLocaleString(undefined, {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      </div>
                      <p className="mt-0.5 truncate text-xs text-foreground/80">
                        <span className="font-medium text-foreground">
                          {log.job_name}
                        </span>
                        {" — "}
                        {log.message}
                      </p>
                      {/* Collapsed: single-line preview */}
                      {hasDetails && !isExpanded && (
                        <p className="mt-0.5 truncate text-[11px] text-muted font-mono">
                          {log.details}
                        </p>
                      )}
                    </div>

                    {/* Expand / collapse indicator */}
                    {hasDetails && (
                      <button
                        className="mt-0.5 shrink-0 text-muted/50 transition-colors hover:text-muted"
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleExpand(log.id);
                        }}
                        aria-label={isExpanded ? "Collapse" : "Expand"}
                      >
                        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                    )}
                  </div>

                  {/* Expanded details */}
                  {hasDetails && isExpanded && (
                    <div className="ml-10 mt-2 rounded-lg bg-background/60 px-3 py-2">
                      <pre className="whitespace-pre-wrap text-[11px] leading-relaxed text-muted font-mono">
                        {log.details}
                      </pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Show More */}
          {paginated && logs.length < total && (
            <div className="border-t border-card-border px-4 py-2.5">
              <button
                onClick={handleShowMore}
                className="w-full text-center text-xs font-medium text-accent transition-colors hover:text-accent-hover"
              >
                {t("showMore")}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
