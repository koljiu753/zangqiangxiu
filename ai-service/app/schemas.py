from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class AnalysisTask(str, Enum):
    palette = "palette"
    embedding = "embedding"
    classification = "classification"
    similar = "similar"


class SearchScope(str, Enum):
    public = "public"
    internal = "internal"


class ReviewStatus(str, Enum):
    draft = "draft"
    approved = "approved"
    rejected = "rejected"


class Visibility(str, Enum):
    internal_only = "internal_only"
    public = "public"


class HealthResponse(BaseModel):
    status: str
    database: str


class AssetResponse(BaseModel):
    id: str
    sha256: str
    filename: str
    content_type: str
    width: int
    height: int
    byte_size: int
    created_at: datetime


class AnalysisCreate(BaseModel):
    asset_id: str
    tasks: list[AnalysisTask] = Field(default_factory=lambda: [AnalysisTask.palette], min_length=1)
    palette_colors: int = Field(default=5, ge=1, le=12)
    top_k: int = Field(default=5, ge=1, le=50)
    scope: SearchScope = SearchScope.public


class ReferenceCreate(BaseModel):
    asset_id: str
    label: str | None = Field(default=None, max_length=200)
    pattern_id: str | None = Field(default=None, max_length=200)
    review_status: ReviewStatus = ReviewStatus.draft
    visibility: Visibility = Visibility.internal_only


class ReferenceResponse(BaseModel):
    asset_id: str
    label: str | None
    pattern_id: str | None
    review_status: ReviewStatus
    visibility: Visibility
    algorithm_version: str
    feature_dimensions: int
    created_at: datetime
    content_url: str
    thumbnail_url: str


class ReferencePublicationUpdate(BaseModel):
    published: bool


class SimilarMatch(BaseModel):
    asset_id: str
    label: str | None
    pattern_id: str | None
    score: float = Field(ge=0, le=1)


class JobResponse(BaseModel):
    id: str
    kind: str
    status: JobStatus
    asset_id: str | None
    requested_tasks: list[str]
    progress: int = Field(ge=0, le=100)
    result_id: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class PaletteColor(BaseModel):
    hex: str
    rgb: tuple[int, int, int]
    ratio: float = Field(ge=0, le=1)


class ProviderOutput(BaseModel):
    status: str
    provider: str
    model_version: str | None = None
    data: Any | None = None
    reason: str | None = None


class AnalysisResultResponse(BaseModel):
    id: str
    job_id: str
    asset_id: str
    palette: list[PaletteColor] | None = None
    embedding: ProviderOutput | None = None
    classification: ProviderOutput | None = None
    similar: list[SimilarMatch] | None = None
    similarity_algorithm_version: str | None = None
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
