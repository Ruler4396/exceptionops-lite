import type {
  CaseQueueResponse,
  CaseDetail,
} from "./types";

const baseUrl = import.meta.env.BASE_URL.replace(/\/$/, "");
const apiBase = `${baseUrl === "" ? "" : baseUrl}/api`;

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Request failed." }));
    throw new Error(payload.detail ?? "Request failed.");
  }

  return response.json() as Promise<T>;
}

export function analyzeCase(caseId: string) {
  return apiRequest<{ run_id: string; current_status: string; ai_result: Record<string, unknown> }>(
    `/cases/${caseId}/analyze`,
    { method: "POST" },
  );
}

export function fetchCaseDetail(caseId: string): Promise<CaseDetail> {
  return apiRequest(`/cases/${caseId}`);
}

export function submitReview(
  caseId: string,
  payload: { reviewer: string; decision: string; comment?: string },
) {
  return apiRequest<{ updated_status: string }>(`/cases/${caseId}/review`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchCaseQueue(status = "all"): Promise<CaseQueueResponse> {
  const params = new URLSearchParams();
  if (status && status !== "all") {
    params.set("status", status);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiRequest(`/cases${suffix}`);
}
