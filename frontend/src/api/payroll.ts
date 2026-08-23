import { apiGet, apiPost, apiDownload } from "@/api/client";

export interface SalaryRecord {
  employee_id: number;
  employee_login_id: string;
  employee_name: string;
  employee_role: "ADMIN" | "HR" | "EMP" | "INT";
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
  employee_role: "ADMIN" | "HR" | "EMP" | "INT";
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
  expense_amount: string;
  net_salary: string;
  created_at: string;
  credited_at: string | null;

}

export interface PayrollSlip {
  id: number;
  company_name: string;
  company_logo_url: string;
  month: string;
  month_label: string;
  employee: {
    id: number;
    login_id: string;
    name: string;
    email: string;
    department: string;
    employment_type: string;
    role: "ADMIN" | "HR" | "EMP" | "INT";
  };
  status: "PENDING" | "PAID";
  total_days_in_month: number;
  attendance_entries: number;
  present_days: number;
  half_days: number;
  leave_days: number;
  absent_days: number;
  payable_days: string;
  designated_salary: string;
  expense_amount: string;
  net_salary: string;
  created_at: string;
  credited_at: string | null;

}

export interface PayrollRunResult {
  employee_id: number;
  employee_login_id: string;
  status: "generated" | "updated" | "skipped";
  net_salary?: string;
  reason?: string;
}

export interface PayrollRunResponse {
  month: string;
  results: PayrollRunResult[];
}

export const fetchSalaryRecords = async () => {
  return apiGet("/payroll/salaries/") as Promise<SalaryRecord[] | SalaryRecord>;
};

export const upsertSalary = async (payload: {
  employee_id: number;
  monthly_salary: string;
  currency: string;
}) => {
  return apiPost("/payroll/salaries/", payload) as Promise<{
    message: string;
    salary: SalaryRecord;
  }>;
};

export const runPayroll = async (payload: {
  month: string;
  employee_id?: number;
  force_recompute?: boolean;
}) => {
  return apiPost("/payroll/run/", payload) as Promise<PayrollRunResponse>;
};

export const fetchPayrollRecords = async (filters?: {
  month?: string;
  status?: "PENDING" | "PAID";
  employee_id?: number;
}) => {
  const params = new URLSearchParams();
  if (filters?.month) params.set("month", filters.month);
  if (filters?.status) params.set("status", filters.status);
  if (typeof filters?.employee_id === "number") {
    params.set("employee_id", String(filters.employee_id));
  }

  const query = params.toString();
  return apiGet(`/payroll/records/${query ? `?${query}` : ""}`) as Promise<PayrollRecord[]>;
};

export const creditPayroll = async (payrollId: number) => {
  return apiPost(`/payroll/records/${payrollId}/credit/`, {}) as Promise<{
    message: string;
    payroll: PayrollRecord;
  }>;
};

export const fetchPayrollSlip = async (payrollId: number) => {
  return apiGet(`/payroll/slips/${payrollId}/`) as Promise<PayrollSlip>;
};

export const downloadPayrollSlip = async (payrollId: number) => {
  return apiDownload(`/payroll/slips/${payrollId}/html/?download=true`);
};

export const addExpense = async (payload: {
  amount: string;
  employee_id?: number;
}) => {
  return apiPost("/payroll/salaries/add-expense/", payload) as Promise<{
    message: string;
    salary: SalaryRecord;
  }>;
};


