export type Pattern = {
  id: string;
  name: string;
  category: string;
  ethnicity: "藏族" | "羌族" | "藏羌共融" | "unknown";
  meaning: string;
  colors: string[];
  imageUrl?: string;
  visibility?: "internal_only" | "public";
  source?: { system: string; legacyType?: string | null; legacyId?: string | null; originClaim: string; description?: string | null };
  rights?: { status: string; owner?: string | null; license?: string | null; evidence?: RightsEvidence[]; verifiedBy?: string | null; verifiedAt?: string | null; verificationNote?: string | null };
  review?: { issues: string[]; reviewedBy?: string | null; reviewedAt?: string | null; note?: string | null };
  status: "published" | "draft";
};

export type RightsEvidence = { id: string; filename: string; contentType?: string | null; sizeBytes?: number | null; storageKey?: string | null; url?: string | null; checksumSha256?: string | null; note?: string | null };
export type ReviewTask = { patternId: string; assignee: string; state: "assigned" | "approved" | "rejected" | "needs_more"; decisionNote?: string | null; assignedAt: string; decidedBy?: string | null; decidedAt?: string | null };

export type AdminPattern = Pattern & {
  status: "draft" | "published" | "archived";
  visibility: "internal_only" | "public";
  source: NonNullable<Pattern["source"]>;
  rights: NonNullable<Pattern["rights"]>;
  review: NonNullable<Pattern["review"]>;
  createdAt: string;
  updatedAt: string;
};

export type PatternAuditLog = {
  id: number;
  patternId: string;
  action: string;
  actor: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  createdAt: string;
};

export type PatternPage<T = Pattern> = { items: T[]; page: number; pageSize: number; total: number; pages: number };

export type AnalysisResult = {
  jobId: string;
  status: "succeeded";
  label?: string;
  confidence?: number;
  palette: string[];
  algorithmVersion?: string;
  similar: SimilarPattern[];
  warnings: string[];
};

export type SimilarPattern = {
  assetId: string;
  patternId?: string;
  label?: string;
  score: number;
  name?: string;
  category?: string;
  meaning?: string;
  imageUrl?: string;
};

export type DataSource = "api" | "preview" | "demo";

export type WithSource<T> = { data: T; source: DataSource };
