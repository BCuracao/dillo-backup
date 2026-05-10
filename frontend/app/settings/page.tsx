"use client";

import { useCallback, useEffect, useState, useTransition } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Globe,
  History,
  Monitor,
  Power,
  Settings,
  Zap,
} from "lucide-react";
import DashboardLayout from "@/components/DashboardLayout";
import {
  fetchAutoStartStatus,
  fetchGlobalSettings,
  setAutoStart,
  updateGlobalSettings,
} from "@/lib/api";
import type { AutoStartStatus, GlobalSettings } from "@/lib/types";

const locales = ["en", "de"] as const;
const VERSIONING_MIN = 0;
const VERSIONING_MAX = 10;

export default function SettingsPage() {
  const t = useTranslations("settingsPage");
  const tAuto = useTranslations("autoStart");
  const tLang = useTranslations("languageSwitcher");
  const tDefaults = useTranslations("defaultBehavior");

  const locale = useLocale();
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  const [autoStart, setAutoStartState] = useState<AutoStartStatus | null>(
    null
  );
  const [autoStartLoading, setAutoStartLoading] = useState(true);
  const [autoStartToggling, setAutoStartToggling] = useState(false);
  const [autoStartError, setAutoStartError] = useState<string | null>(null);

  const [globals, setGlobals] = useState<GlobalSettings | null>(null);
  const [globalsLoading, setGlobalsLoading] = useState(true);
  const [globalsError, setGlobalsError] = useState<string | null>(null);
  const [savingGlobals, setSavingGlobals] = useState(false);

  useEffect(() => {
    fetchAutoStartStatus()
      .then((status) => {
        setAutoStartState(status);
        setAutoStartLoading(false);
      })
      .catch(() => {
        setAutoStartLoading(false);
      });

    fetchGlobalSettings()
      .then((g) => {
        setGlobals(g);
        setGlobalsLoading(false);
      })
      .catch(() => {
        setGlobalsError(tDefaults("loadError"));
        setGlobalsLoading(false);
      });
  }, [tDefaults]);

  const handleToggleAutoStart = useCallback(async () => {
    if (!autoStart || autoStartToggling) return;
    setAutoStartToggling(true);
    setAutoStartError(null);
    try {
      const updated = await setAutoStart(!autoStart.enabled);
      setAutoStartState(updated);
    } catch {
      setAutoStartError(t("autoStartError"));
    } finally {
      setAutoStartToggling(false);
    }
  }, [autoStart, autoStartToggling, t]);

  const persistGlobals = useCallback(
    async (patch: Partial<GlobalSettings>) => {
      if (!globals) return;
      const optimistic: GlobalSettings = { ...globals, ...patch };
      setGlobals(optimistic);
      setSavingGlobals(true);
      setGlobalsError(null);
      try {
        const updated = await updateGlobalSettings(patch);
        setGlobals(updated);
      } catch {
        // Roll back on failure.
        setGlobals(globals);
        setGlobalsError(tDefaults("saveError"));
      } finally {
        setSavingGlobals(false);
      }
    },
    [globals, tDefaults],
  );

  const switchLocale = (newLocale: string) => {
    document.cookie = `NEXT_LOCALE=${newLocale};path=/;max-age=31536000`;
    startTransition(() => {
      router.refresh();
    });
  };

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-3xl px-8 py-8">
        {/* Page Header */}
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent/10">
            <Settings size={20} className="text-accent" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              {t("title")}
            </h1>
            <p className="mt-0.5 text-sm text-muted">{t("subtitle")}</p>
          </div>
        </div>

        <div className="space-y-6">
          {/* ── General Section ─────────────────────────────────── */}
          <section className="rounded-xl border border-card-border bg-card">
            <div className="border-b border-card-border px-5 py-3">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">
                {t("general")}
              </h2>
            </div>

            {/* Language */}
            <div className="flex items-center justify-between px-5 py-4">
              <div className="flex items-center gap-3">
                <Globe size={18} className="text-muted" />
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {t("language")}
                  </p>
                  <p className="text-xs text-muted">
                    {t("languageDescription")}
                  </p>
                </div>
              </div>
              <select
                value={locale}
                onChange={(e) => switchLocale(e.target.value)}
                disabled={isPending}
                className="rounded-lg border border-card-border bg-background px-3 py-2 text-sm text-foreground outline-none transition-colors hover:border-accent/30 focus:border-accent disabled:opacity-50"
              >
                {locales.map((loc) => (
                  <option key={loc} value={loc}>
                    {tLang(loc)}
                  </option>
                ))}
              </select>
            </div>
          </section>

          {/* ── Startup Section ─────────────────────────────────── */}
          <section className="rounded-xl border border-card-border bg-card">
            <div className="border-b border-card-border px-5 py-3">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">
                {t("startup")}
              </h2>
            </div>

            <div className="flex items-center justify-between px-5 py-4">
              <div className="flex items-center gap-3">
                <Power size={18} className="text-muted" />
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {tAuto("label")}
                  </p>
                  <p className="text-xs text-muted">{tAuto("description")}</p>
                  {autoStartError && (
                    <p className="mt-1 text-xs text-error">{autoStartError}</p>
                  )}
                </div>
              </div>

              {autoStartLoading ? (
                <div className="h-7 w-12 animate-pulse rounded-full bg-white/5" />
              ) : autoStart ? (
                <button
                  onClick={handleToggleAutoStart}
                  disabled={autoStartToggling}
                  className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors duration-200 focus:outline-none disabled:opacity-50 ${
                    autoStart.enabled ? "bg-accent" : "bg-white/10"
                  }`}
                  title={
                    autoStart.enabled ? tAuto("enabled") : tAuto("disabled")
                  }
                >
                  <span
                    className={`inline-block h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                      autoStart.enabled ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </button>
              ) : (
                <span className="text-xs text-muted">
                  {t("autoStartNotAvailable")}
                </span>
              )}
            </div>
          </section>

          {/* ── Default Behavior (Auto-Wake & Time Capsule) ────── */}
          <section className="rounded-xl border border-card-border bg-card">
            <div className="border-b border-card-border px-5 py-3">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">
                {tDefaults("section")}
              </h2>
            </div>

            {/* Auto-Wake toggle */}
            <div className="flex items-start justify-between gap-4 px-5 py-4">
              <div className="flex items-start gap-3">
                <Zap size={18} className="mt-0.5 text-muted" />
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {tDefaults("autoWakeLabel")}
                  </p>
                  <p className="text-xs text-muted">
                    {tDefaults("autoWakeDescription")}
                  </p>
                </div>
              </div>

              {globalsLoading ? (
                <div className="h-7 w-12 animate-pulse rounded-full bg-white/5" />
              ) : globals ? (
                <button
                  onClick={() =>
                    persistGlobals({ global_auto_wake: !globals.global_auto_wake })
                  }
                  disabled={savingGlobals}
                  className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors duration-200 focus:outline-none disabled:opacity-50 ${
                    globals.global_auto_wake ? "bg-accent" : "bg-white/10"
                  }`}
                >
                  <span
                    className={`inline-block h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                      globals.global_auto_wake ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </button>
              ) : null}
            </div>

            {/* Versioning slider */}
            <div className="border-t border-card-border px-5 py-4">
              <div className="mb-3 flex items-start gap-3">
                <History size={18} className="mt-0.5 text-muted" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-foreground">
                    {tDefaults("versioningLabel")}
                  </p>
                  <p className="text-xs text-muted">
                    {tDefaults("versioningDescription")}
                  </p>
                </div>
                <span className="rounded-md border border-card-border bg-background px-2.5 py-1 text-xs font-mono text-foreground">
                  {globalsLoading || !globals
                    ? "—"
                    : globals.global_versioning_limit === 0
                      ? tDefaults("versioningOff")
                      : globals.global_versioning_limit}
                </span>
              </div>

              <input
                type="range"
                min={VERSIONING_MIN}
                max={VERSIONING_MAX}
                step={1}
                value={globals?.global_versioning_limit ?? 0}
                disabled={globalsLoading || !globals || savingGlobals}
                onChange={(e) =>
                  persistGlobals({
                    global_versioning_limit: parseInt(e.target.value, 10),
                  })
                }
                className="w-full accent-accent disabled:opacity-50"
                aria-label={tDefaults("versioningLabel")}
              />
              <div className="mt-1 flex justify-between text-[10px] uppercase tracking-wider text-muted/70">
                <span>{tDefaults("versioningOff")}</span>
                <span>{VERSIONING_MAX}</span>
              </div>

              <div className="mt-3 flex items-start gap-2 rounded-lg bg-warning/10 px-3 py-2 text-[11px] text-warning/90">
                <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                <span>{tDefaults("storageWarning")}</span>
              </div>

              {globalsError && (
                <p className="mt-2 text-xs text-error">{globalsError}</p>
              )}
            </div>
          </section>

          {/* ── About Section ──────────────────────────────────── */}
          <section className="rounded-xl border border-card-border bg-card">
            <div className="border-b border-card-border px-5 py-3">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">
                {t("about")}
              </h2>
            </div>

            <div className="divide-y divide-card-border">
              <div className="flex items-center justify-between px-5 py-3">
                <span className="text-sm text-muted">{t("version")}</span>
                <span className="text-sm font-mono text-foreground">
                  1.0.3
                </span>
              </div>
              {autoStart?.platform && (
                <div className="flex items-center justify-between px-5 py-3">
                  <div className="flex items-center gap-2">
                    <Monitor size={14} className="text-muted" />
                    <span className="text-sm text-muted">{t("platform")}</span>
                  </div>
                  <span className="text-sm font-mono text-foreground">
                    {autoStart.platform}
                  </span>
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </DashboardLayout>
  );
}
