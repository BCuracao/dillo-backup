import axios from "axios";
import type {
  ActivityLogListResponse,
  AutoStartStatus,
  BackupEstimate,
  BackupJob,
  BrowseResponse,
  CreateJobPayload,
  JobListResponse,
  JobLog,
  PathValidationResponse,
  RunJobPayload,
  SystemDrivesResponse,
} from "./types";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
});

// ── Jobs ─────────────────────────────────────────────────────────────

export async function fetchJobs(): Promise<JobListResponse> {
  const { data } = await api.get<JobListResponse>("/api/jobs");
  return data;
}

export async function fetchJob(id: string): Promise<BackupJob> {
  const { data } = await api.get<BackupJob>(`/api/jobs/${id}`);
  return data;
}

export async function createJob(payload: CreateJobPayload): Promise<BackupJob> {
  const { data } = await api.post<BackupJob>("/api/jobs", payload);
  return data;
}

export async function updateJob(
  id: string,
  payload: Partial<CreateJobPayload>
): Promise<BackupJob> {
  const { data } = await api.patch<BackupJob>(`/api/jobs/${id}`, payload);
  return data;
}

export async function deleteJob(id: string): Promise<void> {
  await api.delete(`/api/jobs/${id}`);
}

export async function runJob(
  id: string,
  payload?: RunJobPayload
): Promise<{ message: string }> {
  const { data } = await api.post<{ message: string }>(
    `/api/jobs/${id}/run`,
    payload ?? {}
  );
  return data;
}

export async function fetchJobLogs(
  id: string,
  limit = 20
): Promise<JobLog[]> {
  const { data } = await api.get<JobLog[]>(
    `/api/jobs/${id}/logs?limit=${limit}`
  );
  return data;
}

export async function estimateBackup(id: string): Promise<BackupEstimate> {
  const { data } = await api.get<BackupEstimate>(
    `/api/jobs/${id}/estimate`
  );
  return data;
}

// ── Activity Logs ────────────────────────────────────────────────────

export interface ActivityLogFilters {
  job_name?: string;
  event_type?: string;
  date_from?: string;
  date_to?: string;
}

export async function fetchActivityLogs(
  limit = 50,
  offset = 0,
  filters?: ActivityLogFilters
): Promise<ActivityLogListResponse> {
  const { data } = await api.get<ActivityLogListResponse>(
    "/api/activity-logs",
    { params: { limit, offset, ...filters } }
  );
  return data;
}

export async function fetchActivityJobNames(): Promise<string[]> {
  const { data } = await api.get<string[]>("/api/activity-logs/job-names");
  return data;
}

// ── System ───────────────────────────────────────────────────────────

export async function fetchDrives(): Promise<SystemDrivesResponse> {
  const { data } = await api.get<SystemDrivesResponse>("/api/system/drives");
  return data;
}

export async function browsePath(path: string = ""): Promise<BrowseResponse> {
  const { data } = await api.get<BrowseResponse>("/api/system/browse", {
    params: { path },
  });
  return data;
}

export async function validatePath(
  path: string,
  checkWritable = false
): Promise<PathValidationResponse> {
  const { data } = await api.post<PathValidationResponse>(
    "/api/system/validate-path",
    { path, check_writable: checkWritable }
  );
  return data;
}

// ── Auto-Start ──────────────────────────────────────────────────────

export async function fetchAutoStartStatus(): Promise<AutoStartStatus> {
  const { data } = await api.get<AutoStartStatus>("/api/system/autostart");
  return data;
}

export async function setAutoStart(enabled: boolean): Promise<AutoStartStatus> {
  const { data } = await api.put<AutoStartStatus>("/api/system/autostart", { enabled });
  return data;
}
