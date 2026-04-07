"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJobs } from "@/lib/api";
import type { BackupJob } from "@/lib/types";

const POLL_INTERVAL = 5_000; // 5 seconds

interface UseBackupJobsReturn {
  jobs: BackupJob[];
  total: number;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useBackupJobs(): UseBackupJobsReturn {
  const [jobs, setJobs] = useState<BackupJob[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchJobs();
      setJobs(data.jobs);
      setTotal(data.total);
      setError(null);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Failed to fetch jobs";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    intervalRef.current = setInterval(load, POLL_INTERVAL);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [load]);

  return { jobs, total, loading, error, refresh: load };
}
