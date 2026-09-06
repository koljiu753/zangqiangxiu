import type { Metadata } from "next";
import Link from "next/link";
import { AdminPatternCard } from "@/components/admin-pattern-card";
import { ReviewWorkflowPanel } from "@/components/review-workflow-panel";
import { getAdminPattern, getReviewTasks } from "@/lib/admin-api";
import { csrfFor, requireAdmin } from "@/lib/admin-auth-server";
import type { AdminPattern, ReviewTask } from "@/types/domain";

export const metadata: Metadata = { title: "纹样审核详情" };
export const dynamic = "force-dynamic";
type Props = { params: Promise<{ id: string }> };

export default async function PatternReviewPage({ params }: Props) {
  const principal = await requireAdmin("reviewer");
  const csrfToken = await csrfFor(principal);
  const { id } = await params;
  let pattern: AdminPattern | undefined;
  let task: ReviewTask | undefined;
  let errorMessage = "";
  try {
    const [loadedPattern, tasks] = await Promise.all([getAdminPattern(id), getReviewTasks()]);
    pattern = loadedPattern; task = tasks.find((item) => item.patternId === id);
  } catch (error) { errorMessage = error instanceof Error ? error.message : "未知错误"; }
  if (!pattern) return <main className="inner-page admin-page"><nav className="admin-breadcrumb"><Link href="/admin/review">返回审核队列</Link></nav><div className="admin-error" role="alert"><h1>无法读取审核详情</h1><p>{errorMessage}</p></div></main>;
  return <main className="inner-page admin-page review-detail"><nav className="admin-breadcrumb"><Link href="/admin/review">返回审核队列</Link><span>/</span><strong>{pattern.name || pattern.id}</strong></nav><header className="page-hero"><p className="eyebrow">REVIEW DETAIL</p><h1>审核详情</h1><p>先登记来源与权利凭证，再分配任务并记录审核决定；清除全部阻塞原因后，发布员可以执行发布。</p></header><ReviewWorkflowPanel pattern={pattern} task={task} csrfToken={csrfToken}/><AdminPatternCard pattern={pattern} csrfToken={csrfToken} canPublish={principal.role === "publisher"} /></main>;
}
