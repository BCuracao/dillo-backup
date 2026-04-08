"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { HardDrive, RefreshCw } from "lucide-react";
import DashboardLayout from "@/components/DashboardLayout";
import DriveCard from "@/components/DriveCard";
import { fetchDrives } from "@/lib/api";
import type { DriveInfo } from "@/lib/types";

export default function DrivesPage() {
  const t = useTranslations("drivesPage");
  const [drives, setDrives] = useState<DriveInfo[]>([]);
  const [loading, setLoading] = useState(true);

  const loadDrives = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchDrives();
      setDrives(res.drives);
    } catch {
      /* backend not available */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDrives();
  }, [loadDrives]);

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-6xl px-8 py-8">
        {/* Page Header */}
        <div className="mb-8 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent/10">
              <HardDrive size={20} className="text-accent" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-foreground">
                {t("title")}
              </h1>
              <p className="mt-0.5 text-sm text-muted">{t("subtitle")}</p>
            </div>
          </div>

          <button
            onClick={loadDrives}
            disabled={loading}
            className="flex items-center gap-2 rounded-lg border border-card-border px-4 py-2.5 text-sm text-muted transition-colors hover:border-accent/30 hover:text-foreground disabled:opacity-50"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            {loading ? t("refreshing") : t("refresh")}
          </button>
        </div>

        {/* Drive Grid */}
        {!loading && drives.length === 0 ? (
          <div className="flex h-48 flex-col items-center justify-center rounded-xl border border-dashed border-card-border">
            <HardDrive size={32} className="mb-3 text-muted/50" />
            <p className="text-sm text-muted">{t("noDrives")}</p>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-4">
            {drives.map((d) => (
              <DriveCard key={d.path} drive={d} />
            ))}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
