"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Folder,
  FolderOpen,
  HardDrive,
  ChevronRight,
  ArrowUp,
  Check,
  X,
  Loader2,
  ShieldCheck,
  AlertTriangle,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { browsePath, validatePath } from "@/lib/api";
import type { DirectoryEntry } from "@/lib/types";

interface FolderPickerProps {
  label: string;
  value: string;
  onChange: (path: string) => void;
  placeholder?: string;
}

export default function FolderPicker({
  label,
  value,
  onChange,
  placeholder,
}: FolderPickerProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [currentPath, setCurrentPath] = useState("");
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [directories, setDirectories] = useState<DirectoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);
  const [validationOk, setValidationOk] = useState<boolean | null>(null);
  const t = useTranslations("folderPicker");

  const loadDirectory = useCallback(async (path: string) => {
    setLoading(true);
    setError(null);
    setValidationOk(null);
    try {
      const res = await browsePath(path);
      setCurrentPath(res.current_path);
      setParentPath(res.parent_path);
      setDirectories(res.directories);

      // If the browse returned zero directories for a drive root, trigger
      // a canary validation so the user knows if the drive is reachable.
      if (path && res.directories.length === 0) {
        try {
          const validation = await validatePath(path, true);
          if (validation.accessible) {
            setValidationOk(true);
          }
        } catch {
          // non-critical
        }
      }
    } catch {
      setError(t("loadError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (open) {
      // If a value is already set, browse that path's parent or the path itself
      loadDirectory(value || "");
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleOpen = () => {
    setOpen(true);
  };

  const handleNavigate = (path: string) => {
    loadDirectory(path);
  };

  const handleGoUp = () => {
    if (parentPath !== null) {
      loadDirectory(parentPath);
    } else {
      // Go to drives root
      loadDirectory("");
    }
  };

  const handleSelect = () => {
    if (currentPath) {
      onChange(currentPath);
    }
    setOpen(false);
  };

  const handleClose = () => {
    setOpen(false);
  };

  // Build breadcrumb segments from current path
  const breadcrumbs = currentPath
    ? currentPath.split(/[\\/]/).filter(Boolean)
    : [];

  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium text-muted">
        {label}
      </label>

      {/* Path display + browse button */}
      <div className="flex gap-2">
        <div className="flex min-w-0 flex-1 items-center rounded-lg border border-card-border bg-background px-3 py-2.5">
          {value ? (
            <span className="truncate text-sm font-mono text-foreground">
              {value}
            </span>
          ) : (
            <span className="truncate text-sm text-muted/50">
              {placeholder}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={handleOpen}
          className="flex shrink-0 items-center gap-2 rounded-lg border border-card-border px-3 py-2.5 text-sm text-muted transition-colors hover:border-accent/30 hover:text-foreground"
        >
          <FolderOpen size={14} />
          {t("browse")}
        </button>
      </div>

      {/* Inline browser panel */}
      {open && (
        <div className="mt-2 overflow-hidden rounded-xl border border-card-border bg-background">
          {/* Browser header: breadcrumb + actions */}
          <div className="flex items-center justify-between border-b border-card-border px-3 py-2">
            <div className="flex min-w-0 items-center gap-1 text-xs">
              {/* Up button */}
              <button
                type="button"
                onClick={handleGoUp}
                disabled={!currentPath}
                className="mr-1 rounded p-1 text-muted transition-colors hover:bg-white/5 hover:text-foreground disabled:opacity-30"
                title={t("goUp")}
              >
                <ArrowUp size={14} />
              </button>

              {/* Breadcrumb */}
              {currentPath === "" ? (
                <span className="text-muted">{t("drives")}</span>
              ) : (
                <div className="flex min-w-0 items-center gap-0.5 overflow-hidden">
                  <button
                    type="button"
                    onClick={() => loadDirectory("")}
                    className="shrink-0 text-accent transition-colors hover:text-accent-hover"
                  >
                    <HardDrive size={12} />
                  </button>
                  {breadcrumbs.map((segment, i) => {
                    // Build path up to this segment
                    const segmentPath = breadcrumbs
                      .slice(0, i + 1)
                      .join("\\");
                    // On Windows add the backslash back to drive letter
                    const fullPath =
                      segmentPath.length === 2 && segmentPath[1] === ":"
                        ? segmentPath + "\\"
                        : segmentPath;
                    const isLast = i === breadcrumbs.length - 1;
                    return (
                      <span key={i} className="flex shrink-0 items-center gap-0.5">
                        <ChevronRight size={10} className="text-muted/50" />
                        {isLast ? (
                          <span className="font-medium text-foreground">
                            {segment}
                          </span>
                        ) : (
                          <button
                            type="button"
                            onClick={() => loadDirectory(fullPath)}
                            className="text-accent transition-colors hover:text-accent-hover"
                          >
                            {segment}
                          </button>
                        )}
                      </span>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Close browser */}
            <button
              type="button"
              onClick={handleClose}
              className="ml-2 rounded p-1 text-muted transition-colors hover:bg-white/5 hover:text-foreground"
            >
              <X size={14} />
            </button>
          </div>

          {/* Directory listing */}
          <div className="max-h-48 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 size={18} className="animate-spin text-muted" />
              </div>
            ) : error ? (
              <div className="px-3 py-4 text-center text-xs text-error">
                {error}
              </div>
            ) : directories.length === 0 ? (
              <div className="px-3 py-4 text-center text-xs">
                {validationOk ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-center gap-1.5 text-success">
                      <ShieldCheck size={14} />
                      <span>{t("validatedAccessible")}</span>
                    </div>
                    <p className="text-muted/80">{t("emptyButAccessible")}</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <span className="text-muted">{t("empty")}</span>
                    {currentPath && (
                      <button
                        type="button"
                        onClick={async () => {
                          setValidating(true);
                          try {
                            const res = await validatePath(currentPath, true);
                            setValidationOk(res.accessible);
                          } catch {
                            setValidationOk(false);
                          } finally {
                            setValidating(false);
                          }
                        }}
                        disabled={validating}
                        className="mx-auto flex items-center gap-1.5 rounded-md border border-card-border px-2.5 py-1.5 text-xs text-accent transition-colors hover:bg-white/5 disabled:opacity-50"
                      >
                        {validating ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <ShieldCheck size={12} />
                        )}
                        {t("verifyAccess")}
                      </button>
                    )}
                    {validationOk === false && (
                      <div className="flex items-center justify-center gap-1.5 text-error">
                        <AlertTriangle size={12} />
                        <span>{t("notAccessible")}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="py-1">
                {directories.map((dir) => (
                  <button
                    key={dir.path}
                    type="button"
                    onClick={() => handleNavigate(dir.path)}
                    className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm transition-colors hover:bg-white/5"
                  >
                    {dir.is_drive ? (
                      <HardDrive size={14} className="shrink-0 text-accent" />
                    ) : (
                      <Folder size={14} className="shrink-0 text-warning" />
                    )}
                    <span className="truncate text-foreground/90">
                      {dir.name}
                    </span>
                    <ChevronRight
                      size={12}
                      className="ml-auto shrink-0 text-muted/40"
                    />
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Select button */}
          {currentPath && (
            <div className="border-t border-card-border px-3 py-2">
              <button
                type="button"
                onClick={handleSelect}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-accent-hover"
              >
                <Check size={12} />
                {t("selectFolder", { path: currentPath })}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
