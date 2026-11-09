// These match the response formats in backend/app/schemas.

export type Role = "owner" | "manager" | "viewer";
export type PondStatus =
  | "UNKNOWN"
  | "OK"
  | "LOW"
  | "CRITICAL_ALERT"
  | "NO_DATA"
  | "SUBSCRIPTION_EXPIRED";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
}

export interface Me {
  id: string;
  email: string;
  full_name: string;
  is_platform_admin: boolean;
  current_organization_id: string | null;
  organizations: { organization_id: string; organization_name: string; role: Role }[];
}

export interface Farm {
  id: string;
  name: string;
}

export interface Pond {
  id: string;
  farm_id: string;
  name: string;
  status: PondStatus;
}

export interface PondSummary extends Pond {
  dissolved_oxygen: number | null;
  last_reading_at: string | null;
}

export interface Metrics {
  dissolved_oxygen: number | null;
  temperature: number | null;
  ph: number | null;
  salinity: number | null;
  ammonia: number | null;
}

export interface DeviceReading extends Metrics {
  device_id: string;
  ts: string;
  is_stale: boolean;
  extra: Record<string, number> | null;
}

export interface PondDetail extends PondSummary {
  devices: DeviceReading[];
}

export interface Dashboard {
  farm: Farm;
  summary: {
    ponds_total: number;
    ponds_in_range: number;
    open_alerts: number;
    median_dissolved_oxygen: number | null;
  };
  ponds: PondSummary[];
}

export interface Device {
  id: string;
  serial: string;
  name: string | null;
  pond_id: string | null;
  last_reading_at: string | null;
  has_access: boolean;
}

export interface HistoryPoint extends Metrics {
  ts: string;
}

export interface History {
  device_id: string;
  resolution: "raw" | "hour" | "day";
  points: HistoryPoint[];
}

export interface Alert {
  id: string;
  pond_id: string | null;
  device_id: string;
  kind: "threshold" | "no_data";
  metric: string | null;
  severity: "low" | "critical";
  state: "open" | "acknowledged" | "closed";
  threshold: number | null;
  last_value: number | null;
  opened_at: string;
  acknowledged_at: string | null;
  closed_at: string | null;
}

export interface AlertRule {
  id: string;
  org_id: string | null;
  farm_id: string | null;
  pond_id: string | null;
  metric: string;
  operator: "lt" | "lte" | "gt" | "gte";
  threshold: number;
  severity: "low" | "critical";
  clear_after: number;
  enabled: boolean;
}

export interface Subscription {
  id: string;
  device_id: string;
  plan_name: string;
  state: "pending" | "active" | "grace" | "expired" | "canceled";
  starts_at: string;
  ends_at: string;
  access_until: string;
}
