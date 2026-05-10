"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  History,
  Info,
  Sliders,
  Zap,
} from "lucide-react";
import { fetchGlobalSettings } from "@/lib/api";
import type { GlobalSettings } from "@/lib/types";

const VERSIONING_MIN = 0;
const VERSIONING_MAX = 10;

interface JobAdvancedSectionProps {
  /** NULL means "inherit global". */
  jobAutoWake: boolean | null;
  jobVersioningLimit: number | null;
  onAutoWakeChange: (value: boolean | null) => void;
  onVersioningChange: (value: number | null) => void;
  /** Open state mirrors edit-mode UX where users pre-expand to see overrides. */
  defaultOpen?: boolean;
}

/**
 * Collapsible "Advanced" controls shared by Create and Edit modals.
 * Each setting is shown alongside an "Override Global …" checkbox; when
 * unchecked the per-job value is sent as ``null`` and the backend falls
 * back to the global default.
 */
export default function JobAdvancedSection({
  jobAutoWake,
  jobVersioningLimit,
  onAutoWakeChange,
  onVersioningChange,
  defaultOpen = false,
}: JobAdvancedSectionProps) {
  const t = useTranslations("jobAdvanced");
  const [open, setOpen] = useState(defaultOpen || jobAutoWake !== null || jobVersioningLimit !== null);
  const [globals, setGlobals] = useState<GlobalSettings | null>(null);

  useEffect(() => {
    fetchGlobalSettings()
      .then(setGlobals)
      .catch(() => {
        /* silently fall back to label-only display */
      });
  }, []);

  const overrideAutoWake = jobAutoWake !== null;
  const overrideVersioning = jobVersioningLimit !== null;

  const effectiveAutoWake = overrideAutoWake
    ? jobAutoWake
    : globals?.global_auto_wake ?? false;

  const effectiveVersioning = overrideVersioning
    ? jobVersioningLimit ?? 0
    : globals?.global_versioning_limit ?? 0;

  return (
    <div className="rounded-lg border border-card-border bg-background/40">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-xs font-medium text-muted transition-colors hover:text-foreground"
      >
        <span className="flex items-center gap-2">
          <Sliders size={14} />
          {t("title")}
        </span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {open && (
        <div className="space-y-4 border-t border-card-border px-3 py-3">
          {/* Auto-Wake override */}
          <div>
            <label className="flex items-start gap-2 text-xs text-foreground/90">
              <input
                type="checkbox"
                checked={overrideAutoWake}
                onChange={(e) =>
                  onAutoWakeChange(
                    e.target.checked
                      ? globals?.global_auto_wake ?? false
                      : null,
                  )
                }
                className="mt-0.5 h-3.5 w-3.5 accent-accent"
              />
              <span className="flex flex-col">
                <span className="flex items-center gap-1.5">
                  <Zap size={12} className="text-muted" />
                  {t("overrideAutoWake")}
                </span>
                <span className="mt-0.5 text-[11px] text-muted/80">
                  {t("autoWakeHelp")}
                </span>
              </span>
            </label>

            {overrideAutoWake && (
              <div className="ml-6 mt-2 flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => onAutoWakeChange(!effectiveAutoWake)}
                  className={`relative inline-flex h-6 w-10 items-center rounded-full transition-colors duration-200 focus:outline-none ${
                    effectiveAutoWake ? "bg-accent" : "bg-white/10"
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                      effectiveAutoWake ? "translate-x-5" : "translate-x-1"
                    }`}
                  />
                </button>
                <span className="text-[11px] text-muted">
                  {effectiveAutoWake ? t("autoWakeOn") : t("autoWakeOff")}
                </span>
              </div>
            )}

            {!overrideAutoWake && (
              <p className="ml-6 mt-1 text-[11px] text-muted/70">
                {t("inheritsGlobal", {
                  value: (globals?.global_auto_wake ?? false)
                    ? t("autoWakeOn")
                    : t("autoWakeOff"),
                })}
              </p>
            )}

            {/* Same-drive queue info — shown whenever Auto-Wake is effectively on. */}
            {effectiveAutoWake && (
              <div className="ml-6 mt-2 flex items-start gap-1.5 rounded bg-accent/10 px-2 py-1.5 text-[10px] text-accent/90">
                <Info size={10} className="mt-0.5 shrink-0" />
                <span>{t("sameDriveQueueInfo")}</span>
              </div>
            )}
          </div>

          {/* Versioning override */}
          <div>
            <label className="flex items-start gap-2 text-xs text-foreground/90">
              <input
                type="checkbox"
                checked={overrideVersioning}
                onChange={(e) =>
                  onVersioningChange(
                    e.target.checked
                      ? globals?.global_versioning_limit ?? 0
                      : null,
                  )
                }
                className="mt-0.5 h-3.5 w-3.5 accent-accent"
              />
              <span className="flex flex-col">
                <span className="flex items-center gap-1.5">
                  <History size={12} className="text-muted" />
                  {t("overrideVersioning")}
                </span>
                <span className="mt-0.5 text-[11px] text-muted/80">
                  {t("versioningHelp")}
                </span>
              </span>
            </label>

            {overrideVersioning && (
              <div className="ml-6 mt-2 space-y-2">
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={VERSIONING_MIN}
                    max={VERSIONING_MAX}
                    step={1}
                    value={effectiveVersioning}
                    onChange={(e) =>
                      onVersioningChange(parseInt(e.target.value, 10))
                    }
                    className="flex-1 accent-accent"
                  />
                  <span className="min-w-[3rem] rounded border border-card-border bg-background px-2 py-0.5 text-center text-[11px] font-mono text-foreground">
                    {effectiveVersioning === 0
                      ? t("versioningOff")
                      : effectiveVersioning}
                  </span>
                </div>
                <div className="flex items-start gap-1.5 rounded bg-warning/10 px-2 py-1.5 text-[10px] text-warning/90">
                  <AlertTriangle size={10} className="mt-0.5 shrink-0" />
                  <span>{t("storageWarning")}</span>
                </div>
              </div>
            )}

            {!overrideVersioning && (
              <p className="ml-6 mt-1 text-[11px] text-muted/70">
                {t("inheritsGlobal", {
                  value:
                    (globals?.global_versioning_limit ?? 0) === 0
                      ? t("versioningOff")
                      : `${globals?.global_versioning_limit}`,
                })}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
