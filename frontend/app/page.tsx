"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Plus,
  RefreshCw,
  HardDrive,
  FolderSync,
  CheckCircle,
  AlertCircle,
} from "lucide-react";
import { useTranslations } from "next-intl";
import ActivityFeed from "@/components/ActivityFeed";
import DashboardLayout from "@/components/DashboardLayout";
import JobCard from "@/components/JobCard";
import CreateJobModal from "@/components/CreateJobModal";
import EditJobModal from "@/components/EditJobModal";
import DriveCard from "@/components/DriveCard";
import { useBackupJobs } from "@/hooks/useBackupJobs";
import { fetchDrives } from "@/lib/api";
import type { BackupJob, DriveInfo } from "@/lib/types";

export default function DashboardPage() {
  const { jobs, total, loading, error, refresh } = useBackupJobs();
  const [showCreate, setShowCreate] = useState(false);
  const [editingJob, setEditingJob] = useState<BackupJob | null>(null);
  const [drives, setDrives] = useState<DriveInfo[]>([]);
  const [mutationSignal, setMutationSignal] = useState(0);
  const t = useTranslations("dashboard");

  /** Refresh jobs list AND notify ActivityFeed of the change. */
  const handleMutation = useCallback(async () => {
    await refresh();
    setMutationSignal((prev) => prev + 1);
  }, [refresh]);

  useEffect(() => {
    fetchDrives()
      .then((res) => setDrives(res.drives))
      .catch(() => {
        /* backend not available */
      });
  }, []);

  // Stats
  const activeJobs = jobs.filter((j) => j.is_active).length;
  const successJobs = jobs.filter(
    (j) => j.latest_log?.status === "SUCCESS"
  ).length;
  const errorJobs = jobs.filter(
    (j) => j.latest_log?.status === "ERROR"
  ).length;

  const stats = [
    {
      label: t("stats.totalJobs"),
      value: total,
      icon: <FolderSync size={18} />,
      color: "text-accent",
      bg: "bg-accent/10",
    },
    {
      label: t("stats.active"),
      value: activeJobs,
      icon: <HardDrive size={18} />,
      color: "text-foreground",
      bg: "bg-white/5",
    },
    {
      label: t("stats.succeeded"),
      value: successJobs,
      icon: <CheckCircle size={18} />,
      color: "text-success",
      bg: "bg-success/10",
    },
    {
      label: t("stats.failed"),
      value: errorJobs,
      icon: <AlertCircle size={18} />,
      color: "text-error",
      bg: "bg-error/10",
    },
  ];

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-6xl px-8 py-8">
        {/* Page Header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              {t("title")}
            </h1>
            <p className="mt-1 text-sm text-muted">
              {t("subtitle")}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleMutation}
              className="flex items-center gap-2 rounded-lg border border-card-border px-4 py-2.5 text-sm text-muted transition-colors hover:border-accent/30 hover:text-foreground"
            >
              <RefreshCw size={14} />
              {t("refresh")}
            </button>
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
            >
              <Plus size={14} />
              {t("newJob")}
            </button>
          </div>
        </div>

        {/* Stats Row */}
        <div className="mb-8 grid grid-cols-4 gap-4">
          {stats.map((s) => (
            <div
              key={s.label}
              className="rounded-xl border border-card-border bg-card p-4"
            >
              <div className="mb-2 flex items-center gap-2">
                <div
                  className={`flex h-8 w-8 items-center justify-center rounded-lg ${s.bg}`}
                >
                  <span className={s.color}>{s.icon}</span>
                </div>
              </div>
              <p className="text-2xl font-bold text-foreground">{s.value}</p>
              <p className="text-xs text-muted">{s.label}</p>
            </div>
          ))}
        </div>

        {/* Drives */}
        {drives.length > 0 && (
          <div className="mb-8">
            <h2 className="mb-4 text-sm font-semibold text-foreground">
              {t("availableDrives")}
            </h2>
            <div className="grid grid-cols-3 gap-4">
              {drives.map((d) => (
                <DriveCard key={d.path} drive={d} />
              ))}
            </div>
          </div>
        )}

        {/* Jobs Grid */}
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">
            {t("backupJobs")}
          </h2>
          <span className="text-xs text-muted">
            {t("autoRefresh")}
          </span>
        </div>

        {loading && jobs.length === 0 && (
          <div className="flex h-48 items-center justify-center rounded-xl border border-dashed border-card-border">
            <p className="text-sm text-muted">{t("loadingJobs")}</p>
          </div>
        )}

        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-error/10 px-4 py-3 text-sm text-error">
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        {!loading && jobs.length === 0 && !error && (
          <div className="flex h-48 flex-col items-center justify-center rounded-xl border border-dashed border-card-border">
            <FolderSync size={32} className="mb-3 text-muted/50" />
            <p className="text-sm text-muted">{t("noJobs")}</p>
            <button
              onClick={() => setShowCreate(true)}
              className="mt-3 flex items-center gap-2 text-sm font-medium text-accent transition-colors hover:text-accent-hover"
            >
              <Plus size={14} />
              {t("createFirstJob")}
            </button>
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          {jobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              onMutate={handleMutation}
              onEdit={setEditingJob}
            />
          ))}
        </div>

        {/* Activity Log */}
        <div className="mt-8">
          <ActivityFeed refreshSignal={mutationSignal} />
        </div>
      </div>

      {/* Modals */}
      <CreateJobModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={handleMutation}
      />
      <EditJobModal
        job={editingJob}
        onClose={() => setEditingJob(null)}
        onUpdated={handleMutation}
      />
    </DashboardLayout>
  );
}
