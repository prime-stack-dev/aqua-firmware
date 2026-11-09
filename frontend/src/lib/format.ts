import type { PondStatus } from "./types";

export const METRICS = [
  { key: "dissolved_oxygen", unit: "mg/L" },
  { key: "temperature", unit: "°C" },
  { key: "ph", unit: "" },
  { key: "salinity", unit: "ppt" },
  { key: "ammonia", unit: "mg/L" },
] as const;

export type MetricKey = (typeof METRICS)[number]["key"];

export function isKnownMetric(key: string | null): key is MetricKey {
  return METRICS.some((metric) => metric.key === key);
}

export function number(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? "—" : value.toFixed(digits);
}

// Each status has its own symbol, so it never depends on colour alone.
export const STATUS: Record<PondStatus, { symbol: string; tone: string }> = {
  OK: { symbol: "●", tone: "ok" },
  LOW: { symbol: "◆", tone: "low" },
  CRITICAL_ALERT: { symbol: "▲", tone: "critical" },
  NO_DATA: { symbol: "○", tone: "nodata" },
  SUBSCRIPTION_EXPIRED: { symbol: "✕", tone: "nodata" },
  UNKNOWN: { symbol: "–", tone: "nodata" },
};
