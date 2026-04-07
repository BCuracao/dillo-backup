"use client";

import { HardDrive } from "lucide-react";
import { useTranslations } from "next-intl";
import type { DriveInfo } from "@/lib/types";

interface DriveCardProps {
  drive: DriveInfo;
}

export default function DriveCard({ drive }: DriveCardProps) {
  const usedGb = drive.total_gb - drive.free_gb;
  const usedPercent = drive.total_gb > 0 ? (usedGb / drive.total_gb) * 100 : 0;
  const t = useTranslations("driveCard");

  const barColor =
    usedPercent > 90
      ? "bg-error"
      : usedPercent > 70
        ? "bg-warning"
        : "bg-accent";

  return (
    <div className="rounded-xl border border-card-border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <HardDrive size={16} className="text-muted" />
        <span className="text-sm font-medium text-foreground">
          {drive.label}
        </span>
        <span className="ml-auto text-xs text-muted">{drive.fs_type}</span>
      </div>

      {/* Usage bar */}
      <div className="mb-2 h-2 w-full overflow-hidden rounded-full bg-card-border">
        <div
          className={`h-full rounded-full ${barColor} transition-all`}
          style={{ width: `${usedPercent}%` }}
        />
      </div>

      <div className="flex justify-between text-[11px] text-muted">
        <span>
          {t("usedOf", {
            used: usedGb.toFixed(1),
            total: drive.total_gb.toFixed(1),
          })}
        </span>
        <span>{t("free", { free: drive.free_gb.toFixed(1) })}</span>
      </div>
    </div>
  );
}
