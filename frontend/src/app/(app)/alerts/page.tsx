"use client";

import Link from "next/link";
import { useState } from "react";
import { LoadState } from "@/components/LoadState";
import { api, errorKey } from "@/lib/api";
import { isKnownMetric, number } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { MessageKey } from "@/lib/messages";
import { useRole } from "@/lib/session";
import type { Alert, Device, Pond } from "@/lib/types";
import { usePolled } from "@/lib/usePolled";

const STATES: { value: string; label: MessageKey }[] = [
  { value: "", label: "state_all" },
  { value: "open", label: "state_open" },
  { value: "acknowledged", label: "state_acknowledged" },
  { value: "closed", label: "state_closed" },
];

export default function AlertsPage() {
  const { t, dateTime } = useI18n();
  const role = useRole();
  const canAcknowledge = role === "owner" || role === "manager";
  const [state, setState] = useState("");
  const [actionError, setActionError] = useState<MessageKey>();
  const { data, error, loading, reload } = usePolled(async () => {
    const [alerts, ponds, devices] = await Promise.all([
      api<Alert[]>(`/alerts?limit=500${state ? `&state=${state}` : ""}`),
      api<Pond[]>("/ponds?limit=500"),
      api<Device[]>("/devices?limit=500"),
    ]);
    return {
      alerts,
      pondNames: new Map(ponds.map((pond) => [pond.id, pond.name])),
      deviceNames: new Map(devices.map((device) => [device.id, device.serial])),
    };
  }, [state]);

  async function acknowledge(id: string) {
    setActionError(undefined);
    try {
      await api(`/alerts/${id}/acknowledge`, { method: "POST" });
      await reload();
    } catch (caught) {
      setActionError(errorKey(caught));
    }
  }

  function problem(alert: Alert): string {
    if (alert.kind === "no_data") return t("alert_no_data");
    const metric = isKnownMetric(alert.metric) ? t(`metric_${alert.metric}`) : (alert.metric ?? "");
    return t("alert_metric", { metric });
  }

  return (
    <>
      <header className="head">
        <h1>{t("alerts_title")}</h1>
        <select
          aria-label={t("filter")}
          value={state}
          onChange={(event) => setState(event.target.value)}
        >
          {STATES.map((item) => (
            <option key={item.value} value={item.value}>
              {t(item.label)}
            </option>
          ))}
        </select>
      </header>
      <LoadState loading={loading} error={error} hasData={!!data} />
      {actionError && (
        <p className="banner" role="alert">
          {t(actionError)}
        </p>
      )}
      {data && data.alerts.length === 0 && <p className="muted">{t("no_alerts")}</p>}
      {data && (
        <div className="list">
          {data.alerts.map((alert) => (
            <article key={alert.id} className={`item ${alert.state === "closed" ? "" : alert.severity}`}>
              <div className="item-head">
                <span className={`status ${alert.severity}`}>
                  {alert.severity === "critical" ? "▲" : "◆"} {t(`sev_${alert.severity}`)}
                </span>
                <span className="muted small">{t(`state_${alert.state}`)}</span>
              </div>
              <b>
                {alert.pond_id ? (
                  <Link href={`/ponds/${alert.pond_id}`}>
                    {data.pondNames.get(alert.pond_id) ?? t("pond")}
                  </Link>
                ) : (
                  t("pond")
                )}
                : {problem(alert)}
              </b>
              {alert.kind === "threshold" && (
                <span>
                  {t("value_line", {
                    value: number(alert.last_value),
                    limit: number(alert.threshold),
                  })}
                </span>
              )}
              <span className="muted small">
                {t("started", { time: dateTime(alert.opened_at) })} · {t("device")}{" "}
                {data.deviceNames.get(alert.device_id) ?? "—"}
              </span>
              {canAcknowledge && alert.state === "open" && (
                <button className="primary" onClick={() => void acknowledge(alert.id)}>
                  {t("mark_seen")}
                </button>
              )}
            </article>
          ))}
        </div>
      )}
    </>
  );
}
