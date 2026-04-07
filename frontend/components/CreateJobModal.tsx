"use client";

import { useState } from "react";
import { X, Plus, AlertTriangle } from "lucide-react";
import { useTranslations } from "next-intl";
import { createJob } from "@/lib/api";
import FolderPicker from "./FolderPicker";
import SchedulePicker from "./SchedulePicker";
import { useToast } from "./ToastProvider";

interface CreateJobModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => Promise<void>;
}

export default function CreateJobModal({
  open,
  onClose,
  onCreated,
}: CreateJobModalProps) {
  const [name, setName] = useState("");
  const [sourcePath, setSourcePath] = useState("");
  const [destPath, setDestPath] = useState("");
  const [cronExpr, setCronExpr] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const t = useTranslations("createJob");
  const tFolder = useTranslations("folderPicker");
  const tToast = useTranslations("toast");
  const { addToast } = useToast();

  if (!open) return null;

  const validate = (): string | null => {
    if (!name.trim()) return t("validation.nameRequired");
    if (!sourcePath.trim()) return t("validation.sourceRequired");
    if (!destPath.trim()) return t("validation.destRequired");
    if (sourcePath.trim() === destPath.trim()) {
      return t("validation.samePath");
    }
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setError(null);
    setSubmitting(true);

    try {
      await createJob({
        name: name.trim(),
        source_path: sourcePath.trim(),
        dest_path: destPath.trim(),
        schedule_cron: cronExpr.trim() || null,
      });
      addToast("success", tToast("jobCreated", { name: name.trim() }));
      setName("");
      setSourcePath("");
      setDestPath("");
      setCronExpr("");
      await onCreated();
      onClose();
    } catch (err: unknown) {
      if (
        err &&
        typeof err === "object" &&
        "response" in err &&
        err.response &&
        typeof err.response === "object" &&
        "data" in err.response
      ) {
        const resp = err.response as { data: { detail?: string } };
        setError(resp.data?.detail ?? t("errors.createFailed"));
      } else {
        setError(t("errors.backendDown"));
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-card-border bg-card p-6 shadow-2xl">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">
            {t("title")}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted transition-colors hover:bg-white/5 hover:text-foreground"
          >
            <X size={18} />
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 flex items-start gap-2 rounded-lg bg-error/10 px-4 py-3 text-sm text-error">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            {error}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Job Name */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted">
              {t("labels.jobName")}
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("placeholders.jobName")}
              className="w-full rounded-lg border border-card-border bg-background px-3 py-2.5 text-sm text-foreground placeholder-muted/50 outline-none transition-colors focus:border-accent"
            />
          </div>

          {/* Source Path — folder picker + manual override */}
          <FolderPicker
            label={t("labels.sourcePath")}
            value={sourcePath}
            onChange={setSourcePath}
            placeholder={t("placeholders.sourcePath")}
          />
          <div className="mt-1">
            <label className="mb-1 block text-xs text-muted">
              {tFolder("manualPathLabel")}
            </label>
            <input
              type="text"
              value={sourcePath}
              onChange={(e) => setSourcePath(e.target.value)}
              placeholder={tFolder("manualPathPlaceholder")}
              className="w-full rounded-lg border border-card-border bg-background px-3 py-2 text-sm font-mono text-foreground placeholder-muted/50 outline-none transition-colors focus:border-accent"
            />
            <p className="mt-1 text-[11px] text-muted/80">
              {tFolder("manualPathHint")}
            </p>
          </div>

          {/* Destination Path — folder picker + manual override */}
          <FolderPicker
            label={t("labels.destPath")}
            value={destPath}
            onChange={setDestPath}
            placeholder={t("placeholders.destPath")}
          />
          <div className="mt-1">
            <label className="mb-1 block text-xs text-muted">
              {tFolder("manualPathLabel")}
            </label>
            <input
              type="text"
              value={destPath}
              onChange={(e) => setDestPath(e.target.value)}
              placeholder={tFolder("manualPathPlaceholder")}
              className="w-full rounded-lg border border-card-border bg-background px-3 py-2 text-sm font-mono text-foreground placeholder-muted/50 outline-none transition-colors focus:border-accent"
            />
          </div>

          {/* Schedule — friendly picker */}
          <SchedulePicker value={cronExpr} onChange={setCronExpr} />

          {/* Submit */}
          <button
            type="submit"
            disabled={submitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent px-4 py-3 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus size={16} />
            {submitting ? t("submit.creating") : t("submit.create")}
          </button>
        </form>
      </div>
    </div>
  );
}
