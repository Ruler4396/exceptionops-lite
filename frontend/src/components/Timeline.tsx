import type { CaseDetail } from "../lib/types";

function formatDate(value: string) {
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function Timeline({ logs }: { logs: CaseDetail["audit_logs"] }) {
  return (
    <ol className="timeline-list">
      {logs.map((log) => (
        <li key={`${log.event_type}-${log.created_at}`} className="timeline-item">
          <div className="timeline-dot" />
          <div className="timeline-body">
            <div className="timeline-meta">
              <strong>{log.event_type}</strong>
              <span>{formatDate(log.created_at)}</span>
            </div>
            <pre>{JSON.stringify(log.payload, null, 2)}</pre>
          </div>
        </li>
      ))}
    </ol>
  );
}

