import type { CaseStatus } from "../lib/types";

const labels: Record<CaseStatus, string> = {
  created: "已创建",
  context_ready: "上下文就绪",
  analyzing: "分析中",
  waiting_review: "待人工确认",
  completed: "已完成",
  rejected: "已驳回",
  needs_more_info: "待补充信息",
  failed: "失败",
};

export function StatusBadge({ status }: { status: CaseStatus }) {
  return <span className={`status-badge status-${status}`}>{labels[status] ?? status}</span>;
}

