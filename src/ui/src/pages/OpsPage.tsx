import {
  Button,
  Card,
  CardContent,
  CardHeader,
  Input,
  Spinner,
} from "@heroui/react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../lib/api";
import { DataTable, StatusChip } from "../components/DataTable";
import { MetricTile } from "../components/MetricTile";
import { SectionHeader } from "../components/SectionHeader";
import type {
  OpsInsightItem,
  OpsMetrics,
  OpsNewsDetail,
  OpsNewsItem,
  PipelineRunResult,
} from "../lib/types";

const REFRESH_INTERVAL_MS = 10_000;

export function OpsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [metrics, setMetrics] = useState<OpsMetrics | null>(null);
  const [news, setNews] = useState<OpsNewsItem[]>([]);
  const [recentInsights, setRecentInsights] = useState<OpsInsightItem[]>([]);
  const [selectedNews, setSelectedNews] = useState<OpsNewsDetail | null>(null);
  const [pipelineResult, setPipelineResult] = useState<PipelineRunResult | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [newsLimit, setNewsLimit] = useState("50");
  const [insightLimit, setInsightLimit] = useState("10");
  const [newsFilter, setNewsFilter] = useState("");
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [loading, setLoading] = useState(true);
  const [newsLoading, setNewsLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string>("");

  const selectedNewsId = searchParams.get("news") ?? "";
  const searchParamsValue = searchParams.toString();
  const filteredNews = news.filter((item) => {
    const query = newsFilter.trim().toLowerCase();
    if (!query) {
      return true;
    }
    return (
      item.title.toLowerCase().includes(query) ||
      item.source.toLowerCase().includes(query) ||
      item.stage.toLowerCase().includes(query) ||
      item.status.toLowerCase().includes(query)
    );
  });

  useEffect(() => {
    let active = true;

    async function loadDashboard() {
      setLoading(true);
      setError("");
      try {
        const [metricsResponse, newsResponse, insightsResponse] = await Promise.all([
          api.getOpsMetrics(),
          api.getOpsNews(Number(newsLimit)),
          api.getOpsInsights(Number(insightLimit)),
        ]);
        if (!active) {
          return;
        }
        setMetrics(metricsResponse);
        setNews(newsResponse.items);
        setRecentInsights(insightsResponse.items);
        const currentSelectedExists = newsResponse.items.some((item) => item.id === selectedNewsId);
        const firstNewsId = newsResponse.items[0]?.id ?? "";
        if (!selectedNewsId || !currentSelectedExists) {
          const nextParams = new URLSearchParams(searchParams);
          if (firstNewsId) {
            nextParams.set("news", firstNewsId);
          } else {
            nextParams.delete("news");
          }
          if (nextParams.toString() !== searchParamsValue) {
            setSearchParams(nextParams, { replace: true });
          }
        }
      } catch (err) {
        if (!active) {
          return;
        }
        setError(err instanceof Error ? err.message : "Failed to load dashboard");
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void loadDashboard();
    const timer = window.setInterval(() => {
      void loadDashboard();
    }, REFRESH_INTERVAL_MS);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [insightLimit, newsLimit, refreshNonce, searchParamsValue, selectedNewsId, setSearchParams]);

  useEffect(() => {
    if (!selectedNewsId) {
      setSelectedNews(null);
      return;
    }

    let active = true;

    async function loadNewsDetail() {
      setNewsLoading(true);
      try {
        const detail = await api.getOpsNewsDetail(selectedNewsId);
        if (!active) {
          return;
        }
        setSelectedNews(detail);
      } catch (err) {
        if (!active) {
          return;
        }
        setSelectedNews(null);
        setError(err instanceof Error ? err.message : "Failed to load news detail");
      } finally {
        if (active) {
          setNewsLoading(false);
        }
      }
    }

    void loadNewsDetail();
    return () => {
      active = false;
    };
  }, [selectedNewsId]);

  async function handleUploadRun() {
    if (files.length === 0) {
      setError("Select at least one JSON file before starting the pipeline.");
      return;
    }
    setActionLoading(true);
    setError("");
    try {
      setPipelineResult(await api.uploadPipelineFiles(files));
      setFiles([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload pipeline files");
    } finally {
      setActionLoading(false);
    }
  }

  return (
    <div className="grid gap-4 p-4 lg:p-5">
      {error ? <InlineError message={error} /> : null}

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MetricTile label="News Docs" value={loading ? "-" : metrics?.news_docs ?? 0} />
        <MetricTile label="Queued To MAS" value={loading ? "-" : metrics?.queued_to_mas ?? 0} />
        <MetricTile
          label="In Insight Gen"
          value={loading ? "-" : metrics?.in_insight_generation ?? 0}
        />
        <MetricTile label="Insights Saved" value={loading ? "-" : metrics?.insights_saved ?? 0} />
        <MetricTile
          label="Failed"
          value={loading ? "-" : metrics?.failed_news_docs ?? 0}
          accent="text-rose-700"
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.9fr)_360px]">
        <Card className="border border-[var(--border-1)] bg-[rgba(16,22,39,0.86)]">
          <CardHeader className="grid gap-3 border-b border-[rgba(139,163,255,0.12)] pb-4">
            <SectionHeader
              eyebrow="Lifecycle"
              title="Live news documents"
              description="Monitor recent news records and drill into lifecycle history."
              action={
                <Button
                  variant="ghost"
                  className="border border-[var(--border-1)] bg-[rgba(255,255,255,0.03)] text-[var(--text-2)]"
                  onPress={() => setRefreshNonce((value) => value + 1)}
                >
                  Refresh Now
                </Button>
              }
            />
            <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_140px_140px_auto]">
              <Input
                aria-label="Filter news rows"
                placeholder="Filter by title, source, stage, or status"
                className="rounded-2xl border border-[var(--border-1)] bg-[rgba(255,255,255,0.04)] px-4 py-3 text-[var(--text-1)] placeholder:text-[var(--text-3)]"
                value={newsFilter}
                onChange={(event) => setNewsFilter(event.currentTarget.value)}
              />
              <LimitPicker
                label="News rows"
                value={newsLimit}
                options={["10", "25", "50", "100", "200"]}
                onChange={setNewsLimit}
              />
              <LimitPicker
                label="Insight rows"
                value={insightLimit}
                options={["5", "10", "20", "50"]}
                onChange={setInsightLimit}
              />
              <div className="flex items-center justify-end">
                {loading ? <Spinner size="sm" /> : null}
              </div>
            </div>
          </CardHeader>
          <CardContent className="grid gap-3 px-4 pb-4 pt-3">
            <DataTable
              ariaLabel="Live news documents"
              rows={filteredNews}
              emptyMessage="No news documents found for the current filters."
              getRowKey={(row) => row.id}
              columns={[
                {
                  key: "title",
                  header: "Document",
                  cell: (row) => (
                    <button
                      type="button"
                      className="grid gap-1 text-left"
                      onClick={() => {
                        const nextParams = new URLSearchParams(searchParams);
                        nextParams.set("news", row.id);
                        setSearchParams(nextParams);
                      }}
                    >
                      <span className="font-semibold text-white">{row.title}</span>
                      <span className="text-xs text-[var(--text-3)]">{row.id}</span>
                    </button>
                  ),
                },
                {
                  key: "source",
                  header: "Source",
                  cell: (row) => row.source,
                },
                {
                  key: "stage",
                  header: "Stage",
                  cell: (row) => row.stage,
                },
                {
                  key: "status",
                  header: "Status",
                  cell: (row) => <StatusChip value={row.status} />,
                },
                {
                  key: "published_at",
                  header: "Published",
                  cell: (row) => row.published_at,
                },
                {
                  key: "updated_at",
                  header: "Updated",
                  cell: (row) => row.updated_at,
                },
              ]}
            />
          </CardContent>
        </Card>

        <div className="grid gap-4">
          <Card className="border border-[var(--border-1)] bg-[rgba(16,22,39,0.86)]">
            <CardHeader className="flex items-center justify-between">
              <SectionHeader
                eyebrow="Detail"
                title="Selected news timeline"
                description="Review lifecycle status and event-by-event details."
              />
              {newsLoading ? <Spinner size="sm" /> : null}
            </CardHeader>
            <CardContent className="grid gap-3 px-4 pb-4 pt-1">
              {selectedNews ? (
                <>
                  <div className="rounded-2xl border border-[var(--border-1)] bg-[rgba(115,166,255,0.07)] p-4">
                    <p className="font-semibold text-white">{selectedNews.title}</p>
                    <p className="mt-1 text-sm text-[var(--text-2)]">
                      {selectedNews.source} | {selectedNews.current_stage} | {selectedNews.current_status}
                    </p>
                    <p className="mt-1 text-xs text-[var(--text-3)]">
                      Published {selectedNews.published_at} | Updated {selectedNews.updated_at}
                    </p>
                  </div>
                  {selectedNews.timeline.length === 0 ? (
                    <p className="text-sm text-[var(--text-3)]">No lifecycle events yet.</p>
                  ) : (
                    <DataTable
                      ariaLabel="News lifecycle timeline"
                      rows={selectedNews.timeline}
                      emptyMessage="No lifecycle events yet."
                      getRowKey={(row, index) => `${row.timestamp ?? "event"}-${index}`}
                      columns={[
                        {
                          key: "timestamp",
                          header: "Timestamp",
                          cell: (row) => row.timestamp ?? "-",
                        },
                        {
                          key: "stage",
                          header: "Stage",
                          cell: (row) => row.stage,
                        },
                        {
                          key: "status",
                          header: "Status",
                          cell: (row) => <StatusChip value={row.status ?? "unknown"} />,
                        },
                        {
                          key: "details",
                          header: "Details",
                          cell: (row) => (
                            <span className="block max-w-[340px] whitespace-pre-wrap break-words text-xs text-[var(--text-3)]">
                              {row.details}
                            </span>
                          ),
                        },
                      ]}
                    />
                  )}
                </>
              ) : (
                <p className="text-sm text-[var(--text-3)]">
                  Select a news document to inspect its timeline.
                </p>
              )}
            </CardContent>
          </Card>

          <Card className="border border-[var(--border-1)] bg-[rgba(16,22,39,0.86)]">
            <CardHeader>
              <SectionHeader
                eyebrow="Pipeline"
                title="Manual DPS ingestion"
                description="Upload JSON documents to run the DPS pipeline manually."
              />
            </CardHeader>
            <CardContent className="grid gap-3 px-4 pb-4 pt-1">
              <div className="grid gap-3 rounded-2xl border border-dashed border-[var(--border-1)] bg-[rgba(255,255,255,0.03)] p-4">
                <input
                  type="file"
                  accept=".json,application/json"
                  multiple
                  onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
                />
                <div className="flex flex-wrap items-center gap-3">
                  <Button variant="primary" onPress={handleUploadRun} isDisabled={actionLoading}>
                    Upload JSON Files
                  </Button>
                  {actionLoading ? <Spinner size="sm" /> : null}
                  <p className="text-xs text-[var(--text-3)]">
                    {files.length > 0 ? `${files.length} file(s) selected` : "No files selected"}
                  </p>
                </div>
              </div>
              {pipelineResult ? (
                <div className="rounded-2xl border border-[rgba(255,78,184,0.22)] bg-[rgba(255,78,184,0.08)] p-4 text-sm text-[var(--text-1)]">
                  Processed {pipelineResult.documents_processed} document(s). {pipelineResult.pipeline_status}
                </div>
              ) : null}
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(280px,0.55fr)]">
        <Card className="border border-[var(--border-1)] bg-[rgba(16,22,39,0.86)]">
          <CardHeader>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.25em] text-[var(--text-3)]">
                Outputs
              </p>
              <h2 className="text-lg font-semibold text-white">Recent insight results</h2>
            </div>
          </CardHeader>
          <CardContent className="grid gap-2 px-4 pb-4 pt-1">
            {recentInsights.length === 0 ? (
              <p className="text-sm text-[var(--text-3)]">No insights generated yet.</p>
            ) : (
              <DataTable
                ariaLabel="Recent insights"
                rows={recentInsights}
                emptyMessage="No insights generated yet."
                getRowKey={(row, index) => `${row.news_doc_id ?? row.client_id}-${index}`}
                columns={[
                  {
                    key: "news_title",
                    header: "Insight",
                    cell: (row) => (
                      <div className="grid gap-1">
                        <span className="font-semibold">{row.news_title}</span>
                        <span className="text-xs text-[var(--text-3)]">{row.news_doc_id ?? "-"}</span>
                      </div>
                    ),
                  },
                  {
                    key: "client_id",
                    header: "Client",
                    cell: (row) => row.client_id,
                  },
                  {
                    key: "score",
                    header: "Score",
                    align: "right",
                    cell: (row) => row.verification_score ?? "-",
                  },
                  {
                    key: "status",
                    header: "Status",
                    cell: (row) => <StatusChip value={row.status} />,
                  },
                  {
                    key: "timestamp",
                    header: "Timestamp",
                    cell: (row) => row.timestamp ?? "-",
                  },
                ]}
              />
            )}
          </CardContent>
        </Card>

        <Card className="border border-[var(--border-1)] bg-[linear-gradient(180deg,rgba(24,30,52,0.92),rgba(17,21,37,0.86))]">
          <CardHeader>
            <SectionHeader
              eyebrow="Pulse"
              title="Runtime summary"
              description="Compact status for the current ingestion surface."
            />
          </CardHeader>
          <CardContent className="grid gap-3 px-4 pb-4 pt-1 text-sm text-[var(--text-2)]">
            <div className="rounded-2xl border border-[var(--border-1)] bg-[rgba(115,166,255,0.07)] p-4">
              Watching the most recent {news.length} news rows with {recentInsights.length} visible insights.
            </div>
            <div className="rounded-2xl border border-[rgba(255,78,184,0.18)] bg-[rgba(255,78,184,0.06)] p-4">
              Auto-refresh runs every 10 seconds. Use the manual refresh when you want a deterministic pull.
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function LimitPicker(props: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="grid gap-2 rounded-2xl border border-[var(--border-1)] bg-[rgba(255,255,255,0.03)] p-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--text-3)]">{props.label}</p>
      <div className="flex flex-wrap gap-2">
        {props.options.map((option) => (
          <Button
            key={option}
            size="sm"
            variant={option === props.value ? "primary" : "ghost"}
            className={
              option === props.value
                ? ""
                : "border border-[var(--border-1)] bg-[rgba(255,255,255,0.03)] text-[var(--text-2)]"
            }
            onPress={() => props.onChange(option)}
          >
            {option}
          </Button>
        ))}
      </div>
    </div>
  );
}

function InlineError(props: { message: string }) {
  return (
    <div className="rounded-2xl border border-[rgba(255,78,184,0.24)] bg-[rgba(255,78,184,0.08)] p-4 text-sm font-medium text-[var(--text-1)]">
      {props.message}
    </div>
  );
}
