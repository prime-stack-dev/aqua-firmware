"use client";

import { STATUS } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { PondStatus } from "@/lib/types";

export function StatusLabel({ status }: { status: PondStatus }) {
  const { t } = useI18n();
  const { symbol, tone } = STATUS[status];
  return (
    <span className={`status ${tone}`}>
      {symbol} {t(`status_${status}`)}
    </span>
  );
}
