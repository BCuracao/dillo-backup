"use client";

import { useEffect, useState } from "react";
import { Clock } from "lucide-react";
import { useTranslations } from "next-intl";

type Frequency = "manual" | "hourly" | "daily" | "weekly" | "monthly";

interface SchedulePickerProps {
  value: string; // cron expression (or empty)
  onChange: (cron: string) => void;
}

const DAYS_OF_WEEK = [
  "sunday",
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
] as const;

/**
 * Parse a cron expression back into our structured format.
 * Supports the subset we generate: minute hour dom month dow
 */
function parseCron(cron: string): {
  frequency: Frequency;
  minute: number;
  hour: number;
  dayOfWeek: number;
  dayOfMonth: number;
} {
  const defaults = {
    frequency: "manual" as Frequency,
    minute: 0,
    hour: 2,
    dayOfWeek: 1,
    dayOfMonth: 1,
  };

  if (!cron || !cron.trim()) return defaults;

  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return defaults;

  const [minStr, hourStr, domStr, , dowStr] = parts;
  const minute = parseInt(minStr) || 0;
  const hour = parseInt(hourStr) || 0;

  // Hourly: "M * * * *"
  if (hourStr === "*" && domStr === "*" && dowStr === "*") {
    return { frequency: "hourly", minute, hour: 0, dayOfWeek: 1, dayOfMonth: 1 };
  }
  // Weekly: "M H * * D"
  if (domStr === "*" && dowStr !== "*") {
    return {
      frequency: "weekly",
      minute,
      hour,
      dayOfWeek: parseInt(dowStr) || 0,
      dayOfMonth: 1,
    };
  }
  // Monthly: "M H D * *"
  if (domStr !== "*" && dowStr === "*") {
    return {
      frequency: "monthly",
      minute,
      hour,
      dayOfWeek: 1,
      dayOfMonth: parseInt(domStr) || 1,
    };
  }
  // Daily: "M H * * *"
  if (domStr === "*" && dowStr === "*") {
    return { frequency: "daily", minute, hour, dayOfWeek: 1, dayOfMonth: 1 };
  }

  return defaults;
}

/**
 * Build a cron expression from the structured selections.
 */
function buildCron(
  frequency: Frequency,
  minute: number,
  hour: number,
  dayOfWeek: number,
  dayOfMonth: number
): string {
  switch (frequency) {
    case "manual":
      return "";
    case "hourly":
      return `${minute} * * * *`;
    case "daily":
      return `${minute} ${hour} * * *`;
    case "weekly":
      return `${minute} ${hour} * * ${dayOfWeek}`;
    case "monthly":
      return `${minute} ${hour} ${dayOfMonth} * *`;
    default:
      return "";
  }
}

const selectClass =
  "appearance-none rounded-lg border border-card-border bg-background px-3 py-2 text-sm text-foreground outline-none transition-colors focus:border-accent hover:border-accent/30";

export default function SchedulePicker({
  value,
  onChange,
}: SchedulePickerProps) {
  const t = useTranslations("schedulePicker");

  const parsed = parseCron(value);
  const [frequency, setFrequency] = useState<Frequency>(parsed.frequency);
  const [minute, setMinute] = useState(parsed.minute);
  const [hour, setHour] = useState(parsed.hour);
  const [dayOfWeek, setDayOfWeek] = useState(parsed.dayOfWeek);
  const [dayOfMonth, setDayOfMonth] = useState(parsed.dayOfMonth);

  // Sync internal state changes → parent via cron string
  useEffect(() => {
    const cron = buildCron(frequency, minute, hour, dayOfWeek, dayOfMonth);
    onChange(cron);
  }, [frequency, minute, hour, dayOfWeek, dayOfMonth]); // eslint-disable-line react-hooks/exhaustive-deps

  const frequencyOptions: { value: Frequency; label: string }[] = [
    { value: "manual", label: t("frequency.manual") },
    { value: "hourly", label: t("frequency.hourly") },
    { value: "daily", label: t("frequency.daily") },
    { value: "weekly", label: t("frequency.weekly") },
    { value: "monthly", label: t("frequency.monthly") },
  ];

  // Build hour options (00–23)
  const hourOptions = Array.from({ length: 24 }, (_, i) => i);
  // Build minute options (00, 05, 10, ..., 55)
  const minuteOptions = Array.from({ length: 12 }, (_, i) => i * 5);
  // Build day-of-month options (1–28)
  const dayOfMonthOptions = Array.from({ length: 28 }, (_, i) => i + 1);

  return (
    <div>
      <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-muted">
        <Clock size={12} />
        {t("label")}
        <span className="text-muted/50">{t("optional")}</span>
      </label>

      {/* Frequency selector */}
      <select
        value={frequency}
        onChange={(e) => setFrequency(e.target.value as Frequency)}
        className={`${selectClass} mb-3 w-full`}
      >
        {frequencyOptions.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      {/* Conditional detail selectors */}
      {frequency !== "manual" && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-card-border bg-card/50 px-3 py-3 text-sm text-foreground/80">
          {/* Hourly: at minute :XX */}
          {frequency === "hourly" && (
            <>
              <span className="text-xs text-muted">{t("atMinute")}</span>
              <select
                value={minute}
                onChange={(e) => setMinute(Number(e.target.value))}
                className={`${selectClass} w-20`}
              >
                {minuteOptions.map((m) => (
                  <option key={m} value={m}>
                    :{m.toString().padStart(2, "0")}
                  </option>
                ))}
              </select>
            </>
          )}

          {/* Daily: at HH:MM */}
          {frequency === "daily" && (
            <>
              <span className="text-xs text-muted">{t("atTime")}</span>
              <select
                value={hour}
                onChange={(e) => setHour(Number(e.target.value))}
                className={`${selectClass} w-20`}
              >
                {hourOptions.map((h) => (
                  <option key={h} value={h}>
                    {h.toString().padStart(2, "0")}
                  </option>
                ))}
              </select>
              <span className="text-muted">:</span>
              <select
                value={minute}
                onChange={(e) => setMinute(Number(e.target.value))}
                className={`${selectClass} w-20`}
              >
                {minuteOptions.map((m) => (
                  <option key={m} value={m}>
                    {m.toString().padStart(2, "0")}
                  </option>
                ))}
              </select>
            </>
          )}

          {/* Weekly: on DAY at HH:MM */}
          {frequency === "weekly" && (
            <>
              <span className="text-xs text-muted">{t("onDay")}</span>
              <select
                value={dayOfWeek}
                onChange={(e) => setDayOfWeek(Number(e.target.value))}
                className={`${selectClass} w-32`}
              >
                {DAYS_OF_WEEK.map((day, i) => (
                  <option key={day} value={i}>
                    {t(`days.${day}`)}
                  </option>
                ))}
              </select>
              <span className="text-xs text-muted">{t("atTime")}</span>
              <select
                value={hour}
                onChange={(e) => setHour(Number(e.target.value))}
                className={`${selectClass} w-20`}
              >
                {hourOptions.map((h) => (
                  <option key={h} value={h}>
                    {h.toString().padStart(2, "0")}
                  </option>
                ))}
              </select>
              <span className="text-muted">:</span>
              <select
                value={minute}
                onChange={(e) => setMinute(Number(e.target.value))}
                className={`${selectClass} w-20`}
              >
                {minuteOptions.map((m) => (
                  <option key={m} value={m}>
                    {m.toString().padStart(2, "0")}
                  </option>
                ))}
              </select>
            </>
          )}

          {/* Monthly: on day DD at HH:MM */}
          {frequency === "monthly" && (
            <>
              <span className="text-xs text-muted">{t("onDayOfMonth")}</span>
              <select
                value={dayOfMonth}
                onChange={(e) => setDayOfMonth(Number(e.target.value))}
                className={`${selectClass} w-20`}
              >
                {dayOfMonthOptions.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
              <span className="text-xs text-muted">{t("atTime")}</span>
              <select
                value={hour}
                onChange={(e) => setHour(Number(e.target.value))}
                className={`${selectClass} w-20`}
              >
                {hourOptions.map((h) => (
                  <option key={h} value={h}>
                    {h.toString().padStart(2, "0")}
                  </option>
                ))}
              </select>
              <span className="text-muted">:</span>
              <select
                value={minute}
                onChange={(e) => setMinute(Number(e.target.value))}
                className={`${selectClass} w-20`}
              >
                {minuteOptions.map((m) => (
                  <option key={m} value={m}>
                    {m.toString().padStart(2, "0")}
                  </option>
                ))}
              </select>
            </>
          )}
        </div>
      )}
    </div>
  );
}
