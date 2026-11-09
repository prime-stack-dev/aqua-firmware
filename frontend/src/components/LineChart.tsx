"use client";

import { useEffect, useRef, useState } from "react";
import { number } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

const PAD = { top: 12, right: 12, bottom: 28, left: 40 };

export interface ChartPoint {
  time: number;
  value: number | null;
}

/** Splits the line where data is missing, so a gap never looks like a reading. */
function segments(points: ChartPoint[]): ChartPoint[][] {
  const spacing = points.slice(1).map((point, i) => point.time - points[i].time);
  const typical = [...spacing].sort((a, b) => a - b)[Math.floor(spacing.length / 2)] ?? 0;
  const result: ChartPoint[][] = [];
  let current: ChartPoint[] = [];
  points.forEach((point, i) => {
    const gap = i > 0 && point.time - points[i - 1].time > typical * 3;
    if (point.value === null || gap) {
      if (current.length) result.push(current);
      current = [];
    }
    if (point.value !== null) current.push(point);
  });
  if (current.length) result.push(current);
  return result;
}

export function LineChart({ points, label }: { points: ChartPoint[]; label: string }) {
  const { t, locale } = useI18n();
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);

  // Drawn at the real screen width, so the text stays readable on a phone.
  useEffect(() => {
    if (!box.current) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) setWidth(Math.round(entry.contentRect.width));
    });
    observer.observe(box.current);
    return () => observer.disconnect();
  }, []);

  const valid = points.filter((point) => point.value !== null) as {
    time: number;
    value: number;
  }[];
  if (valid.length === 0) return <p className="muted">{t("no_chart")}</p>;

  const height = width < 500 ? 210 : 280;
  const values = valid.map((point) => point.value);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const margin = high === low ? 1 : (high - low) * 0.1;
  const yMin = low - margin;
  const yMax = high + margin;
  const start = valid[0].time;
  const end = valid[valid.length - 1].time;

  const x = (time: number) =>
    PAD.left +
    (end === start ? 0.5 : (time - start) / (end - start)) * (width - PAD.left - PAD.right);
  const y = (value: number) =>
    height - PAD.bottom - ((value - yMin) / (yMax - yMin)) * (height - PAD.top - PAD.bottom);
  const ticks = [0, 1, 2, 3].map((i) => yMin + ((yMax - yMin) * i) / 3);
  const timeLabel = (time: number) =>
    new Date(time).toLocaleString(locale, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });

  return (
    <div ref={box}>
      <svg
        className="chart"
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${label}: ${number(low)} – ${number(high)}`}
      >
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="grid" x1={PAD.left} x2={width - PAD.right} y1={y(tick)} y2={y(tick)} />
            <text className="axis" x={PAD.left - 8} y={y(tick) + 4} textAnchor="end">
              {number(tick)}
            </text>
          </g>
        ))}
        {segments(points).map((segment) =>
          segment.length === 1 ? (
            <circle
              key={segment[0].time}
              className="dot"
              cx={x(segment[0].time)}
              cy={y(segment[0].value as number)}
              r={3}
            />
          ) : (
            <polyline
              key={segment[0].time}
              className="line"
              points={segment.map((p) => `${x(p.time)},${y(p.value as number)}`).join(" ")}
            />
          ),
        )}
        <text className="axis" x={PAD.left} y={height - 8}>
          {timeLabel(start)}
        </text>
        <text className="axis" x={width - PAD.right} y={height - 8} textAnchor="end">
          {timeLabel(end)}
        </text>
      </svg>
    </div>
  );
}
