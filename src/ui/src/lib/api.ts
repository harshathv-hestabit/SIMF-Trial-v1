import type {
  ClientInsightListResponse,
  ClientListResponse,
  ClientPortfolio,
  OpsInsightListResponse,
  OpsMetrics,
  OpsNewsDetail,
  OpsNewsListResponse,
  PipelineRunResult,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(payload.detail ?? `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  listClients: () => request<ClientListResponse>("/api/clients"),
  getClientPortfolio: (clientId: string) =>
    request<ClientPortfolio>(`/api/clients/${clientId}/portfolio`),
  getClientInsights: (clientId: string) =>
    request<ClientInsightListResponse>(`/api/clients/${clientId}/insights`),
  getOpsMetrics: () => request<OpsMetrics>("/api/ops/metrics"),
  getOpsNews: (limit = 50) =>
    request<OpsNewsListResponse>(`/api/ops/news?limit=${limit}`),
  getOpsNewsDetail: (newsId: string) =>
    request<OpsNewsDetail>(`/api/ops/news/${newsId}`),
  getOpsInsights: (limit = 10) =>
    request<OpsInsightListResponse>(`/api/ops/insights?limit=${limit}`),
  uploadPipelineFiles: (files: File[]) => {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append("files", file);
    });
    return request<PipelineRunResult>("/api/ops/pipeline/upload", {
      method: "POST",
      body: formData,
    });
  },
};
