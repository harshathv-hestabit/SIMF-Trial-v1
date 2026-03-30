import {
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  Input,
  Separator,
  Spinner,
} from "@heroui/react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../lib/api";
import { DataTable, StatusChip } from "../components/DataTable";
import { MetricTile } from "../components/MetricTile";
import { SectionHeader } from "../components/SectionHeader";
import type {
  ClientInsightListResponse,
  ClientListItem,
  ClientPortfolio,
  WeightEntry,
} from "../lib/types";

export function ClientsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [clients, setClients] = useState<ClientListItem[]>([]);
  const [portfolio, setPortfolio] = useState<ClientPortfolio | null>(null);
  const [insights, setInsights] = useState<ClientInsightListResponse | null>(null);
  const [searchValue, setSearchValue] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string>("");

  const selectedClientId = searchParams.get("client") ?? "";
  const selectedInsightId = searchParams.get("insight") ?? "";
  const searchParamsValue = searchParams.toString();
  const filteredClients = clients.filter((client) => {
    const query = searchValue.trim().toLowerCase();
    if (!query) {
      return true;
    }
    return (
      client.client_name.toLowerCase().includes(query) ||
      client.client_id.toLowerCase().includes(query)
    );
  });

  useEffect(() => {
    let alive = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const response = await api.listClients();
        if (!alive) {
          return;
        }
        setClients(response.items);
        const selectedStillExists = response.items.some((item) => item.client_id === selectedClientId);
        const firstClientId = response.items[0]?.client_id ?? "";
        if (!selectedClientId || !selectedStillExists) {
          const nextParams = new URLSearchParams(searchParams);
          if (firstClientId) {
            nextParams.set("client", firstClientId);
          } else {
            nextParams.delete("client");
          }
          nextParams.delete("insight");
          if (nextParams.toString() !== searchParamsValue) {
            setSearchParams(nextParams, { replace: true });
          }
        }
      } catch (err) {
        if (!alive) {
          return;
        }
        setError(err instanceof Error ? err.message : "Failed to load clients");
      } finally {
        if (alive) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      alive = false;
    };
  }, [searchParamsValue, selectedClientId, setSearchParams]);

  useEffect(() => {
    if (!selectedClientId) {
      setPortfolio(null);
      setInsights(null);
      return;
    }

    let alive = true;
    async function loadDetails() {
      setDetailLoading(true);
      setError("");
      try {
        const [portfolioResponse, insightsResponse] = await Promise.all([
          api.getClientPortfolio(selectedClientId),
          api.getClientInsights(selectedClientId),
        ]);
        if (!alive) {
          return;
        }
        setPortfolio(portfolioResponse);
        setInsights(insightsResponse);
        const firstInsightId = insightsResponse.items[0]?.id ?? "";
        const nextParams = new URLSearchParams(searchParams);
        nextParams.set("client", selectedClientId);
        if (!selectedInsightId && firstInsightId) {
          nextParams.set("insight", firstInsightId);
        } else if (
          selectedInsightId &&
          !insightsResponse.items.some((item) => item.id === selectedInsightId)
        ) {
          if (firstInsightId) {
            nextParams.set("insight", firstInsightId);
          } else {
            nextParams.delete("insight");
          }
        }
        if (nextParams.toString() !== searchParamsValue) {
          setSearchParams(nextParams, { replace: true });
        }
      } catch (err) {
        if (!alive) {
          return;
        }
        setError(err instanceof Error ? err.message : "Failed to load client details");
      } finally {
        if (alive) {
          setDetailLoading(false);
        }
      }
    }

    void loadDetails();
    return () => {
      alive = false;
    };
  }, [searchParamsValue, selectedClientId, selectedInsightId, setSearchParams]);

  const selectedInsight =
    insights?.items.find((item) => item.id === selectedInsightId) ??
    insights?.items[0] ??
    null;

  return (
    <div className="grid gap-4 p-4 lg:p-5">
      <section className="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)]">
        <Card className="border border-[var(--border-1)] bg-[rgba(16,22,39,0.86)]">
          <CardHeader>
            <SectionHeader
              eyebrow="Clients"
              title="Portfolio selector"
              description="Search clients and switch the active portfolio context."
            />
          </CardHeader>
          <CardContent className="gap-3 px-4 pb-4 pt-1">
            <Input
              aria-label="Search clients"
              placeholder="Search by name or ID"
              className="rounded-2xl border border-[var(--border-1)] bg-[rgba(255,255,255,0.04)] px-4 py-3 text-[var(--text-1)] placeholder:text-[var(--text-3)]"
              value={searchValue}
              onChange={(event) => setSearchValue(event.currentTarget.value)}
            />
            {loading ? (
              <div className="flex items-center gap-2 text-sm text-[var(--text-3)]">
                <Spinner size="sm" />
                <span>Loading clients</span>
              </div>
            ) : filteredClients.length === 0 ? (
              <p className="text-sm text-[var(--text-3)]">No clients matched the current search.</p>
            ) : (
              filteredClients.map((client) => (
                <Button
                  key={client.client_id}
                  variant={client.client_id === selectedClientId ? "primary" : "ghost"}
                  className={
                    client.client_id === selectedClientId
                      ? "justify-start"
                      : "justify-start border border-[var(--border-1)] bg-[rgba(255,255,255,0.03)] text-[var(--text-2)]"
                  }
                  onPress={() => {
                    const nextParams = new URLSearchParams(searchParams);
                    nextParams.set("client", client.client_id);
                    nextParams.delete("insight");
                    setSearchParams(nextParams);
                  }}
                >
                  <span className="truncate">{client.client_name}</span>
                </Button>
              ))
            )}
          </CardContent>
        </Card>

        <div className="grid gap-4">
          {error ? <ErrorCard message={error} /> : null}

          <Card className="border border-[var(--border-1)] bg-[rgba(16,22,39,0.86)]">
            <CardHeader className="flex items-center justify-between">
              <SectionHeader
                eyebrow="Portfolio"
                title={portfolio?.client_name ?? selectedClientId ?? "Select a client"}
                description="Client allocation, identifiers, and derived portfolio metadata."
              />
              {detailLoading ? <Spinner size="sm" /> : null}
            </CardHeader>
            <CardContent className="grid gap-4 px-4 pb-4 pt-1">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <MetricTile label="Client Type" value={portfolio?.client_type ?? "-"} />
                <MetricTile label="Mandate" value={portfolio?.mandate ?? "-"} />
                <MetricTile
                  label="AUM"
                  value={
                    portfolio?.total_aum_aed !== undefined
                      ? `AED ${portfolio.total_aum_aed.toLocaleString()}`
                      : "-"
                  }
                />
                <MetricTile label="Tickers" value={String(portfolio?.ticker_count ?? 0)} />
              </div>
              <Separator />
              <div className="grid gap-3 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
                <InfoBlock
                  title="Ticker Symbols"
                  value={(portfolio?.ticker_symbols ?? []).join(", ") || "No ticker symbols available."}
                />
                <InfoBlock
                  title="Portfolio Summary"
                  value={portfolio?.query ?? "No portfolio summary available."}
                />
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <InfoBlock
                  title="Currencies"
                  value={(portfolio?.currencies ?? []).join(", ") || "No currencies available."}
                />
                <InfoBlock
                  title="Tags Of Interest"
                  value={(portfolio?.tags_of_interest ?? []).join(", ") || "No derived tags available."}
                />
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                <WeightTable
                  title="Asset Class Weights"
                  rows={portfolio?.classification_weights ?? []}
                  emptyMessage="No asset class weights available."
                />
                <WeightTable
                  title="Asset Type Weights"
                  rows={portfolio?.asset_type_weights ?? []}
                  emptyMessage="No asset type weights available."
                />
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                <SimpleListTable
                  title="Top Asset Descriptions"
                  rows={portfolio?.asset_descriptions ?? []}
                  columnLabel="Asset Description"
                  emptyMessage="No asset descriptions available."
                />
                <SimpleListTable
                  title="Identifiers"
                  rows={portfolio?.isins ?? []}
                  columnLabel="ISIN"
                  emptyMessage="No ISINs available."
                />
              </div>
            </CardContent>
          </Card>

          <Card className="border border-[var(--border-1)] bg-[rgba(16,22,39,0.86)]">
            <CardHeader className="flex items-center justify-between">
              <SectionHeader
                eyebrow="Insights"
                title="Saved client insights"
                description="Browse recent outputs and inspect one selected insight in detail."
              />
              <Chip variant="soft">{insights?.count ?? 0}</Chip>
            </CardHeader>
            <CardContent className="grid gap-4 px-4 pb-4 pt-1 xl:grid-cols-[minmax(0,1.3fr)_360px]">
              {(insights?.items ?? []).length === 0 ? (
                <p className="text-sm text-[var(--text-3)]">No insights available for the selected client.</p>
              ) : (
                <>
                  <DataTable
                    ariaLabel="Client insights"
                    rows={insights?.items ?? []}
                    emptyMessage="No insights available for the selected client."
                    getRowKey={(row) => row.id}
                    columns={[
                      {
                        key: "news_title",
                        header: "News",
                        cell: (row) => (
                          <button
                            type="button"
                            className="grid gap-1 text-left"
                            onClick={() => {
                              const nextParams = new URLSearchParams(searchParams);
                              nextParams.set("client", selectedClientId);
                              nextParams.set("insight", row.id);
                              setSearchParams(nextParams);
                            }}
                          >
                            <span className="font-semibold text-white">{row.news_title}</span>
                            <span className="text-xs text-[var(--text-3)]">{row.timestamp ?? "unknown"}</span>
                          </button>
                        ),
                      },
                      {
                        key: "status",
                        header: "Status",
                        cell: (row) => <StatusChip value={row.status} />,
                      },
                      {
                        key: "score",
                        header: "Score",
                        align: "right",
                        cell: (row) => row.verification_score ?? "-",
                      },
                    ]}
                  />
                  <InsightDetail insight={selectedInsight} />
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}

function InsightDetail(props: { insight: ClientInsightListResponse["items"][number] | null }) {
  if (!props.insight) {
    return (
      <div className="rounded-2xl border border-dashed border-[var(--border-1)] bg-[rgba(255,255,255,0.03)] p-6 text-sm text-[var(--text-3)]">
        Select an insight to inspect its full output.
      </div>
    );
  }

  return (
    <div className="grid gap-3 rounded-2xl border border-[var(--border-1)] bg-[rgba(115,166,255,0.07)] p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-3)]">Selected Insight</p>
          <h3 className="mt-1 text-lg font-semibold text-white">{props.insight.news_title}</h3>
        </div>
        <StatusChip value={props.insight.status} />
      </div>
      <p className="text-sm text-[var(--text-2)]">
        Score {props.insight.verification_score ?? "-"} | {props.insight.timestamp ?? "unknown"}
      </p>
      {props.insight.tickers.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {props.insight.tickers.map((ticker) => (
            <Chip key={ticker} size="sm" variant="secondary">
              {ticker}
            </Chip>
          ))}
        </div>
      ) : null}
      <div className="rounded-2xl border border-[var(--border-1)] bg-[rgba(10,14,28,0.55)] p-4 text-sm leading-6 text-[var(--text-2)]">
        {props.insight.insight}
      </div>
    </div>
  );
}

function InfoBlock(props: { title: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[var(--border-1)] bg-[rgba(255,255,255,0.03)] p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-3)]">{props.title}</p>
      <p className="mt-2 text-sm leading-6 text-[var(--text-2)]">{props.value}</p>
    </div>
  );
}

function WeightTable(props: {
  title: string;
  rows: WeightEntry[];
  emptyMessage: string;
}) {
  return (
    <div className="grid gap-3">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-3)]">{props.title}</p>
      <DataTable
        rows={props.rows}
        emptyMessage={props.emptyMessage}
        columns={[
          {
            key: "label",
            header: "Label",
            cell: (row) => row.label,
          },
          {
            key: "weight",
            header: "Weight %",
            align: "right",
            cell: (row) => row.weight_percent.toFixed(2),
          },
        ]}
      />
    </div>
  );
}

function SimpleListTable(props: {
  title: string;
  rows: string[];
  columnLabel: string;
  emptyMessage: string;
}) {
  return (
    <div className="grid gap-3">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-3)]">{props.title}</p>
      <DataTable
        rows={props.rows.map((value) => ({ value }))}
        emptyMessage={props.emptyMessage}
        columns={[
          {
            key: "value",
            header: props.columnLabel,
            cell: (row) => row.value,
          },
        ]}
      />
    </div>
  );
}

function ErrorCard(props: { message: string }) {
  return (
    <Card className="border border-[rgba(255,78,184,0.24)] bg-[rgba(255,78,184,0.08)]">
      <CardContent>
        <p className="text-sm font-medium text-[var(--text-1)]">{props.message}</p>
      </CardContent>
    </Card>
  );
}
