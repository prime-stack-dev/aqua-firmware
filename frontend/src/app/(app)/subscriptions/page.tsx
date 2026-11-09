"use client";

import { LoadState } from "@/components/LoadState";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Device, Subscription } from "@/lib/types";
import { usePolled } from "@/lib/usePolled";

const STATE_TONE: Record<Subscription["state"], string> = {
  active: "ok",
  grace: "low",
  pending: "nodata",
  expired: "critical",
  canceled: "nodata",
};

export default function SubscriptionsPage() {
  const { t, dateTime } = useI18n();
  const { data, error, loading } = usePolled(async () => {
    const [subscriptions, devices] = await Promise.all([
      api<Subscription[]>("/subscriptions?limit=500"),
      api<Device[]>("/devices?limit=500"),
    ]);
    return {
      subscriptions,
      deviceNames: new Map(devices.map((device) => [device.id, device.serial])),
    };
  }, []);

  return (
    <>
      <header className="head">
        <h1>{t("plans_title")}</h1>
      </header>
      <LoadState loading={loading} error={error} hasData={!!data} />
      {data && (
        <section className="card">
          {data.subscriptions.length === 0 ? (
            <p className="muted">{t("no_plans")}</p>
          ) : (
            <div className="table-wrap">
              <table className="stack-table">
                <thead>
                  <tr>
                    <th scope="col">{t("device")}</th>
                    <th scope="col">{t("plan")}</th>
                    <th scope="col">{t("plan_state")}</th>
                    <th scope="col">{t("starts")}</th>
                    <th scope="col">{t("ends")}</th>
                    <th scope="col">{t("access_until")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.subscriptions.map((subscription) => (
                    <tr key={subscription.id}>
                      <td data-label={t("device")}>
                        {data.deviceNames.get(subscription.device_id) ?? "—"}
                      </td>
                      <td data-label={t("plan")}>{subscription.plan_name}</td>
                      <td data-label={t("plan_state")}>
                        <span className={`status ${STATE_TONE[subscription.state]}`}>
                          {t(`sub_${subscription.state}`)}
                        </span>
                      </td>
                      <td data-label={t("starts")}>{dateTime(subscription.starts_at)}</td>
                      <td data-label={t("ends")}>{dateTime(subscription.ends_at)}</td>
                      <td data-label={t("access_until")}>{dateTime(subscription.access_until)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </>
  );
}
