"use client";

import { type FormEvent, useState } from "react";
import { LoadState } from "@/components/LoadState";
import { api, errorKey } from "@/lib/api";
import { isKnownMetric, METRICS } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { MessageKey } from "@/lib/messages";
import { useRole } from "@/lib/session";
import type { AlertRule, Farm, Pond } from "@/lib/types";
import { usePolled } from "@/lib/usePolled";

const OPERATORS: AlertRule["operator"][] = ["lt", "lte", "gt", "gte"];

function RuleRow({
  rule,
  scope,
  canEdit,
  onChanged,
  onError,
}: {
  rule: AlertRule;
  scope: string;
  canEdit: boolean;
  onChanged: () => Promise<void>;
  onError: (message: MessageKey | undefined) => void;
}) {
  const { t } = useI18n();
  const [threshold, setThreshold] = useState(String(rule.threshold));
  const editable = canEdit && rule.org_id !== null;

  async function run(path: string, init: RequestInit) {
    onError(undefined);
    try {
      await api(path, init);
      await onChanged();
    } catch (caught) {
      onError(errorKey(caught));
    }
  }

  const update = (body: object) =>
    run(`/alert-rules/${rule.id}`, { method: "PUT", body: JSON.stringify(body) });

  return (
    <tr>
      <td data-label={t("applies_to")}>{scope}</td>
      <td data-label={t("sensor")}>
        {isKnownMetric(rule.metric) ? t(`metric_${rule.metric}`) : rule.metric}
      </td>
      <td data-label={t("level")}>{t(`sev_${rule.severity}`)}</td>
      <td data-label={t("alert_when")}>
        {editable ? (
          <input
            className="threshold"
            type="number"
            step="any"
            aria-label={t("limit")}
            value={threshold}
            onChange={(event) => setThreshold(event.target.value)}
          />
        ) : (
          rule.threshold
        )}{" "}
        {t(`op_${rule.operator}`)}
      </td>
      <td data-label={t("status")}>{rule.enabled ? t("on") : t("off")}</td>
      <td data-label={t("action")}>
        {editable ? (
          <div className="actions">
            <button
              disabled={threshold === "" || Number(threshold) === rule.threshold}
              onClick={() => void update({ threshold: Number(threshold) })}
            >
              {t("save")}
            </button>
            <button onClick={() => void update({ enabled: !rule.enabled })}>
              {rule.enabled ? t("turn_off") : t("turn_on")}
            </button>
            <button
              className="danger"
              onClick={() => void run(`/alert-rules/${rule.id}`, { method: "DELETE" })}
            >
              {t("delete")}
            </button>
          </div>
        ) : (
          <span className="muted small">
            {rule.org_id === null ? t("default_rule") : t("owner_only")}
          </span>
        )}
      </td>
    </tr>
  );
}

function NewRuleForm({
  farms,
  ponds,
  onCreated,
}: {
  farms: Farm[];
  ponds: Pond[];
  onCreated: () => Promise<void>;
}) {
  const { t } = useI18n();
  const [metric, setMetric] = useState<string>(METRICS[0].key);
  const [operator, setOperator] = useState<AlertRule["operator"]>("lt");
  const [threshold, setThreshold] = useState("");
  const [severity, setSeverity] = useState("critical");
  const [scope, setScope] = useState("");
  const [error, setError] = useState<MessageKey>();
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    const [kind, id] = scope.split(":");
    try {
      await api("/alert-rules", {
        method: "POST",
        body: JSON.stringify({
          metric,
          operator,
          severity,
          threshold: Number(threshold),
          ...(kind === "farm" ? { farm_id: id } : {}),
          ...(kind === "pond" ? { pond_id: id } : {}),
        }),
      });
      setThreshold("");
      await onCreated();
    } catch (caught) {
      setError(errorKey(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>{t("add_limit_title")}</h2>
      <p className="muted small">{t("limit_help")}</p>
      {error && (
        <p className="banner" role="alert">
          {t(error)}
        </p>
      )}
      <form className="form" onSubmit={submit}>
        <label>
          {t("applies_to")}
          <select value={scope} onChange={(event) => setScope(event.target.value)}>
            <option value="">{t("whole_org")}</option>
            {farms.map((farm) => (
              <option key={farm.id} value={`farm:${farm.id}`}>
                {farm.name}
              </option>
            ))}
            {ponds.map((pond) => (
              <option key={pond.id} value={`pond:${pond.id}`}>
                {pond.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("sensor")}
          <select value={metric} onChange={(event) => setMetric(event.target.value)}>
            {METRICS.map((item) => (
              <option key={item.key} value={item.key}>
                {t(`metric_${item.key}`)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("limit")}
          <input
            className="threshold"
            type="number"
            step="any"
            required
            value={threshold}
            onChange={(event) => setThreshold(event.target.value)}
          />
        </label>
        <label>
          {t("alert_when")}
          <select
            value={operator}
            onChange={(event) => setOperator(event.target.value as AlertRule["operator"])}
          >
            {OPERATORS.map((value) => (
              <option key={value} value={value}>
                {t(`op_${value}`)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("level")}
          <select value={severity} onChange={(event) => setSeverity(event.target.value)}>
            <option value="critical">{t("sev_critical")}</option>
            <option value="low">{t("sev_low")}</option>
          </select>
        </label>
        <button className="primary" type="submit" disabled={busy}>
          {t("add_limit")}
        </button>
      </form>
    </section>
  );
}

export default function AlertRulesPage() {
  const { t } = useI18n();
  const isOwner = useRole() === "owner";
  const [actionError, setActionError] = useState<MessageKey>();
  const { data, error, loading, reload } = usePolled(async () => {
    const [rules, farms, ponds] = await Promise.all([
      api<AlertRule[]>("/alert-rules"),
      api<Farm[]>("/farms?limit=500"),
      api<Pond[]>("/ponds?limit=500"),
    ]);
    return { rules, farms, ponds };
  }, []);

  function scopeName(rule: AlertRule): string {
    if (rule.pond_id) return data?.ponds.find((pond) => pond.id === rule.pond_id)?.name ?? t("pond");
    if (rule.farm_id) return data?.farms.find((farm) => farm.id === rule.farm_id)?.name ?? t("farm");
    return rule.org_id ? t("whole_org") : t("default_rule");
  }

  return (
    <>
      <header className="head">
        <h1>{t("limits_title")}</h1>
      </header>
      <LoadState loading={loading} error={error} hasData={!!data} />
      {actionError && (
        <p className="banner" role="alert">
          {t(actionError)}
        </p>
      )}
      {data && (
        <>
          <section className="card">
            <div className="table-wrap">
              <table className="stack-table">
                <thead>
                  <tr>
                    <th scope="col">{t("applies_to")}</th>
                    <th scope="col">{t("sensor")}</th>
                    <th scope="col">{t("level")}</th>
                    <th scope="col">{t("alert_when")}</th>
                    <th scope="col">{t("status")}</th>
                    <th scope="col">{t("action")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rules.map((rule) => (
                    // The key includes the limit so a saved value resets the input.
                    <RuleRow
                      key={`${rule.id}-${rule.threshold}`}
                      rule={rule}
                      scope={scopeName(rule)}
                      canEdit={isOwner}
                      onChanged={reload}
                      onError={setActionError}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          {isOwner && <NewRuleForm farms={data.farms} ponds={data.ponds} onCreated={reload} />}
        </>
      )}
    </>
  );
}
