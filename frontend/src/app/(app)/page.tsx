"use client";

import Link from "next/link";
import { useState } from "react";
import { LoadState } from "@/components/LoadState";
import { StatusLabel } from "@/components/StatusLabel";
import { api } from "@/lib/api";
import { number, STATUS } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { Dashboard, Farm } from "@/lib/types";
import { usePolled } from "@/lib/usePolled";

// Most urgent first.
const ATTENTION = ["CRITICAL_ALERT", "NO_DATA", "LOW", "SUBSCRIPTION_EXPIRED"] as const;

function FarmDashboard({ farmId }: { farmId: string }) {
  const { t } = useI18n();
  const { data, error, loading } = usePolled(
    () => api<Dashboard>(`/farms/${farmId}/dashboard`),
    [farmId],
  );
  const needAttention = ATTENTION.flatMap((status) =>
    (data?.ponds ?? []).flatMap((pond) => (pond.status === status ? [{ pond, status }] : [])),
  );

  return (
    <>
      <LoadState loading={loading} error={error} hasData={!!data} />
      {data && (
        <>
          <section className="kpis" aria-label={t("home_title")}>
            <div className="kpi">
              <span className="muted small">{t("kpi_good")}</span>
              <b>
                {data.summary.ponds_in_range} / {data.summary.ponds_total}
              </b>
            </div>
            <div className="kpi">
              <span className="muted small">{t("kpi_attention")}</span>
              <b>{data.summary.ponds_total - data.summary.ponds_in_range}</b>
            </div>
            <div className="kpi">
              <span className="muted small">{t("kpi_alerts")}</span>
              <b>{data.summary.open_alerts}</b>
            </div>
          </section>

          <section className="card">
            <h2>{t("attention_title")}</h2>
            {needAttention.length === 0 ? (
              <p className="status ok">● {t("all_good")}</p>
            ) : (
              <ul className="attention">
                {needAttention.map(({ pond, status }) => (
                  <li key={pond.id}>
                    <Link href={`/ponds/${pond.id}`} className={`item ${STATUS[status].tone}`}>
                      <span className="item-head">
                        <b>{pond.name}</b>
                        <StatusLabel status={status} />
                      </span>
                      <span>
                        {t(`attention_${status}`)}
                        {pond.dissolved_oxygen !== null &&
                          ` ${t("metric_dissolved_oxygen")}: ${number(pond.dissolved_oxygen)} mg/L`}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card">
            <h2>{t("all_ponds")}</h2>
            {data.ponds.length === 0 && <p className="muted">{t("no_ponds")}</p>}
            <div className="ponds">
              {data.ponds.map((pond) => (
                <Link key={pond.id} href={`/ponds/${pond.id}`} className={`pond ${STATUS[pond.status].tone}`}>
                  <span className="pond-name">{pond.name}</span>
                  <b>{number(pond.dissolved_oxygen)}</b>
                  <StatusLabel status={pond.status} />
                </Link>
              ))}
            </div>
          </section>
        </>
      )}
    </>
  );
}

export default function DashboardPage() {
  const { t } = useI18n();
  const { data: farms, error, loading } = usePolled(() => api<Farm[]>("/farms?limit=500"), []);
  const [selected, setSelected] = useState<string>();
  const farmId = selected ?? farms?.[0]?.id;

  return (
    <>
      <header className="head">
        <h1>{t("home_title")}</h1>
        {farms && farms.length > 1 && (
          <select
            aria-label={t("farm")}
            value={farmId}
            onChange={(event) => setSelected(event.target.value)}
          >
            {farms.map((farm) => (
              <option key={farm.id} value={farm.id}>
                {farm.name}
              </option>
            ))}
          </select>
        )}
      </header>
      <LoadState loading={loading} error={error} hasData={!!farms} />
      {farms?.length === 0 && <p className="muted">{t("no_farms")}</p>}
      {farmId && <FarmDashboard farmId={farmId} />}
    </>
  );
}
