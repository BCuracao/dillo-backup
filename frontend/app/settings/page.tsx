"use client";

import { useCallback, useEffect, useState, useTransition } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { Download, Globe, Monitor, Power, Settings } from "lucide-react";
import DashboardLayout from "@/components/DashboardLayout";
import { DOWNLOAD_MACOS_DMG_URL } from "@/lib/downloads";
import { fetchAutoStartStatus, setAutoStart } from "@/lib/api";
import type { AutoStartStatus } from "@/lib/types";

const locales = ["en", "de"] as const;

export default function SettingsPage() {
  const t = useTranslations("settingsPage");
  const tAuto = useTranslations("autoStart");
  const tLang = useTranslations("languageSwitcher");

  const locale = useLocale();
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  const [autoStart, setAutoStartState] = useState<AutoStartStatus | null>(
    null
  );
  const [autoStartLoading, setAutoStartLoading] = useState(true);
  const [autoStartToggling, setAutoStartToggling] = useState(false);
  const [autoStartError, setAutoStartError] = useState<string | null>(null);

  useEffect(() => {
    fetchAutoStartStatus()
      .then((status) => {
        setAutoStartState(status);
        setAutoStartLoading(false);
      })
      .catch(() => {
        setAutoStartLoading(false);
      });
  }, []);

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

          {/* ── Downloads Section ───────────────────────────────── */}
          <section className="rounded-xl border border-card-border bg-card">
            <div className="border-b border-card-border px-5 py-3">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">
                {t("downloads")}
              </h2>
            </div>

            <div className="px-5 py-4">
              <p className="mb-3 text-xs text-muted">{t("downloadsDescription")}</p>
              <a
                href={DOWNLOAD_MACOS_DMG_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-lg border border-card-border bg-background px-4 py-2.5 text-sm font-medium text-foreground transition-colors hover:border-accent/40 hover:bg-accent/5"
              >
                <Download size={16} className="text-accent" />
                {t("downloadMacOS")}
              </a>
              <p className="mt-2 text-xs text-muted">{t("downloadMacOSHint")}</p>
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
                  1.0.0
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
