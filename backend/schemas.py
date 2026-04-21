"""Pydantic v2 schemas for API request/response validation."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── BackupJob Schemas ─────────────────────────────────────────────────

class JobCreate(BaseModel):
    """Schema for creating a new backup job."""

    name: str = Field(..., min_length=1, max_length=255, examples=["Daily Photos Backup"])
    source_path: str = Field(..., min_length=1, examples=["D:\\Photos"])
    dest_path: str = Field(..., min_length=1, examples=["E:\\Backups\\Photos"])
    schedule_cron: Optional[str] = Field(
        default=None,
        examples=["0 2 * * *"],
        description="Cron expression for scheduling (optional).",
    )
    is_active: bool = True

    @field_validator("source_path", "dest_path")
    @classmethod
    def strip_trailing_whitespace(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def source_must_differ_from_dest(self) -> "JobCreate":
        if self.source_path == self.dest_path:
            raise ValueError("Source and destination paths must be different to prevent recursion loops.")
        return self


class JobUpdate(BaseModel):
    """Schema for partially updating a backup job."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    source_path: Optional[str] = None
    dest_path: Optional[str] = None
    schedule_cron: Optional[str] = None
    is_active: Optional[bool] = None


class JobLogResponse(BaseModel):
    """Schema for a single execution log entry."""

    id: int
    job_id: uuid.UUID
    start_time: datetime
    end_time: Optional[datetime] = None
    status: str
    files_processed: int
    files_skipped: int
    total_size_mb: float
    error_message: Optional[str] = None
    is_dry_run: bool

    model_config = {"from_attributes": True}


class JobResponse(BaseModel):
    """Schema for returning a backup job with its latest log."""

    id: uuid.UUID
    name: str
    source_path: str
    dest_path: str
    schedule_cron: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    latest_log: Optional[JobLogResponse] = None

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    """Wrapper for paginated job lists."""

    jobs: list[JobResponse]
    total: int


# ── Run Trigger ───────────────────────────────────────────────────────

class RunJobRequest(BaseModel):
    """Optional parameters when triggering a manual run."""

    dry_run: bool = Field(
        default=False,
        description="If true, log what would be copied without actually writing.",
    )
    force_system_drive: bool = Field(
        default=False,
        description="Override the Safety Lock that blocks the OS drive as destination.",
    )
    verify_after_copy: bool = Field(
        default=False,
        description="Run SHA-256 verification after each file copy to ensure integrity.",
    )


# ── System ────────────────────────────────────────────────────────────

class DriveInfo(BaseModel):
    """Information about an available drive/volume."""

    path: str
    label: str
    total_gb: float
    free_gb: float
    fs_type: str


class SystemDrivesResponse(BaseModel):
    drives: list[DriveInfo]


# ── Activity Logs ─────────────────────────────────────────────────────

class ActivityLogResponse(BaseModel):
    """Schema for a single activity log entry."""

    id: int
    event_type: str
    job_name: str
    job_id: Optional[uuid.UUID] = None
    message: str
    details: Optional[str] = None
    timestamp: datetime

    model_config = {"from_attributes": True}


class ActivityLogListResponse(BaseModel):
    """Wrapper for activity log lists."""

    logs: list[ActivityLogResponse]
    total: int


# ── Backup Estimation ─────────────────────────────────────────────────

class BackupEstimate(BaseModel):
    """Estimated size and file count for a backup job before running."""

    total_files: int = Field(description="Number of files that would be copied")
    skipped_files: int = Field(description="Number of files already up-to-date")
    estimated_size_mb: float = Field(description="Total size of files to copy (MB)")
    estimated_time_seconds: float = Field(
        description="Rough time estimate based on ~50 MB/s throughput"
    )
    scan_duration_seconds: float = Field(description="How long the scan itself took")


# ── Directory Browsing ────────────────────────────────────────────────

class DirectoryEntry(BaseModel):
    """A single directory entry returned by the browse endpoint."""

    name: str
    path: str
    is_drive: bool = False


class BrowseResponse(BaseModel):
    """Response from the directory browse endpoint."""

    current_path: str
    parent_path: Optional[str] = None
    directories: list[DirectoryEntry]


# ── Path Validation ──────────────────────────────────────────────────

class AutoStartStatusResponse(BaseModel):
    """Current state of the auto-start setting."""

    enabled: bool = Field(description="True if Dillo Backup is set to start on boot.")
    platform: str = Field(description="Operating system identifier.")


class AutoStartRequest(BaseModel):
    """Request body to enable or disable auto-start."""

    enabled: bool = Field(description="True to enable, False to disable auto-start on boot.")


class PathValidationRequest(BaseModel):
    """Request body for the path validation endpoint."""

    path: str = Field(..., min_length=1, description="Absolute path to validate.")
    check_writable: bool = Field(
        default=False,
        description="Also verify write access via a canary file test.",
    )


class PathValidationResponse(BaseModel):
    """Detailed result of a multi-strategy directory access check."""

    path: str = Field(description="The normalised path that was tested.")
    accessible: bool = Field(description="True if the directory could be reached by any strategy.")
    writable: bool = Field(description="True if a canary file was successfully created and deleted.")
    method: str = Field(description="Which validation strategy confirmed access (standard, scandir, stat, canary_file, none).")
    error: Optional[str] = Field(
        default=None,
        description="Machine-readable error key when the path is not fully accessible.",
    )
