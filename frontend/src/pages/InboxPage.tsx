import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { StatusBadge } from "../components/StatusBadge";
import { fetchCaseQueue } from "../lib/api";
import type { CaseQueueResponse, QueueItem } from "../lib/types";

const tabs = [
  { id: "all", label: "全部" },
  { id: "waiting_review", label: "待审核" },
  { id: "needs_more_info", label: "待补证" },
  { id: "completed", label: "已完成" },
  { id: "rejected", label: "已驳回" },
] as const;

const anomalyTypeLabel: Record<string, string> = {
  amount_mismatch: "金额不一致",
  quantity_mismatch: "数量不一致",
  status_conflict: "状态冲突",
  field_missing: "关键字段缺失",
  cross_system_exception: "跨系统异常",
  stale_exception: "超时异常",
  normal: "正常对照",
};

const riskScore: Record<string, number> = {
  high: 3,
  medium: 2,
  low: 1,
};

const statusOrder: Record<string, number> = {
  waiting_review: 1,
  needs_more_info: 2,
  rejected: 3,
  completed: 4,
  created: 5,
  context_ready: 6,
  analyzing: 7,
  failed: 8,
};

function formatDate(value: string) {
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getSlaLabel(value: QueueItem["sla_status"]) {
  if (value === "overdue") return "已逾期";
  if (value === "due_soon") return "即将到期";
  if (value === "on_track") return "进行中";
  if (value === "closed") return "已关闭";
  return "未跟踪";
}

type SortField = "case_id" | "updated_at" | "case_type" | "risk_level" | "status" | "owner";
type SortDirection = "asc" | "desc";

function getStatusLabel(status: QueueItem["status"]) {
  if (status === "waiting_review") return "待审核";
  if (status === "needs_more_info") return "待补证";
  if (status === "completed") return "已完成";
  if (status === "rejected") return "已驳回";
  if (status === "created") return "新建";
  if (status === "context_ready") return "上下文就绪";
  if (status === "analyzing") return "分析中";
  return "失败";
}

export function InboxPage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]["id"]>("all");
  const [slaFilter, setSlaFilter] = useState<"all" | "overdue">("all");
  const [query, setQuery] = useState("");
  const [sortField, setSortField] = useState<SortField>("updated_at");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [data, setData] = useState<CaseQueueResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchCaseQueue(activeTab, slaFilter)
      .then((payload) => {
        setData(payload);
        setError("");
      })
      .catch((loadError) => {
        setError(loadError instanceof Error ? loadError.message : "加载队列失败。");
      });
  }, [activeTab, slaFilter]);

  const items = useMemo(() => {
    const source = data?.items ?? [];
    const filtered = source.filter((item) => {
      const queryLower = query.trim().toLowerCase();
      const queryMatch =
        queryLower.length === 0 ||
        item.case_id.toLowerCase().includes(queryLower) ||
        item.external_ref.toLowerCase().includes(queryLower) ||
        item.summary.toLowerCase().includes(queryLower) ||
        item.owner.toLowerCase().includes(queryLower);
      return queryMatch;
    });
    return [...filtered].sort((left, right) => {
      let comparison = 0;
      if (sortField === "updated_at") {
        comparison = new Date(left.updated_at).getTime() - new Date(right.updated_at).getTime();
      } else if (sortField === "risk_level") {
        comparison = riskScore[left.risk_level] - riskScore[right.risk_level];
      } else if (sortField === "status") {
        comparison = (statusOrder[left.status] ?? 99) - (statusOrder[right.status] ?? 99);
      } else if (sortField === "case_type") {
        comparison = (anomalyTypeLabel[left.case_type] ?? left.case_type).localeCompare(
          anomalyTypeLabel[right.case_type] ?? right.case_type,
          "zh-CN",
        );
      } else if (sortField === "owner") {
        comparison = left.owner.localeCompare(right.owner, "zh-CN");
      } else {
        comparison = left.case_id.localeCompare(right.case_id, "zh-CN");
      }

      if (comparison === 0) {
        comparison = new Date(left.updated_at).getTime() - new Date(right.updated_at).getTime();
      }

      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [data?.items, query, sortDirection, sortField]);

  function handleSort(field: SortField) {
    if (sortField === field) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortField(field);
    setSortDirection(field === "updated_at" || field === "risk_level" ? "desc" : "asc");
  }

  function getSortMarker(field: SortField) {
    if (sortField !== field) return "";
    return sortDirection === "asc" ? " ↑" : " ↓";
  }

  return (
    <div className="page-shell inbox-shell">
      <header className="workspace-header">
        <div className="workspace-title-block">
          <p className="panel-topline">运营异常处理台</p>
          <h1>异常工作台</h1>
          <p className="detail-subline">采购、履约、财务跨系统异常统一处理</p>
        </div>
        <div className="workspace-actions">
          <div className="workspace-search">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索案例编号、单号、摘要、负责人"
            />
          </div>
          <p className="workspace-hint">点击案例进入处理页，点击表头切换排序</p>
        </div>
      </header>

      {error ? <div className="inline-alert">{error}</div> : null}

      <section className="kpi-strip">
        <article className="kpi-card">
          <strong>{data?.metrics.all_open ?? 0}</strong>
          <span>待处理</span>
        </article>
        <article className="kpi-card">
          <strong>{data?.metrics.waiting_review ?? 0}</strong>
          <span>待审核</span>
        </article>
        <article className="kpi-card">
          <strong>{data?.metrics.needs_more_info ?? 0}</strong>
          <span>待补证</span>
        </article>
        <article className="kpi-card">
          <strong>{data?.metrics.overdue ?? 0}</strong>
          <span>已逾期</span>
        </article>
        <article className="kpi-card">
          <strong>{data?.metrics.high_risk ?? 0}</strong>
          <span>高风险</span>
        </article>
        <article className="kpi-card">
          <strong>{data?.metrics.completed ?? 0}</strong>
          <span>已完成</span>
        </article>
      </section>

      <section className="queue-panel">
        <div className="queue-toolbar">
          <div className="queue-filters">
            <div className="tab-strip">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  className={tab.id === activeTab ? "tab-button active" : "tab-button"}
                  onClick={() => setActiveTab(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="scope-strip">
              <button
                className={slaFilter === "all" ? "scope-button active" : "scope-button"}
                onClick={() => setSlaFilter("all")}
              >
                全部 SLA
              </button>
              <button
                className={slaFilter === "overdue" ? "scope-button active" : "scope-button"}
                onClick={() => setSlaFilter("overdue")}
              >
                仅看逾期
              </button>
            </div>
          </div>
          <div className="queue-meta">
            <span className="queue-count">共 {items.length} 条</span>
          </div>
        </div>

        <div className="table-shell">
          <table className="queue-table">
            <thead>
              <tr>
                <th>
                  <button className="table-sort-button" onClick={() => handleSort("case_id")}>
                    案例{getSortMarker("case_id")}
                  </button>
                </th>
                <th>
                  <button className="table-sort-button" onClick={() => handleSort("updated_at")}>
                    时间{getSortMarker("updated_at")}
                  </button>
                </th>
                <th>
                  <button className="table-sort-button" onClick={() => handleSort("case_type")}>
                    异常类型{getSortMarker("case_type")}
                  </button>
                </th>
                <th>
                  <button className="table-sort-button" onClick={() => handleSort("risk_level")}>
                    风险等级{getSortMarker("risk_level")}
                  </button>
                </th>
                <th>
                  <button className="table-sort-button" onClick={() => handleSort("status")}>
                    当前状态{getSortMarker("status")}
                  </button>
                </th>
                <th>
                  <button className="table-sort-button" onClick={() => handleSort("owner")}>
                    负责人{getSortMarker("owner")}
                  </button>
                </th>
                <th>摘要</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.case_id} className="queue-row" onClick={() => navigate(`/cases/${item.case_id}`)}>
                  <td className="cell-case">
                    <strong>{item.case_id}</strong>
                    <div className="case-meta-row">
                      <span>{item.external_ref}</span>
                      <em>查看详情</em>
                    </div>
                  </td>
                  <td className="cell-center">
                    <div className="time-cell">
                      <strong>{formatDate(item.updated_at)}</strong>
                      <span className={`sla-pill sla-${item.sla_status}`}>{getSlaLabel(item.sla_status)}</span>
                    </div>
                  </td>
                  <td>{anomalyTypeLabel[item.case_type] ?? item.case_type}</td>
                  <td className="cell-center">
                    <span className={`risk-pill risk-${item.risk_level}`}>
                      {item.risk_level === "high" ? "高" : item.risk_level === "medium" ? "中" : "低"}
                    </span>
                  </td>
                  <td className="cell-center">
                    <StatusBadge status={item.status} />
                  </td>
                  <td className="cell-center">{item.owner}</td>
                  <td className="summary-cell">{item.summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
