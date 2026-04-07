"use client";

import { CheckCircle, AlertCircle, Loader2, Clock, Pause } from "lucide-react";
import { useTranslations } from "next-intl";

type Status = "RUNNING" | "SUCCESS" | "ERROR" | "IDLE" | "PAUSED";

const config: Record<Status, { bg: string; text: string; icon: React.ReactNode }> = {
  RUNNING: {
    bg: "bg-accent/15",
    text: "text-accent",
    icon: <Loader2 size={12} className="animate-spin" />,
  },
  SUCCESS: {
    bg: "bg-success/15",
    text: "text-success",
    icon: <CheckCircle size={12} />,
  },
  ERROR: {
    bg: "bg-error/15",
    text: "text-error",
    icon: <AlertCircle size={12} />,
  },
  IDLE: {
    bg: "bg-muted/15",
    text: "text-muted",
    icon: <Clock size={12} />,
  },
  PAUSED: {
    bg: "bg-warning/15",
    text: "text-warning",
    icon: <Pause size={12} />,
  },
};

interface StatusBadgeProps {
  status: Status;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const { bg, text, icon } = config[status] ?? config.IDLE;
  const t = useTranslations("statusBadge");

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${bg} ${text}`}
    >
      {icon}
      {t(status)}
    </span>
  );
}
