"use client";

import Link from "next/link";
import { LoadState } from "@/components/LoadState";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Device, Pond } from "@/lib/types";
import { usePolled } from "@/lib/usePolled";

export default function DevicesPage() {
  const { t, dateTime } = useI18n();
  const { data, error, loading } = usePolled(async () => {
    const [devices, ponds] = await Promise.all([
      api<Device[]>("/devices?limit=500"),
      api<Pond[]>("/ponds?limit=500"),
    ]);
    return { devices, pondNames: new Map(ponds.map((pond) => [pond.id, pond.name])) };
  }, []);

  return (
    <>
      <header className="head">
        <h1>{t("devices_title")}</h1>
      </header>
      <LoadState loading={loading} error={error} hasData={!!data} />
      {data && (
        <section className="card">
          {data.devices.length === 0 ? (
            <p className="muted">{t("no_devices")}</p>
          ) : (
            <div className="table-wrap">
              <table className="stack-table">
                <thead>
                  <tr>
                    <th scope="col">{t("device_serial")}</th>
                    <th scope="col">{t("name")}</th>
                    <th scope="col">{t("pond")}</th>
                    <th scope="col">{t("last_reading")}</th>
                    <th scope="col">{t("access")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.devices.map((device) => (
                    <tr key={device.id}>
                      <td data-label={t("device_serial")}>{device.serial}</td>
                      <td data-label={t("name")}>{device.name ?? "—"}</td>
                      <td data-label={t("pond")}>
                        {device.pond_id ? (
                          <Link href={`/ponds/${device.pond_id}`}>
                            {data.pondNames.get(device.pond_id) ?? t("pond")}
                          </Link>
                        ) : (
                          t("not_assigned")
                        )}
                      </td>
                      <td data-label={t("last_reading")}>{dateTime(device.last_reading_at)}</td>
                      <td data-label={t("access")}>
                        <span className={`status ${device.has_access ? "ok" : "nodata"}`}>
                          {device.has_access ? `● ${t("access_active")}` : `✕ ${t("access_ended")}`}
                        </span>
                      </td>
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
