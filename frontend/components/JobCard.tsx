"use client";

import { useState } from "react";
import {
  ArrowRight,
  CirclePlay,
  Clock,
  FolderOpen,
  FolderOutput,
  HardDrive,
  Pause,
  Play,
  Trash2,
  FlaskConical,
  Pencil,
  MoreVertical,
  ScanSearch,
  ShieldCheck,
} from "lucide-react";
import { useTranslations } from "next-intl";
import type { BackupEstimate, BackupJob } from "@/lib/types";
import { runJob, deleteJob, updateJob, estimateBackup } from "@/lib/api";
import StatusBadge from "./StatusBadge";
import { useToast } from "./ToastProvider";

const DAYS_OF_WEEK = [
  "sunday", "monday", "tuesday", "wednesday",
  "thursday", "friday", "saturday",
] as const;

/** Parse a cron expression into a human-readable schedule label. */
function describeCron(
  cron: string | null | undefined,
  t: ReturnType<typeof useTranslations>,
  tSchedule: ReturnType<typeof useTranslations>,
): string {
  if (!cron || !cron.trim()) return t("schedule.manual");

  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return t("schedule.manual");

  const [minStr, hourStr, domStr, , dowStr] = parts;
  const minute = parseInt(minStr) || 0;
  const hour = parseInt(hourStr) || 0;
  const pad = (n: number) => n.toString().padStart(2, "0");
  const time = `${pad(hour)}:${pad(minute)}`;

  if (hourStr === "*" && domStr === "*" && dowStr === "*") {
    return t("schedule.hourly", { minute: pad(minute) });
  }
  if (domStr === "*" && dowStr !== "*") {
    const dayIdx = parseInt(dowStr) || 0;
    const dayKey = DAYS_OF_WEEK[dayIdx] ?? "sunday";
    return t("schedule.weekly", { day: tSchedule(`days.${dayKey}`), time });
  }
  if (domStr !== "*" && dowStr === "*") {
    return t("schedule.monthly", { dayOfMonth: parseInt(domStr) || 1, time });
  }
  if (domStr === "*" && dowStr === "*") {
    return t("schedule.daily", { time });
  }

  return t("schedule.manual");
}

interface JobCardProps {
  job: BackupJob;
  onMutate: () => Promise<void>;
  onEdit: (job: BackupJob) => void;
}

export default function JobCard({ job, onMutate, onEdit }: JobCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [estimate, setEstimate] = useState<BackupEstimate | null>(null);
  const [estimating, setEstimating] = useState(false);
  const t = useTranslations("jobCard");
  const tToast = useTranslations("toast");
  const tSchedule = useTranslations("schedulePicker");
  const { addToast } = useToast();

  const isPaused = !job.is_active;
  const logStatus = job.latest_log?.status ?? "IDLE";
  const status = isPaused ? "PAUSED" : logStatus;
  const scheduleLabel = describeCron(job.schedule_cron, t, tSchedule);
  const isRunning = logStatus === "RUNNING" || running;

  const handleTogglePause = async () => {
    setMenuOpen(false);
    try {
      await updateJob(job.id, { is_active: isPaused });
      addToast(
        "success",
        isPaused
          ? tToast("jobResumed", { name: job.name })
          : tToast("jobPaused", { name: job.name })
      );
      await onMutate();
    } catch {
      addToast("error", tToast("actionFailed"));
    }
  };

  const handleEstimate = async () => {
    setMenuOpen(false);
    setEstimating(true);
    setEstimate(null);
    try {
      const result = await estimateBackup(job.id);
      setEstimate(result);
    } catch {
      addToast("error", tToast("actionFailed"));
    } finally {
      setEstimating(false);
    }
  };

  const handleRun = async (dryRun: boolean, verify: boolean = false) => {
    setRunning(true);
    setMenuOpen(false);
    try {
      await runJob(job.id, { dry_run: dryRun, verify_after_copy: verify });
      const mode = dryRun
        ? tToast("modeDryRun")
        : verify
          ? tToast("modeVerified")
          : tToast("modeLive");
      addToast("success", tToast("jobQueued", { name: job.name, mode }));
      setTimeout(() => onMutate(), 800);
    } catch {
      addToast("error", tToast("actionFailed"));
    } finally {
      setTimeout(() => setRunning(false), 2000);
    }
  };

  const handleDelete = async () => {
    if (!confirm(t("deleteConfirm", { name: job.name }))) return;
    setMenuOpen(false);
    try {
      await deleteJob(job.id);
      addToast("success", tToast("jobDeleted", { name: job.name }));
      await onMutate();
    } catch {
      addToast("error", tToast("actionFailed"));
    }
  };

  const formatSize = (mb: number) => {
    if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
    return `${mb.toFixed(1)} MB`;
  };

  const formatTime = (iso: string) => {
    const date = new Date(iso);
    // If the ISO string lacks timezone info, treat it as UTC
    const safeDate = iso.endsWith("Z") || iso.includes("+") || iso.includes("T") && iso.match(/[+-]\d{2}:\d{2}$/)
      ? date
      : new Date(iso + "Z");
    return safeDate.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className={`group relative rounded-xl border border-card-border bg-card p-5 transition-colors hover:border-accent/30 ${isPaused ? "opacity-60" : ""}`}>
      {/* Header row */}
      <div className="mb-4 flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent/10">
            <FolderOpen size={18} className="text-accent" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">{job.name}</h3>
            <div className="mt-0.5 flex items-center gap-2">
              <p className="text-[11px] text-muted">
                {t("created", { time: formatTime(job.created_at) })}
              </p>
              <span className="text-[11px] text-muted">·</span>
              <span className="inline-flex items-center gap-1 text-[11px] text-muted">
                <Clock size={10} className="shrink-0" />
                {scheduleLabel}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <StatusBadge status={status as "RUNNING" | "SUCCESS" | "ERROR" | "IDLE" | "PAUSED"} />

          {/* Context menu */}
          <div className="relative">
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="rounded-md p-1.5 text-muted transition-colors hover:bg-white/5 hover:text-foreground"
            >
              <MoreVertical size={16} />
            </button>

            {menuOpen && (
              <div className="absolute right-0 top-full z-10 mt-1 w-44 rounded-lg border border-card-border bg-[#1a1a1a] py-1 shadow-xl">
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    onEdit(job);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-muted transition-colors hover:bg-white/5 hover:text-foreground"
                >
                  <Pencil size={14} />
                  {t("actions.editJob")}
                </button>
                <button
                  onClick={handleTogglePause}
                  className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors ${
                    isPaused
                      ? "text-success/80 hover:bg-success/10 hover:text-success"
                      : "text-warning/80 hover:bg-warning/10 hover:text-warning"
                  }`}
                >
                  {isPaused ? <CirclePlay size={14} /> : <Pause size={14} />}
                  {isPaused ? t("actions.resumeJob") : t("actions.pauseJob")}
                </button>
                <button
                  onClick={() => handleRun(true)}
                  disabled={isPaused}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-muted transition-colors hover:bg-white/5 hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
                >
                  <FlaskConical size={14} />
                  {t("actions.dryRun")}
                </button>
                <button
                  onClick={() => handleRun(false, true)}
                  disabled={isPaused}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-success/80 transition-colors hover:bg-success/10 hover:text-success disabled:pointer-events-none disabled:opacity-40"
                >
                  <ShieldCheck size={14} />
                  {t("actions.verifiedRun")}
                </button>
                <button
                  onClick={handleEstimate}
                  disabled={isPaused || estimating}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-muted transition-colors hover:bg-white/5 hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
                >
                  <ScanSearch size={14} />
                  {t("actions.estimate")}
                </button>
                <button
                  onClick={handleDelete}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-error/80 transition-colors hover:bg-error/10 hover:text-error"
                >
                  <Trash2 size={14} />
                  {t("actions.deleteJob")}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Path display */}
      <div className="mb-4 flex items-center gap-2 rounded-lg bg-background/60 px-3 py-2.5">
        <FolderOpen size={14} className="shrink-0 text-muted" />
        <span className="truncate text-xs text-foreground/80 font-mono">
          {job.source_path}
        </span>
        <ArrowRight size={14} className="shrink-0 text-accent" />
        <FolderOutput size={14} className="shrink-0 text-muted" />
        <span className="truncate text-xs text-foreground/80 font-mono">
          {job.dest_path}
        </span>
      </div>

      {/* Stats row (hidden while running — live progress takes over) */}
      {job.latest_log && !isRunning && (
        <div className="mb-4 flex gap-4 text-xs text-muted">
          <span>
            <strong className="text-foreground/80">
              {job.latest_log.files_processed}
            </strong>{" "}
            {t("stats.filesCopied")}
          </span>
          <span>
            <strong className="text-foreground/80">
              {job.latest_log.files_skipped}
            </strong>{" "}
            {t("stats.skipped")}
          </span>
          <span>
            <strong className="text-foreground/80">
              {formatSize(job.latest_log.total_size_mb)}
            </strong>{" "}
            {t("stats.total")}
          </span>
        </div>
      )}

      {/* Estimate result */}
      {(estimate || estimating) && (
        <div className="mb-4 rounded-lg bg-accent/5 border border-accent/10 px-3 py-2">
          {estimating ? (
            <div className="flex items-center gap-2 text-xs text-muted">
              <ScanSearch size={14} className="animate-pulse text-accent" />
              {t("estimate.scanning")}
            </div>
          ) : estimate && (
            <div className="flex items-center gap-4 text-xs text-muted">
              <span className="flex items-center gap-1">
                <HardDrive size={12} className="text-accent" />
                <strong className="text-foreground/80">{estimate.total_files}</strong>{" "}
                {t("estimate.filesToCopy")}
              </span>
              <span>
                <strong className="text-foreground/80">
                  {estimate.estimated_size_mb >= 1024
                    ? `${(estimate.estimated_size_mb / 1024).toFixed(1)} GB`
                    : `${estimate.estimated_size_mb.toFixed(1)} MB`}
                </strong>
              </span>
              <span>
                ~{estimate.estimated_time_seconds < 60
                  ? `${Math.ceil(estimate.estimated_time_seconds)}s`
                  : `${Math.ceil(estimate.estimated_time_seconds / 60)} min`}
              </span>
              {estimate.skipped_files > 0 && (
                <span className="text-success/80">
                  {estimate.skipped_files} {t("estimate.upToDate")}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Live progress (shown when running) */}
      {isRunning && (
        <div className="mb-4">
          {job.latest_log && job.latest_log.status === "RUNNING" && (job.latest_log.files_processed > 0 || job.latest_log.files_skipped > 0) ? (
            <div className="flex items-center gap-4 rounded-lg bg-accent/5 border border-accent/10 px-3 py-2">
              <div className="h-2 w-2 rounded-full bg-accent animate-pulse shrink-0" />
              <div className="flex items-center gap-3 text-xs text-muted">
                <span>{t("progress.filesCopied", { count: job.latest_log.files_processed })}</span>
                <span className="text-muted/60">·</span>
                <span>{t("progress.skipped", { count: job.latest_log.files_skipped })}</span>
                <span className="text-muted/60">·</span>
                <span>{t("progress.size", { size: formatSize(job.latest_log.total_size_mb) })}</span>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-3 rounded-lg bg-accent/5 border border-accent/10 px-3 py-2">
              <div className="h-2 w-2 rounded-full bg-accent animate-pulse shrink-0" />
              <span className="text-xs text-muted">{t("actions.running")}</span>
            </div>
          )}
        </div>
      )}

      {/* Run button */}
      <button
        onClick={() => handleRun(false)}
        disabled={isRunning || isPaused}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
      >
        <Play size={14} />
        {isRunning ? t("actions.running") : isPaused ? t("actions.paused") : t("actions.runNow")}
      </button>
    </div>
  );
}
