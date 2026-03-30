import { Card, CardContent } from "@heroui/react";

interface MetricTileProps {
  label: string;
  value: string | number;
  accent?: string;
}

export function MetricTile(props: MetricTileProps) {
  return (
    <Card className="border border-[var(--border-1)] bg-[linear-gradient(180deg,rgba(20,26,46,0.92),rgba(14,19,34,0.85))]">
      <CardContent className="gap-1.5 px-4 py-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.26em] text-[var(--text-3)]">
          {props.label}
        </p>
        <p className={["text-2xl font-semibold leading-none text-white", props.accent ?? ""].join(" ").trim()}>
          {props.value}
        </p>
      </CardContent>
    </Card>
  );
}
