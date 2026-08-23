import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, ShieldCheck } from "lucide-react";
import { fetchAuditLog, type AuditEntry } from "@/api/audit";

const ACTION_FILTERS = [
  { value: "", label: "All activity" },
  { value: "SALARY_SET", label: "Salary changes" },
  { value: "PAYROLL_RUN", label: "Payroll runs" },
  { value: "PAYROLL_CREDITED", label: "Salary credits" },
  { value: "EXPENSE_APPROVED", label: "Expense approvals" },
  { value: "LEAVE_APPROVED", label: "Leave approvals" },
  { value: "EMPLOYEE_DEACTIVATED", label: "Deactivations" },
  { value: "SETTINGS_CHANGED", label: "Settings changes" },
  { value: "SUBSCRIPTION_CHANGED", label: "Subscription changes" },
];

const renderChange = (key: string, value: unknown) => {
  if (value && typeof value === "object" && ("from" in value || "to" in value)) {
    const { from, to } = value as { from?: unknown; to?: unknown };
    return (
      <span key={key} className="mr-3 inline-block">
        <span className="text-muted-foreground">{key}:</span>{" "}
        <span className="line-through opacity-60">{String(from ?? "—")}</span>{" "}
        <span aria-hidden>→</span> <span className="font-medium">{String(to ?? "—")}</span>
      </span>
    );
  }
  return (
    <span key={key} className="mr-3 inline-block">
      <span className="text-muted-foreground">{key}:</span>{" "}
      <span className="font-medium">{String(value)}</span>
    </span>
  );
};

/** The append-only trail of privileged and financial actions (audit V-30). */
const AuditLog: React.FC = () => {
  const [action, setAction] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["audit-log", action],
    queryFn: () => fetchAuditLog(action ? { action } : undefined),
  });

  return (
    <div className="p-6 md:p-10">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-3xl font-bold text-foreground">
            <ShieldCheck className="text-primary" /> Audit trail
          </h1>
          <p className="mt-1 text-muted-foreground">
            Every salary change, payroll run, credit and approval, with who did it and what
            changed. Entries cannot be edited or deleted.
          </p>
        </div>

        <select
          value={action}
          onChange={(event) => setAction(event.target.value)}
          className="rounded-xl border border-input bg-background px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
        >
          {ACTION_FILTERS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </header>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : !data?.length ? (
        <p className="rounded-2xl border border-dashed border-border py-16 text-center text-muted-foreground">
          Nothing recorded yet.
        </p>
      ) : (
        <ol className="space-y-3">
          {data.map((entry: AuditEntry) => (
            <li
              key={entry.id}
              className="rounded-2xl border border-border bg-card p-4 shadow-soft"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-semibold text-foreground">
                  {entry.action_label}
                  {entry.target_label ? (
                    <span className="font-normal text-muted-foreground"> · {entry.target_label}</span>
                  ) : null}
                </p>
                <time className="text-xs text-muted-foreground">
                  {new Date(entry.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
                </time>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                by {entry.actor_label || "system"}
              </p>
              {entry.changes && Object.keys(entry.changes).length ? (
                <p className="mt-2 text-xs text-foreground">
                  {Object.entries(entry.changes).map(([key, value]) => renderChange(key, value))}
                </p>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
};

export default AuditLog;
