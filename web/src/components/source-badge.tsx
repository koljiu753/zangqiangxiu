import type { DataSource } from "@/types/domain";

export function SourceBadge({ source }: { source: DataSource }) {
  if (source === "demo") return <div className="demo-banner" role="status"><strong>演示数据</strong><span>后端尚未连接，当前内容来自明确标记的本地样例。</span></div>;
  if (source === "preview") return <div className="demo-banner" role="status"><strong>内部预览</strong><span>当前显示尚未完成版权核验与发布审核的导入数据。</span></div>;
  return <div className="live-badge">实时数据</div>;
}
