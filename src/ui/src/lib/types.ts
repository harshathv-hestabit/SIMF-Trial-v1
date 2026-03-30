export interface ClientListItem {
  client_id: string;
  client_name: string;
}

export interface ClientListResponse {
  items: ClientListItem[];
}

export interface WeightEntry {
  label: string;
  weight_percent: number;
}

export interface ClientPortfolio {
  client_id: string;
  client_name?: string;
  client_type?: string;
  mandate?: string;
  total_aum_aed?: number;
  ticker_count: number;
  ticker_symbols: string[];
  currencies: string[];
  tags_of_interest: string[];
  query?: string;
  classification_weights: WeightEntry[];
  asset_type_weights: WeightEntry[];
  asset_descriptions: string[];
  isins: string[];
}

export interface ClientInsight {
  id: string;
  client_id: string;
  news_title: string;
  insight: string;
  verification_score?: number;
  tickers: string[];
  status: string;
  timestamp?: string;
}

export interface ClientInsightListResponse {
  client_id: string;
  count: number;
  items: ClientInsight[];
}

export interface OpsMetrics {
  news_docs: number;
  queued_to_mas: number;
  in_insight_generation: number;
  insights_saved: number;
  failed_news_docs: number;
}

export interface OpsNewsItem {
  id: string;
  title: string;
  source: string;
  symbols: string[];
  symbols_preview: string;
  stage: string;
  status: string;
  updated_at: string;
  published_at: string;
}

export interface OpsNewsListResponse {
  count: number;
  items: OpsNewsItem[];
}

export interface TimelineEvent {
  timestamp?: string;
  stage: string;
  status?: string;
  details: string;
}

export interface OpsNewsDetail {
  id: string;
  title: string;
  source: string;
  symbols: string[];
  published_at: string;
  current_stage: string;
  current_status: string;
  updated_at: string;
  timeline: TimelineEvent[];
  raw_monitoring: Record<string, unknown>;
}

export interface OpsInsightItem {
  client_id: string;
  news_doc_id?: string;
  news_title: string;
  status: string;
  verification_score?: number;
  timestamp?: string;
}

export interface OpsInsightListResponse {
  count: number;
  items: OpsInsightItem[];
}

export interface PipelineRunResult {
  documents_processed: number;
  pipeline_status: string;
  sample_folder?: string;
}
