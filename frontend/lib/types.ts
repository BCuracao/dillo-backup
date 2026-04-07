// ── Backend-aligned TypeScript types ──────────────────────────────────

export interface JobLog {
  id: number;
  job_id: string;
  start_time: string;
  end_time: string | null;
  status: "RUNNING" | "SUCCESS" | "ERROR";
  files_processed: number;
  files_skipped: number;
  total_size_mb: number;
  error_message: string | null;
  is_dry_run: boolean;
}

export interface BackupJob {
  id: string;
  name: string;
  source_path: string;
  dest_path: string;
  schedule_cron: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  latest_log: JobLog | null;
}

export interface JobListResponse {
  jobs: BackupJob[];
  total: number;
}

export interface CreateJobPayload {
  name: string;
  source_path: string;
  dest_path: string;
  schedule_cron?: string | null;
  is_active?: boolean;
}

export interface RunJobPayload {
  dry_run?: boolean;
  force_system_drive?: boolean;
  verify_after_copy?: boolean;
}

// ── Activity Logs ─────────────────────────────────────────────────────

export interface ActivityLog {
  id: number;
  event_type:
    | "JOB_CREATED"
    | "JOB_DELETED"
    | "JOB_RUN"
    | "JOB_DRY_RUN"
    | "JOB_COMPLETED"
    | "JOB_FAILED";
  job_name: string;
  job_id: string | null;
  message: string;
  details: string | null;
  timestamp: string;
}

export interface ActivityLogListResponse {
  logs: ActivityLog[];
  total: number;
}

// ── Backup Estimation ─────────────────────────────────────────────────

export interface BackupEstimate {
  total_files: number;
  skipped_files: number;
  estimated_size_mb: number;
  estimated_time_seconds: number;
  scan_duration_seconds: number;
}

// ── Drives ────────────────────────────────────────────────────────────

export interface DriveInfo {
  path: string;
  label: string;
  total_gb: number;
  free_gb: number;
  fs_type: string;
}

export interface SystemDrivesResponse {
  drives: DriveInfo[];
}

export interface DirectoryEntry {
  name: string;
  path: string;
  is_drive: boolean;
}

export interface BrowseResponse {
  current_path: string;
  parent_path: string | null;
  directories: DirectoryEntry[];
}

// ── Path Validation ───────────────────────────────────────────────────

export interface PathValidationResponse {
  path: string;
  accessible: boolean;
  writable: boolean;
  method: string;
  error: string | null;
}

// ── Auto-Start ───────────────────────────────────────────────────────

export interface AutoStartStatus {
  enabled: boolean;
  platform: string;
}
