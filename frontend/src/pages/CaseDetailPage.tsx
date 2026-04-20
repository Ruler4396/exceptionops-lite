import { useEffect, useEffectEvent, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { Timeline } from "../components/Timeline";
import { analyzeCase, fetchCaseDetail, submitReview } from "../lib/api";
import type { CaseDetail } from "../lib/types";

const anomalyTypeLabel: Record<string, string> = {
  amount_mismatch: "金额不一致",
  quantity_mismatch: "数量不一致",
  status_conflict: "状态冲突",
  field_missing: "关键字段缺失",
  cross_system_exception: "跨系统异常",
  stale_exception: "超时异常",
  normal: "正常对照",
};

const riskFlagLabel: Record<string, string> = {
  amount_adjustment: "涉及金额调整",
  insufficient_evidence: "证据不足",
  missing_critical_field: "关键字段缺失",
  multiple_possible_causes: "存在多种可能原因",
  stale_exception: "异常长期未更新",
  status_change: "涉及状态变更",
};

function formatDate(value: string) {
  return new Date(value).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function riskText(value: "low" | "medium" | "high" | undefined) {
  if (value === "high") return "高";
  if (value === "medium") return "中";
  if (value === "low") return "低";
  return "未知";
}

function getComparisonRows(records: Record<string, unknown> | null) {
  const purchaseOrder = (records?.purchase_order as Record<string, unknown> | undefined) ?? {};
  const receipt = (records?.goods_receipt as Record<string, unknown> | undefined) ?? {};
  const invoice = (records?.invoice as Record<string, unknown> | undefined) ?? {};
  const statusItems = (records?.shipment_or_status_log as Array<Record<string, unknown>> | undefined) ?? [];
  const statusLog = statusItems[statusItems.length - 1] ?? {};

  const rows = [
    {
      label: "数量",
      po: purchaseOrder.ordered_qty,
      receipt: receipt.received_qty,
      invoice: invoice.billed_qty,
    },
    {
      label: "金额",
      po: purchaseOrder.total_amount,
      receipt: "-",
      invoice: invoice.total_amount,
    },
    {
      label: "状态",
      po: purchaseOrder.status,
      receipt: receipt.status,
      invoice: invoice.status,
    },
    {
      label: "关键字段",
      po: purchaseOrder.po_number,
      receipt: receipt.receiver_id || "缺失",
      invoice: invoice.invoice_number || "缺失",
    },
    {
      label: "物流",
      po: "-",
      receipt: "-",
      invoice: statusLog.status ?? "-",
    },
  ];

  return rows.map((row) => {
    const values = [row.po, row.receipt, row.invoice].filter((item) => item !== "-" && item !== undefined && item !== null);
    const normalized = values.map((item) => String(item));
    const isConflict =
      normalized.length > 1 && new Set(normalized).size > 1
        ? "冲突"
        : normalized.includes("缺失")
          ? "缺失"
          : "一致";
    return { ...row, result: isConflict };
  });
}

function getEvidenceNotes(detail: CaseDetail) {
  const records = detail.records_snapshot ?? {};
  const statusItems = (records.shipment_or_status_log as Array<Record<string, unknown>> | undefined) ?? [];
  const statusLog = statusItems[statusItems.length - 1] ?? {};
  return [
    `采购单：${(records.purchase_order as Record<string, unknown> | undefined)?.po_number ?? "-"}`,
    `收货单：${(records.goods_receipt as Record<string, unknown> | undefined)?.gr_number ?? "-"}`,
    `发票: ${(records.invoice as Record<string, unknown> | undefined)?.invoice_number || "缺失"}`,
    `最新物流: ${String(statusLog.status ?? "-")}`,
  ];
}

export function CaseDetailPage() {
  const { caseId = "" } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");
  const [reviewer, setReviewer] = useState("ops.lead@example.com");
  const [decision, setDecision] = useState("approve");
  const [comment, setComment] = useState("建议按 SOP 执行人工闭环，并保留当前限制。");

  const loadCase = useEffectEvent(async (silent = false) => {
    if (!silent) {
      setLoading(true);
    }
    try {
      const payload = await fetchCaseDetail(caseId);
      setDetail(payload);
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载案例失败。");
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  });

  useEffect(() => {
    void loadCase();
  }, [caseId, loadCase]);

  const comparisonRows = useMemo(() => getComparisonRows(detail?.records_snapshot ?? null), [detail?.records_snapshot]);
  const evidenceNotes = useMemo(() => (detail ? getEvidenceNotes(detail) : []), [detail]);

  async function handleAnalyze() {
    setActionLoading(true);
    try {
      await analyzeCase(caseId);
      await loadCase();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "分析失败。");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleReview(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActionLoading(true);
    try {
      await submitReview(caseId, { reviewer, decision, comment });
      await loadCase();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "审核提交失败。");
    } finally {
      setActionLoading(false);
    }
  }

  if (loading && !detail) {
    return (
      <div className="page-shell detail-shell">
        <div className="loading-block">加载案例中...</div>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="page-shell detail-shell">
        <div className="loading-block">
          <p>{error || "案例不存在。"}</p>
          <button className="ghost-button" onClick={() => navigate("/")}>
            返回队列
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="page-shell detail-shell">
      <header className="detail-hero compact-header">
        <div className="workspace-title-block">
          <p className="panel-topline">异常处理页</p>
          <h1>{detail.base_info.case_id}</h1>
          <p className="detail-subline">
            {detail.base_info.external_ref} · {anomalyTypeLabel[detail.base_info.case_type] ?? detail.base_info.case_type} · {detail.base_info.owner}
          </p>
          <p className="hero-hint">
            {!detail.ai_result
              ? "先启动分析，再进入处理动作"
              : detail.ai_result.needs_human_review && !detail.review_result
                ? "右侧可直接提交审核"
                : "向下查看证据、规则与处理留痕"}
          </p>
        </div>
        <div className="hero-actions">
          <span className={`risk-pill risk-${detail.rule_results?.risk_level ?? "low"}`}>
            {riskText(detail.rule_results?.risk_level)}
          </span>
          <StatusBadge status={detail.base_info.status} />
          <Link className="ghost-button as-link" to="/">
            返回队列
          </Link>
        </div>
      </header>

      {error ? <div className="inline-alert">{error}</div> : null}

      <div className="workspace-grid detail-layout">
        <div className="detail-main">
          <SectionCard
            eyebrow="证据"
            title="字段对比"
            aside={
              !detail.ai_result ? (
                <button className="primary-button" onClick={handleAnalyze} disabled={actionLoading}>
                  {actionLoading ? "分析中..." : "启动分析"}
                </button>
              ) : null
            }
          >
            <div className="table-shell">
              <table className="comparison-table">
                <thead>
                  <tr>
                    <th>字段</th>
                    <th>PO</th>
                    <th>收货</th>
                    <th>发票 / 物流</th>
                    <th>结果</th>
                  </tr>
                </thead>
                <tbody>
                  {comparisonRows.map((row) => (
                    <tr key={row.label}>
                      <td>{row.label}</td>
                      <td>{String(row.po ?? "-")}</td>
                      <td>{String(row.receipt ?? "-")}</td>
                      <td>{String(row.invoice ?? "-")}</td>
                      <td>
                        <span className={`result-pill result-${row.result}`}>{row.result}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="evidence-strip">
              {evidenceNotes.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
          </SectionCard>

          <SectionCard eyebrow="规则" title="规则命中">
            <div className="table-shell">
              <table className="comparison-table dense-table">
                <thead>
                  <tr>
                    <th>规则编码</th>
                    <th>严重度</th>
                    <th>证据字段</th>
                    <th>下一检查项</th>
                  </tr>
                </thead>
                <tbody>
                  {(detail.rule_results?.rule_hits ?? []).map((hit) => (
                    <tr key={`${hit.rule_code}-${hit.message}`}>
                      <td>{hit.rule_code}</td>
                      <td>
                        <span className={`risk-pill risk-${hit.severity}`}>{riskText(hit.severity)}</span>
                      </td>
                      <td>{hit.evidence_refs.join(" / ")}</td>
                      <td>{hit.suggested_next_checks[0] ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flag-strip">
              {(detail.rule_results?.risk_flags ?? []).map((flag) => (
                <span key={flag}>{riskFlagLabel[flag] ?? flag}</span>
              ))}
            </div>
          </SectionCard>

          <SectionCard eyebrow="审计" title="时间线">
            <Timeline logs={detail.audit_logs} />
          </SectionCard>
        </div>

        <aside className="detail-side">
          <SectionCard eyebrow="摘要" title="处置摘要">
            <div className="summary-grid">
              <div className="summary-item">
                <span>负责人</span>
                <strong>{detail.base_info.owner}</strong>
              </div>
              <div className="summary-item">
                <span>队列</span>
                <strong>
                  {detail.base_info.queue_bucket === "waiting_review"
                    ? "待审核"
                    : detail.base_info.queue_bucket === "needs_more_info"
                      ? "待补证"
                      : detail.base_info.queue_bucket === "completed"
                        ? "已完成"
                        : detail.base_info.queue_bucket === "rejected"
                          ? "已驳回"
                          : "新流入"}
                </strong>
              </div>
              <div className="summary-item">
                <span>创建时间</span>
                <strong>{formatDate(detail.base_info.created_at)}</strong>
              </div>
              <div className="summary-item">
                <span>最近更新</span>
                <strong>{formatDate(detail.base_info.updated_at)}</strong>
              </div>
            </div>
            <div className="summary-copy">
              <h3>摘要</h3>
              <p>{detail.ai_result?.summary ?? detail.base_info.user_description}</p>
            </div>
          </SectionCard>

          <SectionCard eyebrow="分析" title="建议动作">
            <div className="analysis-block">
              <h3>可能原因</h3>
              <ul>
                {(detail.ai_result?.possible_causes ?? []).map((cause) => (
                  <li key={cause}>{cause}</li>
                ))}
              </ul>
            </div>
            <div className="analysis-block">
              <h3>建议下一步</h3>
              <ul>
                {(detail.ai_result?.recommended_action ?? []).map((action) => (
                  <li key={action}>{action}</li>
                ))}
              </ul>
            </div>
            <div className="analysis-block">
              <h3>审核门槛</h3>
              <p>{detail.ai_result?.review_reason ?? "未生成分析结果"}</p>
            </div>
          </SectionCard>

          <SectionCard eyebrow="审核" title="人工确认">
            {detail.ai_result?.needs_human_review && !detail.review_result ? (
              <form className="review-form" onSubmit={handleReview}>
                <label>
                  审核人
                  <input value={reviewer} onChange={(event) => setReviewer(event.target.value)} />
                </label>
                <label>
                  处理决定
                  <select value={decision} onChange={(event) => setDecision(event.target.value)}>
                    <option value="approve">通过</option>
                    <option value="reject">驳回</option>
                    <option value="request_more_info">要求补充信息</option>
                  </select>
                </label>
                <label>
                  审核意见
                  <textarea value={comment} onChange={(event) => setComment(event.target.value)} rows={4} />
                </label>
                <button className="primary-button full-width" type="submit" disabled={actionLoading}>
                  {actionLoading ? "提交中..." : "提交审核"}
                </button>
                <p className="form-hint">提交后会自动写入时间线</p>
              </form>
            ) : detail.review_result ? (
              <div className="review-result">
                <p>
                  <strong>
                    {detail.review_result.decision === "approve"
                      ? "通过"
                      : detail.review_result.decision === "reject"
                        ? "驳回"
                        : "要求补充信息"}
                  </strong>
                </p>
                <p>{detail.review_result.reviewer}</p>
                <p>{detail.review_result.comment || "无附加意见"}</p>
                <p className="muted">{formatDate(detail.review_result.created_at)}</p>
              </div>
            ) : (
              <p className="muted">当前案例无需人工确认</p>
            )}
          </SectionCard>
        </aside>
      </div>
    </div>
  );
}
