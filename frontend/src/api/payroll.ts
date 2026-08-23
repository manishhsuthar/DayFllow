import { apiGet, apiPost, apiDownload, unwrapList } from "@/api/client";
import type { Role } from "@/api/auth";

export interface SalaryRecord {
  employee_id: number;
  employee_login_id: string;
  employee_name: string;
  employee_role: Role;
  monthly_salary: string;
  currency: string;
  expense: string;
  outstanding: string;
  adjusted_salary: string;
  updated_at: string;
}

export interface PayrollRecord {
  id: number;
  employee_id: number;
  employee_login_id: string;
  employee_name: string;
  employee_role: Role;
  month: string;
  month_label: string;
  status: "PENDING" | "PAID";
  total_days_in_month: number;
  attendance_entries: number;
  present_days: number;
  half_days: number;
  leave_days: number;
  absent_days: number;
  payable_days: string;
  designated_salary: string;
  /** Earned before expense recovery. */
  gross_salary: string;
  /** Recovered this period. Capped so net pay never goes negative (audit V-08). */
  expense_amount: string;
  /** Left to recover in later periods. */
  expense_carried_forward: string;
  net_salary: string;
  currency: string;
  revision: number;
  created_at: string;
  credited_at: string | null;
}

export interface PayrollSlip extends Omit<PayrollRecord, "employee_id" | "employee_login_id" | "employee_name" | "employee_role"> {
  company_name: string;
  company_logo_url: string;
  employee: {
    id: number;
    login_id: string;
    name: string;
    email: string;
    department: string;
    employment_type: string;
    role: Role;
  };
}

export interface PayrollRunResult {
  employee_id: number;
  employee_login_id: string;
  status: "generated" | "recomputed";
  net_salary: string;
  expense_carried_forward: string;
  revision: number;
}

export interface PayrollRunSkip {
  employee_id: number;
  employee_login_id: string;
  /** `already_paid` is never overridden, even with force_recompute (audit V-20). */
  reason: "already_paid" | "already_generated";
  credited_at?: string;
  hint?: string;
}

export interface PayrollRunResponse {
  month: string;
  results: PayrollRunResult[];
  skipped: PayrollRunSkip[];
}

export type ExpenseStatus = "PENDING" | "APPROVED" | "REJECTED";

export interface ExpenseClaim {
  id: number;
  employee: number;
  employee_login_id: string;
  employee_name: string;
  amount: string;
  description: string;
  incurred_on: string;
  status: ExpenseStatus;
  review_note: string;
  reviewed_by_login_id: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export const fetchSalaryRecords = async () => {
  const payload = await apiGet("/payroll/salaries/");
  // Managers get a list; an employee gets their own single record.
  return Array.isArray(payload) ? (payload as SalaryRecord[]) : [payload as SalaryRecord];
};

/** Owner only, and audited with before/after values. */
export const upsertSalary = (payload: {
  employee_id: number;
  monthly_salary: string;
  /** Ignored: the platform is USD-only. Accepted so old callers still compile. */
  currency?: string;
}) =>
  apiPost("/payroll/salaries/", { ...payload, currency: "USD" }) as Promise<{
    message: string;
    salary: SalaryRecord;
  }>;

export const runPayroll = (payload: {
  month: string;
  employee_id?: number;
  force_recompute?: boolean;
}) => apiPost("/payroll/run/", payload) as Promise<PayrollRunResponse>;

export const fetchPayrollRecords = async (filters?: {
  month?: string;
  status?: "PENDING" | "PAID";
  employee_id?: number;
}) => {
  const params = new URLSearchParams({ page_size: "200" });
  if (filters?.month) params.set("month", filters.month);
  if (filters?.status) params.set("status", filters.status);
  if (typeof filters?.employee_id === "number") {
    params.set("employee_id", String(filters.employee_id));
  }
  return unwrapList<PayrollRecord>(await apiGet(`/payroll/records/?${params.toString()}`));
};

/** Owner only. A credited payslip is immutable afterwards (audit V-20). */
export const creditPayroll = (payrollId: number) =>
  apiPost(`/payroll/records/${payrollId}/credit/`, {}) as Promise<{
    message: string;
    payroll: PayrollRecord;
  }>;

export const fetchPayrollSlip = (payrollId: number) =>
  apiGet(`/payroll/slips/${payrollId}/`) as Promise<PayrollSlip>;

export const downloadPayrollSlip = (payrollId: number) =>
  apiDownload(`/payroll/slips/${payrollId}/html/?download=true`);

// ---------------------------------------------------------------------------
// Expense claims
// ---------------------------------------------------------------------------
// Submitting no longer moves money. The old endpoint wrote straight into the
// employee's outstanding balance with no review at all (audit V-07).

export const fetchExpenseClaims = async (filters?: {
  status?: ExpenseStatus;
  employee_id?: number;
}) => {
  const params = new URLSearchParams({ page_size: "200" });
  if (filters?.status) params.set("status", filters.status);
  if (filters?.employee_id) params.set("employee_id", String(filters.employee_id));
  return unwrapList<ExpenseClaim>(await apiGet(`/payroll/expenses/?${params.toString()}`));
};

export const submitExpenseClaim = (payload: {
  amount: string;
  description: string;
  incurred_on: string;
  employee_id?: number;
}) => apiPost("/payroll/expenses/", payload) as Promise<ExpenseClaim>;

/** Approval is the only thing that changes an outstanding balance. */
/**
 * Back-compat shim for the old `addExpense` call.
 *
 * The old endpoint moved money immediately with no review. This submits a claim
 * instead, so an approver still has to act on it (audit V-07).
 */
export const addExpense = (payload: {
  amount: string;
  employee_id?: number;
  description?: string;
  incurred_on?: string;
}) =>
  submitExpenseClaim({
    amount: payload.amount,
    description: payload.description ?? "Expense",
    incurred_on: payload.incurred_on ?? new Date().toISOString().slice(0, 10),
    employee_id: payload.employee_id,
  });

export const reviewExpenseClaim = (
  claimId: number,
  action: "APPROVE" | "REJECT",
  note?: string,
) => apiPost(`/payroll/expenses/${claimId}/review/`, { action, note }) as Promise<ExpenseClaim>;
