import type { CaseDetail } from "../lib/types";

function formatDate(value: string) {
  return new Date(value).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getEventLabel(eventType: string) {
  const mapping: Record<string, string> = {
    case_seeded: "案例已入库",
    case_created: "案例已创建",
    assignment_updated: "负责人已更新",
    context_ready: "证据快照已生成",
    context_failed: "证据快照失败",
    analysis_started: "分析已启动",
    analysis_completed: "分析已完成",
    analysis_failed: "分析失败",
    review_recorded: "人工审核已记录",
  };
  return mapping[eventType] ?? eventType;
}

function getRiskLabel(value: unknown) {
  if (value === "high") return "高风险";
  if (value === "medium") return "中风险";
  if (value === "low") return "低风险";
  return String(value ?? "");
}

function getDecisionLabel(value: unknown) {
  if (value === "approve") return "通过";
  if (value === "reject") return "驳回";
  if (value === "request_more_info") return "待补证";
  return String(value ?? "");
}

function buildTimelineContent(log: CaseDetail["audit_logs"][number]) {
  const payload = log.payload ?? {};

  if (log.event_type === "case_seeded" || log.event_type === "case_created") {
    const refs = [payload.external_ref, payload.owner].filter(Boolean).map(String);
    return {
      title: getEventLabel(log.event_type),
      description:
        log.event_type === "case_seeded"
          ? "演示案例已写入系统，并完成初始分派。"
          : "异常案例已登记，等待后续分析链路执行。",
      tags: refs,
    };
  }

  if (log.event_type === "context_ready") {
    const ruleCodes = Array.isArray(payload.rule_codes) ? payload.rule_codes.map(String) : [];
    return {
      title: getEventLabel(log.event_type),
      description: `已生成跨系统证据快照，识别 ${ruleCodes.length} 条规则命中。`,
      tags: [getRiskLabel(payload.risk_level), ...ruleCodes.slice(0, 3)],
    };
  }

  if (log.event_type === "analysis_started") {
    return {
      title: getEventLabel(log.event_type),
      description: "规则结果与上下文快照已送入分析流程。",
      tags: [],
    };
  }

  if (log.event_type === "analysis_completed") {
    return {
      title: getEventLabel(log.event_type),
      description:
        payload.needs_human_review === true
          ? "结构化分析结果已返回，当前案例需要人工复核。"
          : "结构化分析结果已返回，当前案例可按受控路径继续流转。",
      tags: [getRiskLabel(payload.risk_level), payload.run_id ? String(payload.run_id) : ""].filter(Boolean),
    };
  }

  if (log.event_type === "analysis_failed") {
    return {
      title: getEventLabel(log.event_type),
      description: payload.error ? String(payload.error) : "分析流程未成功完成。",
      tags: ["需重试"],
    };
  }

  if (log.event_type === "review_recorded") {
    const tags = [getDecisionLabel(payload.decision), payload.reviewer].filter(Boolean).map(String);
    const comment = payload.comment ? `审核备注：${String(payload.comment)}` : "审核动作已落表并写入审计记录。";
    return {
      title: getEventLabel(log.event_type),
      description: comment,
      tags,
    };
  }

  if (log.event_type === "assignment_updated") {
    const tags = [payload.from_owner, payload.to_owner, payload.assigned_by].filter(Boolean).map(String);
    return {
      title: getEventLabel(log.event_type),
      description: payload.comment ? `转派备注：${String(payload.comment)}` : "案例负责人已调整。",
      tags,
    };
  }

  return {
    title: getEventLabel(log.event_type),
    description: "系统事件已记录。",
    tags: Object.values(payload).slice(0, 2).map(String),
  };
}

export function Timeline({ logs }: { logs: CaseDetail["audit_logs"] }) {
  return (
    <ol className="timeline-list">
      {logs.map((log) => {
        const content = buildTimelineContent(log);
        return (
          <li key={`${log.event_type}-${log.created_at}`} className="timeline-item">
            <div className="timeline-dot" />
            <div className="timeline-body">
              <div className="timeline-meta">
                <strong>{content.title}</strong>
                <span>{formatDate(log.created_at)}</span>
              </div>
              <p className="timeline-description">{content.description}</p>
              {content.tags.length > 0 ? (
                <div className="timeline-tags">
                  {content.tags.map((tag) => (
                    <span key={`${log.event_type}-${log.created_at}-${tag}`} className="timeline-tag">
                      {tag}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
