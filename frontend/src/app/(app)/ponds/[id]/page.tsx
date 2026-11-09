"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { LineChart } from "@/components/LineChart";
import { LoadState } from "@/components/LoadState";
import { StatusLabel } from "@/components/StatusLabel";
import { api } from "@/lib/api";
import { type MetricKey, METRICS, number } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { MessageKey } from "@/lib/messages";
import type { DeviceReading, History, PondDetail } from "@/lib/types";
import { usePolled } from "@/lib/usePolled";

const RANGES: { label: MessageKey; hours: number }[] = [
  { label: "range_1d", hours: 24 },
  { label: "range_7d", hours: 24 * 7 },
  { label: "range_90d", hours: 24 * 90 },
];

function HistoryChart({ deviceId }: { deviceId: string }) {
  const { t } = useI18n();
  const [hours, setHours] = useState(24);
  const [metric, setMetric] = useState<MetricKey>("dissolved_oxygen");
  const { data, error, loading } = usePolled(() => {
    const end = new Date();
    const start = new Date(end.getTime() - hours * 3_600_000);
    const query = `start=${start.toISOString()}&end=${end.toISOString()}`;
    return api<History>(`/telemetry/${deviceId}/history?${query}`);
  }, [deviceId, hours]);
  const unit = METRICS.find((item) => item.key === metric)!.unit;
  const title = `${t(`metric_${metric}`)}${unit ? ` (${unit})` : ""}`;

  return (
    <section className="card">
      <h2>
        {t("graph")}: {title}
      </h2>
      <div className="controls">
        <select
          aria-label={t("sensor")}
          value={metric}
          onChange={(event) => setMetric(event.target.value as MetricKey)}
        >
          {METRICS.map((item) => (
            <option key={item.key} value={item.key}>
              {t(`metric_${item.key}`)}
            </option>
          ))}
        </select>
        <select
          aria-label={t("time_range")}
          value={hours}
          onChange={(event) => setHours(Number(event.target.value))}
        >
          {RANGES.map((range) => (
            <option key={range.hours} value={range.hours}>
              {t(range.label)}
            </option>
          ))}
        </select>
      </div>
      <LoadState loading={loading} error={error} hasData={!!data} />
      {data && (
        <>
          <LineChart
            label={title}
            points={data.points.map((point) => ({
              time: new Date(point.ts).getTime(),
              value: point[metric],
            }))}
          />
          <p className="muted small">{t(`res_${data.resolution}`)}</p>
        </>
      )}
    </section>
  );
}

function Readings({ device }: { device: DeviceReading }) {
  const { t } = useI18n();
  return (
    <div className="readings">
      {METRICS.map((metric) => (
        <div key={metric.key} className="reading">
          <span className="muted small">{t(`metric_${metric.key}`)}</span>
          <b>
            {number(device.is_stale ? null : device[metric.key], metric.key === "ammonia" ? 2 : 1)}
          </b>
          <span className="muted small">{metric.unit || " "}</span>
        </div>
      ))}
    </div>
  );
}

export default function PondPage() {
  const { t, dateTime } = useI18n();
  const { id } = useParams<{ id: string }>();
  const { data: pond, error, loading } = usePolled(() => api<PondDetail>(`/ponds/${id}`), [id]);
  const [selected, setSelected] = useState<string>();
  const deviceId = selected ?? pond?.devices[0]?.device_id;

  return (
    <>
      <p className="small">
        <Link href="/" className="muted">
          {t("back_home")}
        </Link>
      </p>
      <LoadState loading={loading} error={error} hasData={!!pond} />
      {pond && (
        <>
          <header className="head">
            <h1>{pond.name}</h1>
            <StatusLabel status={pond.status} />
          </header>
          {pond.status === "SUBSCRIPTION_EXPIRED" && (
            <p className="banner">{t("plan_ended_text")}</p>
          )}
          {pond.devices.length > 0 ? (
            <>
              {pond.devices.map((device, index) => (
                <section key={device.device_id} className="card">
                  <div className="head compact">
                    <h2>
                      {pond.devices.length > 1 ? t("device_n", { n: index + 1 }) : t("latest")}
                    </h2>
                    {pond.devices.length > 1 && device.device_id !== deviceId && (
                      <button onClick={() => setSelected(device.device_id)}>{t("graph")}</button>
                    )}
                  </div>
                  <Readings device={device} />
                  <p className="muted small">
                    {t("updated", { time: dateTime(device.ts) })}
                    {device.is_stale && <span className="status nodata"> · ○ {t("no_recent")}</span>}
                  </p>
                </section>
              ))}
              {deviceId && <HistoryChart deviceId={deviceId} />}
            </>
          ) : (
            pond.status !== "SUBSCRIPTION_EXPIRED" && <p className="muted">{t("no_readings")}</p>
          )}
        </>
      )}
    </>
  );
}
