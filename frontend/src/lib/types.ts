// Mirrors the FastAPI response shapes. Kept hand-written rather than generated
// so it stays readable -- if the backend adds a field, add it here too.

export type SiteType = "solar" | "wind";
export type Severity = "critical" | "warning" | "info";
export type SiteStatus = "critical" | "warning" | "normal" | "unavailable";

export type AlertType =
  | "over_generation"
  | "under_generation"
  | "ramp_up"
  | "ramp_down";

export type ActionType =
  | "curtail"
  | "storage_charge"
  | "backup_activation"
  | "spinning_reserve"
  | "grid_absorption_check";

export interface Site {
  id: number;
  name: string;
  site_type: SiteType;
  latitude: number;
  longitude: number;
  capacity_kw: number;
  region: string;
  export_limit_kw: number;
  firm_commitment_kw: number;
  commitment_start_hour_utc: number;
  commitment_end_hour_utc: number;
  storage_capacity_kwh: number;
  storage_soc_kwh: number;
  over_threshold: number;
  under_threshold: number;
  ramp_threshold: number;
  is_demo_site: boolean;
  notes: string;
}

export interface WeatherPoint {
  ghi_wm2: number;
  direct_radiation_wm2: number;
  diffuse_radiation_wm2: number;
  temperature_c: number;
  windspeed_10m_ms: number;
  windspeed_100m_ms: number;
  cloudcover_pct: number;
}

export interface ForecastPoint {
  timestamp: string;
  hours_ahead: number;
  predicted_kw: number;
  lower_kw: number;
  upper_kw: number;
  capacity_factor: number;
  potential_kw: number;
  weather: WeatherPoint;
}

export interface HistoryPoint {
  timestamp: string;
  actual_kw: number;
  predicted_kw: number | null;
}

export interface Alert {
  id: string;
  type: AlertType;
  severity: Severity;
  start: string;
  end: string;
  duration_hours: number;
  headline: string;
  detail: string;
  threshold_kw: number;
  // Present depending on alert type.
  peak_kw?: number;
  trough_kw?: number;
  reference_kw?: number;
  reference_label?: string;
  surplus_kwh?: number;
  shortfall_kwh?: number;
  peak_surplus_kw?: number;
  peak_shortfall_kw?: number;
  peak_pct_of_reference?: number;
  delta_kw?: number;
  from_kw?: number;
  to_kw?: number;
  steepest_hourly_kw?: number;
  pct_of_capacity_per_hour?: number;
}

export interface Recommendation {
  id: string;
  site_id: number;
  alert_id: string;
  action: ActionType;
  title: string;
  severity: Severity;
  window_start: string;
  window_end: string;
  /** Energy total, used for portfolio roll-ups. Zero for ramp actions. */
  quantity_kwh: number;
  /** The figure to show, with the unit the engine measured it in. */
  quantity: number;
  quantity_unit: "kWh" | "kW";
  quantity_label: string;
  reason: string;
}

export interface AlertSummary {
  total: number;
  critical: number;
  warning: number;
  info: number;
  by_type: Record<AlertType, number>;
  status: SiteStatus;
}

export interface ModelInfo {
  algorithm: string;
  trained_at: string | null;
  mae_pct_capacity: number | null;
  rmse_pct_capacity: number | null;
  r2: number | null;
  improvement_over_persistence_pct: number | null;
  confidence_pct: number;
  band_width_pct_capacity: number;
}

export interface BacktestScore {
  available: boolean;
  hours_scored?: number;
  mae_kw?: number;
  mae_pct_capacity?: number;
  rmse_kw?: number;
  rmse_pct_capacity?: number;
  r2?: number | null;
  bias_kw?: number;
  window_start?: string;
  window_end?: string;
}

export interface SiteForecast {
  site_id: number;
  site_name: string;
  site_type: SiteType;
  capacity_kw: number;
  export_limit_kw: number;
  generated_at: string;
  horizon_hours: number;
  current: {
    timestamp: string;
    output_kw: number;
    capacity_factor: number;
    weather: WeatherPoint & { timestamp: string };
  };
  today_generated_kwh: number;
  forecast: ForecastPoint[];
  history: HistoryPoint[];
  backtest: BacktestScore;
  model: ModelInfo;
  alerts: Alert[];
  alert_summary: AlertSummary;
  recommendations: Recommendation[];
  cache?: { hit: boolean; expires_at: string };
}

export interface PortfolioSite {
  id: number;
  name: string;
  site_type: SiteType;
  region: string;
  latitude: number;
  longitude: number;
  capacity_kw: number;
  is_demo_site: boolean;
  status: SiteStatus;
  error?: string;
  current_output_kw: number;
  capacity_factor: number;
  today_generated_kwh: number;
  peak_forecast_kw: number;
  alert_counts: { critical: number; warning: number; info: number };
  top_recommendation: Recommendation | null;
}

export interface PortfolioSummary {
  generated_at: string;
  site_count: number;
  total_capacity_kw: number;
  current_output_kw: number;
  portfolio_capacity_factor: number;
  forecast_24h_mwh: number;
  sites_with_alerts: number;
  alert_counts: { critical: number; warning: number; info: number };
  curtailment_at_risk_mwh: number;
  curtailment_avoidable_mwh: number;
  shortfall_to_cover_mwh: number;
  sites: PortfolioSite[];
  model: {
    trained_at: string | null;
    dataset_rows: number | null;
    dataset_span: [string, string] | null;
    solar: Record<string, unknown>;
    wind: Record<string, unknown>;
  };
}

export interface HistoricalBacktest {
  site_id: number;
  site_name: string;
  days: number;
  capacity_kw: number;
  points: { timestamp: string; actual_kw: number; predicted_kw: number }[];
  accuracy: BacktestScore;
}
