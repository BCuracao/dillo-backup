"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Database, Filter, X } from "lucide-react";
import DashboardLayout from "@/components/DashboardLayout";
import ActivityFeed from "@/components/ActivityFeed";
import { fetchActivityJobNames, type ActivityLogFilters } from "@/lib/api";

const EVENT_TYPES = [
  "JOB_CREATED",
  "JOB_DELETED",
  "JOB_RUN",
  "JOB_DRY_RUN",
  "JOB_COMPLETED",
  "JOB_FAILED",
] as const;

export default function LogsPage() {
  const t = useTranslations("logsPage");
  const tEvents = useTranslations("activityFeed.events");

  // Filter state
  const [jobName, setJobName] = useState("");
  const [eventType, setEventType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [jobNames, setJobNames] = useState<string[]>([]);
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    fetchActivityJobNames()
      .then(setJobNames)
      .catch(() => {});
  }, []);

  const filters: ActivityLogFilters | undefined = useMemo(() => {
    const f: ActivityLogFilters = {};
    if (jobName) f.job_name = jobName;
    if (eventType) f.event_type = eventType;
    if (dateFrom) f.date_from = dateFrom;
    if (dateTo) f.date_to = dateTo;
    return Object.keys(f).length > 0 ? f : undefined;
  }, [jobName, eventType, dateFrom, dateTo]);

  const activeFilterCount = [jobName, eventType, dateFrom, dateTo].filter(Boolean).length;

  const clearFilters = () => {
    setJobName("");
    setEventType("");
    setDateFrom("");
    setDateTo("");
  };

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-6xl px-8 py-8">
        {/* Page Header */}
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent/10">
              <Database size={20} className="text-accent" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-foreground">
                {t("title")}
              </h1>
              <p className="mt-0.5 text-sm text-muted">{t("subtitle")}</p>
            </div>
          </div>

          {/* Toggle filters button */}
          <button
            onClick={() => setShowFilters((v) => !v)}
            className={`flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm transition-colors ${
              showFilters || activeFilterCount > 0
                ? "border-accent/40 bg-accent/10 text-accent"
                : "border-card-border text-muted hover:border-accent/30 hover:text-foreground"
            }`}
          >
            <Filter size={14} />
            {t("filters")}
            {activeFilterCount > 0 && (
              <span className="ml-1 flex h-5 w-5 items-center justify-center rounded-full bg-accent text-[10px] font-bold text-white">
                {activeFilterCount}
              </span>
            )}
          </button>
        </div>

        {/* Filter Bar */}
        {showFilters && (
          <div className="mb-6 rounded-xl border border-card-border bg-card p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-xs font-semibold text-foreground">{t("filterTitle")}</h3>
              {activeFilterCount > 0 && (
                <button
                  onClick={clearFilters}
                  className="flex items-center gap-1 text-[11px] text-muted transition-colors hover:text-error"
                >
                  <X size={12} />
                  {t("clearFilters")}
                </button>
              )}
            </div>
            <div className="grid grid-cols-4 gap-3">
              {/* Job Name */}
              <div>
                <label className="mb-1 block text-[11px] font-medium text-muted">
                  {t("filterJob")}
                </label>
                <select
                  value={jobName}
                  onChange={(e) => setJobName(e.target.value)}
                  className="w-full rounded-lg border border-card-border bg-background px-3 py-2 text-xs text-foreground outline-none transition-colors focus:border-accent"
                >
                  <option value="">{t("allJobs")}</option>
                  {jobNames.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Event Type */}
              <div>
                <label className="mb-1 block text-[11px] font-medium text-muted">
                  {t("filterEvent")}
                </label>
                <select
                  value={eventType}
                  onChange={(e) => setEventType(e.target.value)}
                  className="w-full rounded-lg border border-card-border bg-background px-3 py-2 text-xs text-foreground outline-none transition-colors focus:border-accent"
                >
                  <option value="">{t("allEvents")}</option>
                  {EVENT_TYPES.map((et) => (
                    <option key={et} value={et}>
                      {tEvents(et)}
                    </option>
                  ))}
                </select>
              </div>

              {/* Date From */}
              <div>
                <label className="mb-1 block text-[11px] font-medium text-muted">
                  {t("filterFrom")}
                </label>
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className="w-full rounded-lg border border-card-border bg-background px-3 py-2 text-xs text-foreground outline-none transition-colors focus:border-accent"
                />
              </div>

              {/* Date To */}
              <div>
                <label className="mb-1 block text-[11px] font-medium text-muted">
                  {t("filterTo")}
                </label>
                <input
                  type="date"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  className="w-full rounded-lg border border-card-border bg-background px-3 py-2 text-xs text-foreground outline-none transition-colors focus:border-accent"
                />
              </div>
            </div>
          </div>
        )}

        {/* Activity Feed — 100 entries, paginated, with filters */}
        <ActivityFeed limit={100} paginated showTitle={false} filters={filters} />
      </div>
    </DashboardLayout>
  );
}
