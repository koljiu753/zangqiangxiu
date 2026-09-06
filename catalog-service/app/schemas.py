from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


Ethnicity = Literal["藏族", "羌族", "藏羌共融", "unknown"]
Status = Literal["draft", "published", "archived"]
Visibility = Literal["internal_only", "public"]


class SourceInfo(BaseModel):
    system: str = "manual"
    legacyType: str | None = None
    legacyId: str | None = None
    originClaim: str = "unknown"
    description: str | None = Field(default=None, max_length=2000)


class RightsEvidence(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,99}$")
    filename: str = Field(min_length=1, max_length=255)
    contentType: str | None = Field(default=None, max_length=200)
    sizeBytes: int | None = Field(default=None, ge=0)
    storageKey: str | None = Field(default=None, max_length=1000)
    url: str | None = Field(default=None, max_length=2000)
    checksumSha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    note: str | None = Field(default=None, max_length=1000)


class RightsInfo(BaseModel):
    status: str = "unverified"
    owner: str | None = None
    license: str | None = None
    evidence: list[RightsEvidence] = Field(default_factory=list, max_length=100)
    verifiedBy: str | None = Field(default=None, max_length=200)
    verifiedAt: str | None = Field(default=None, max_length=100)
    verificationNote: str | None = Field(default=None, max_length=2000)


class ReviewInfo(BaseModel):
    issues: list[str] = Field(default_factory=list)
    reviewedBy: str | None = None
    reviewedAt: str | None = None
    note: str | None = Field(default=None, max_length=2000)


class EvidenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sourceDescription: str | None = Field(default=None, max_length=2000)
    originClaim: str | None = Field(default=None, max_length=2000)
    rightsStatus: str | None = Field(default=None, min_length=1, max_length=100)
    rightsOwner: str | None = Field(default=None, max_length=500)
    rightsLicense: str | None = Field(default=None, max_length=500)
    evidence: list[RightsEvidence] | None = Field(default=None, max_length=100)
    verifiedBy: str | None = Field(default=None, max_length=200)
    verifiedAt: str | None = Field(default=None, max_length=100)
    verificationNote: str | None = Field(default=None, max_length=2000)
    reviewNote: str | None = Field(default=None, max_length=2000)


class PatternBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(default="", max_length=100)
    ethnicity: Ethnicity = "unknown"
    meaning: str = ""
    colors: list[str] = Field(default_factory=list)
    imageUrl: str | None = None
    source: SourceInfo = Field(default_factory=SourceInfo)
    rights: RightsInfo = Field(default_factory=RightsInfo)
    review: ReviewInfo = Field(default_factory=ReviewInfo)


class PatternCreate(PatternBase):
    id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,99}$")
    status: Status = "draft"
    visibility: Visibility = "internal_only"


class PatternUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    ethnicity: Ethnicity | None = None
    meaning: str | None = None
    colors: list[str] | None = None
    imageUrl: str | None = None
    source: SourceInfo | None = None
    rights: RightsInfo | None = None
    review: ReviewInfo | None = None
    status: Status | None = None
    visibility: Visibility | None = None


class Pattern(PatternBase):
    id: str
    status: Status
    visibility: Visibility
    createdAt: str
    updatedAt: str


class PatternPage(BaseModel):
    items: list[Pattern]
    page: int
    pageSize: int
    total: int
    pages: int


class AuditLog(BaseModel):
    id: int
    patternId: str
    action: str
    actor: str
    before: dict | None
    after: dict | None
    createdAt: str


class BatchReviewItem(BaseModel):
    patternId: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,99}$")
    reviewedBy: str = Field(min_length=1, max_length=200)
    reviewedAt: str = Field(min_length=1, max_length=100)
    issues: list[str] = Field(default_factory=list, max_length=100)


class BatchReviewRequest(BaseModel):
    items: list[BatchReviewItem] = Field(min_length=1, max_length=100)


class BatchPublishRequest(BaseModel):
    patternIds: list[str] = Field(min_length=1, max_length=100)


class BatchOperationItem(BaseModel):
    patternId: str
    status: Literal["succeeded", "failed"]
    code: str | None = None
    message: str | None = None
    pattern: Pattern | None = None


class BatchOperationResponse(BaseModel):
    succeeded: int
    failed: int
    items: list[BatchOperationItem]


class CategoryCount(BaseModel):
    category: str
    count: int


class ReviewRiskStats(BaseModel):
    hasIssues: int
    rightsUnverified: int


class CatalogStats(BaseModel):
    total: int
    statuses: dict[str, int]
    rightsStatuses: dict[str, int]
    reviewRisk: ReviewRiskStats
    ready: int
    categories: list[CategoryCount]


ReviewDecision = Literal["approved", "rejected", "needs_more"]
ReviewTaskState = Literal["assigned", "approved", "rejected", "needs_more"]


class ReviewAssignmentItem(BaseModel):
    patternId: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,99}$")
    assignee: str = Field(min_length=1, max_length=200)
    requestId: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{7,99}$")


class BatchReviewAssignmentRequest(BaseModel):
    items: list[ReviewAssignmentItem] = Field(min_length=1, max_length=100)


class ReviewDecisionItem(BaseModel):
    patternId: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,99}$")
    decision: ReviewDecision
    decidedBy: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    issues: list[str] = Field(default_factory=list, max_length=100)
    requestId: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{7,99}$")


class BatchReviewDecisionRequest(BaseModel):
    items: list[ReviewDecisionItem] = Field(min_length=1, max_length=100)


class ReviewTask(BaseModel):
    patternId: str
    assignee: str
    state: ReviewTaskState
    decisionNote: str | None = None
    assignedAt: str
    decidedBy: str | None = None
    decidedAt: str | None = None


class ReviewWorkflowItem(BaseModel):
    patternId: str
    status: Literal["succeeded", "failed"]
    code: str | None = None
    message: str | None = None
    replayed: bool = False
    task: ReviewTask | None = None


class ReviewWorkflowResponse(BaseModel):
    succeeded: int
    failed: int
    items: list[ReviewWorkflowItem]
