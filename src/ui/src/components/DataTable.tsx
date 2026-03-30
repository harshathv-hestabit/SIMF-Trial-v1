import { Chip } from "@heroui/react";
import type { ReactNode } from "react";

interface Column<T> {
  key: string;
  header: string;
  align?: "left" | "right";
  cell: (row: T) => ReactNode;
}

interface DataTableProps<T> {
  columns: Array<Column<T>>;
  rows: T[];
  emptyMessage: string;
  ariaLabel?: string;
  getRowKey?: (row: T, index: number) => string;
}

export function DataTable<T>(props: DataTableProps<T>) {
  if (props.rows.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-[var(--border-1)] bg-[rgba(255,255,255,0.03)] p-6 text-sm text-[var(--text-3)]">
        {props.emptyMessage}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--border-1)] bg-[rgba(255,255,255,0.03)]">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse" aria-label={props.ariaLabel ?? "Data table"}>
          <thead className="bg-[rgba(115,166,255,0.08)]">
            <tr>
              {props.columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={[
                    "border-b border-[var(--border-1)] px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-3)]",
                    column.align === "right" ? "text-right" : "text-left",
                  ].join(" ")}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row, rowIndex) => (
              <tr
                key={props.getRowKey?.(row, rowIndex) ?? String(rowIndex)}
                className="border-b border-[var(--border-1)] last:border-b-0 odd:bg-[rgba(255,255,255,0.025)]"
              >
                {props.columns.map((column, columnIndex) => {
                  const cell = (
                    <div
                      className={[
                        "text-sm text-[var(--text-2)]",
                        column.align === "right" ? "text-right" : "text-left",
                      ].join(" ")}
                    >
                      {column.cell(row)}
                    </div>
                  );

                  if (columnIndex === 0) {
                    return (
                      <th key={column.key} scope="row" className="px-4 py-4 font-medium">
                        {cell}
                      </th>
                    );
                  }

                  return (
                    <td key={column.key} className="px-4 py-4 align-top">
                      {cell}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function StatusChip(props: { value: string }) {
  const value = props.value.toLowerCase();
  const tone =
    value === "failed"
      ? "danger"
      : value === "stored" || value === "saved" || value === "success"
        ? "success"
        : value === "pending" || value === "queued"
          ? "warning"
          : "default";

  return (
    <Chip size="sm" variant="soft" color={tone}>
      {props.value}
    </Chip>
  );
}
