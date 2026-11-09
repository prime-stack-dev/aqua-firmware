// Sample data for demo mode (see IS_DEMO in api.ts). Changes last until the page reloads.
import { ApiError } from "./api";
import type {
  Alert,
  AlertRule,
  Dashboard,
  Device,
  DeviceReading,
  Farm,
  History,
  Me,
  Pond,
  PondDetail,
  PondStatus,
  PondSummary,
  Subscription,
} from "./types";

const ORG_ID = "demo-org";
const FARM: Farm = { id: "demo-farm", name: "Demo Farm" };
const MINUTE = 60_000;
const DAY = 24 * 60 * MINUTE;

const SPECIAL: Record<number, { status: PondStatus; oxygen: number | null }> = {
  3: { status: "LOW", oxygen: 4.7 },
  7: { status: "CRITICAL_ALERT", oxygen: 3.8 },
  11: { status: "LOW", oxygen: 4.9 },
  14: { status: "NO_DATA", oxygen: null },
  19: { status: "SUBSCRIPTION_EXPIRED", oxygen: null },
};

const pad = (n: number) => String(n).padStart(2, "0");
const ago = (ms: number) => new Date(Date.now() - ms).toISOString();

const PONDS = Array.from({ length: 20 }, (_, i) => {
  const n = i + 1;
  const { status, oxygen } = SPECIAL[n] ?? {
    status: "OK" as const,
    oxygen: 5.6 + ((n * 7) % 12) / 10,
  };
  return { id: `pond-${pad(n)}`, deviceId: `device-${pad(n)}`, n, status, oxygen };
});

let alerts: Alert[] = [
  demoAlert(7, "threshold", "critical", 4.0, 3.8, 60),
  demoAlert(14, "no_data", "critical", null, null, 9),
  demoAlert(3, "threshold", "low", 5.0, 4.7, 25),
  demoAlert(11, "threshold", "low", 5.0, 4.9, 12),
];

function demoAlert(
  n: number,
  kind: Alert["kind"],
  severity: Alert["severity"],
  threshold: number | null,
  last_value: number | null,
  minutesAgo: number,
): Alert {
  return {
    id: `alert-${pad(n)}`,
    pond_id: `pond-${pad(n)}`,
    device_id: `device-${pad(n)}`,
    kind,
    metric: kind === "threshold" ? "dissolved_oxygen" : null,
    severity,
    state: "open",
    threshold,
    last_value,
    opened_at: ago(minutesAgo * MINUTE),
    acknowledged_at: null,
    closed_at: null,
  };
}

const defaultRule = (severity: AlertRule["severity"], threshold: number): AlertRule => ({
  id: `default-${severity}`,
  org_id: null,
  farm_id: null,
  pond_id: null,
  metric: "dissolved_oxygen",
  operator: "lt",
  threshold,
  severity,
  clear_after: 3,
  enabled: true,
});

let rules: AlertRule[] = [defaultRule("critical", 4.0), defaultRule("low", 5.0)];
let nextRule = 1;

const pondOut = (p: (typeof PONDS)[number]): Pond => ({
  id: p.id,
  farm_id: FARM.id,
  name: `Pond ${pad(p.n)}`,
  status: p.status,
});

const summary = (p: (typeof PONDS)[number]): PondSummary => ({
  ...pondOut(p),
  dissolved_oxygen: p.oxygen,
  last_reading_at: p.status === "SUBSCRIPTION_EXPIRED" ? null : ago(p.oxygen === null ? 9 * MINUTE : 0),
});

function dashboard(): Dashboard {
  const oxygen = PONDS.flatMap((p) => (p.oxygen === null ? [] : [p.oxygen])).sort((a, b) => a - b);
  const middle = Math.floor(oxygen.length / 2);
  return {
    farm: FARM,
    summary: {
      ponds_total: PONDS.length,
      ponds_in_range: PONDS.filter((p) => p.status === "OK").length,
      open_alerts: alerts.filter((alert) => alert.state !== "closed").length,
      median_dissolved_oxygen:
        oxygen.length % 2 ? oxygen[middle] : (oxygen[middle - 1] + oxygen[middle]) / 2,
    },
    ponds: PONDS.map(summary),
  };
}

function pondDetail(id: string): PondDetail {
  const pond = PONDS.find((p) => p.id === id);
  if (!pond) throw new ApiError(404, "Pond not found");
  const reading: DeviceReading = {
    device_id: pond.deviceId,
    ts: ago(pond.oxygen === null ? 9 * MINUTE : 0),
    is_stale: pond.oxygen === null,
    dissolved_oxygen: pond.oxygen ?? 6.0,
    temperature: 29.9,
    ph: 7.8,
    salinity: 15.2,
    ammonia: 0.02,
    extra: null,
  };
  return {
    ...summary(pond),
    devices: pond.status === "SUBSCRIPTION_EXPIRED" ? [] : [reading],
  };
}

function history(deviceId: string, query: URLSearchParams): History {
  const pond = PONDS.find((p) => p.deviceId === deviceId);
  const end = new Date(query.get("end") ?? Date.now()).getTime();
  const start = new Date(query.get("start") ?? end - DAY).getTime();
  const span = end - start;
  const finish = pond?.oxygen ?? 6.0;
  const steps = 120;
  const points = Array.from({ length: steps + 1 }, (_, i) => {
    const wave = Math.sin(i / 4) * 0.12;
    return {
      ts: new Date(start + (span * i) / steps).toISOString(),
      dissolved_oxygen: finish + (2.4 * (steps - i)) / steps + wave,
      temperature: 29 + Math.sin(i / 9),
      ph: 7.8 + wave / 2,
      salinity: 15.2 + wave,
      ammonia: 0.02 + Math.abs(wave) / 20,
    };
  });
  return {
    device_id: deviceId,
    resolution: span <= 2 * DAY ? "raw" : span <= 60 * DAY ? "hour" : "day",
    points,
  };
}

const devices = (): Device[] =>
  PONDS.map((p) => ({
    id: p.deviceId,
    serial: `DEMO-${pad(p.n)}`,
    name: null,
    pond_id: p.id,
    last_reading_at: p.status === "SUBSCRIPTION_EXPIRED" ? null : ago(p.oxygen === null ? 9 * MINUTE : 0),
    has_access: p.status !== "SUBSCRIPTION_EXPIRED",
  }));

const subscriptions = (): Subscription[] =>
  PONDS.map((p) => {
    const expired = p.status === "SUBSCRIPTION_EXPIRED";
    const endsIn = expired ? -35 * DAY : 300 * DAY;
    return {
      id: `sub-${pad(p.n)}`,
      device_id: p.deviceId,
      plan_name: "Standard",
      state: expired ? "expired" : "active",
      starts_at: ago(65 * DAY),
      ends_at: ago(-endsIn),
      access_until: ago(-endsIn - 7 * DAY),
    };
  });

const ME: Me = {
  id: "demo-user",
  email: "demo@example.com",
  full_name: "Demo User",
  is_platform_admin: false,
  current_organization_id: ORG_ID,
  organizations: [{ organization_id: ORG_ID, organization_name: "Demo Organization", role: "owner" }],
};

function acknowledge(id: string): Alert {
  const alert = alerts.find((item) => item.id === id);
  if (!alert) throw new ApiError(404, "Alert not found");
  alert.state = "acknowledged";
  alert.acknowledged_at = new Date().toISOString();
  alerts = [...alerts];
  return alert;
}

function createRule(body: Partial<AlertRule>): AlertRule {
  const scope = (rule: Partial<AlertRule>) =>
    [rule.farm_id ?? "", rule.pond_id ?? "", rule.metric, rule.severity].join("|");
  if (rules.some((rule) => rule.org_id && scope(rule) === scope(body))) {
    throw new ApiError(409, "A rule for this scope and severity already exists");
  }
  const rule: AlertRule = {
    clear_after: 3,
    enabled: true,
    farm_id: null,
    pond_id: null,
    metric: "dissolved_oxygen",
    operator: "lt",
    threshold: 0,
    severity: "critical",
    ...body,
    id: `rule-${nextRule++}`,
    org_id: ORG_ID,
  };
  rules = [...rules, rule];
  return rule;
}

function changeRule(id: string, method: string, body: Partial<AlertRule>): AlertRule | undefined {
  if (method === "DELETE") {
    rules = rules.filter((rule) => rule.id !== id);
    return undefined;
  }
  const updated = rules.find((rule) => rule.id === id);
  if (!updated) throw new ApiError(404, "Alert rule not found");
  Object.assign(updated, body);
  rules = [...rules];
  return updated;
}

/** Answers the same paths as the real API, using the sample data above. */
export function demoApi(fullPath: string, init: RequestInit): unknown {
  const [path, queryString] = fullPath.split("?");
  const query = new URLSearchParams(queryString);
  const method = init.method ?? "GET";
  const body = init.body ? JSON.parse(String(init.body)) : {};
  const part = path.split("/").filter(Boolean);

  if (path === "/me") return ME;
  if (path === "/farms") return [FARM];
  if (part[0] === "farms" && part[2] === "dashboard") return dashboard();
  if (path === "/ponds") return PONDS.map(pondOut);
  if (part[0] === "ponds") return pondDetail(part[1]);
  if (path === "/devices") return devices();
  if (part[0] === "telemetry" && part[2] === "history") return history(part[1], query);
  if (path === "/subscriptions") return subscriptions();
  if (path === "/alerts") {
    const state = query.get("state");
    return state ? alerts.filter((alert) => alert.state === state) : alerts;
  }
  if (part[0] === "alerts" && part[2] === "acknowledge") return acknowledge(part[1]);
  if (path === "/alert-rules") return method === "POST" ? createRule(body) : rules;
  if (part[0] === "alert-rules") return changeRule(part[1], method, body);
  throw new ApiError(404, "Not available in demo mode");
}
