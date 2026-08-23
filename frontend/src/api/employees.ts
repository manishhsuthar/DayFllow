import { apiDelete, apiDownload, apiGet, apiPost, unwrapList } from "@/api/client";
import type { Role } from "@/api/auth";

export interface Employee {
  id: number;
  login_id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  organization_name: string;
  role: Role;
  date_of_joining: string;
  department: string;
  employment_type: string;
  is_active: boolean;
  is_approved: boolean;
  // `salary` is deliberately absent: the directory no longer carries
  // compensation data (audit V-18). Use the payroll endpoints.
}

type Scope = "non_admin" | "employees_only";

interface EmployeeQuery {
  scope?: Scope;
  role?: Role;
  includeInactive?: boolean;
}

/** Accepts a bare scope string as well as an options object. */
const asQuery = (input?: Scope | EmployeeQuery): EmployeeQuery =>
  typeof input === "string" ? { scope: input } : (input ?? {});

export const fetchEmployees = async (input?: Scope | EmployeeQuery) => {
  const options = asQuery(input);
  const params = new URLSearchParams();
  if (options?.scope) params.set("scope", options.scope);
  if (options?.role) params.set("role", options.role);
  if (options?.includeInactive) params.set("include_inactive", "true");
  params.set("page_size", "200");

  const payload = await apiGet(`/accounts/employees/?${params.toString()}`);
  return unwrapList<Employee>(payload);
};

export const createEmployee = (payload: {
  first_name: string;
  last_name: string;
  email: string;
  role: "EMP" | "INT" | "HR";
  date_of_joining: string;
  department?: string;
  employment_type?: string;
}) =>
  apiPost("/auth/create-employee/", payload) as Promise<{
    login_id: string;
    temporary_password: string;
    message: string;
  }>;

export const exportEmployees = (input?: Scope | EmployeeQuery, role?: Role) => {
  const options = { ...asQuery(input), ...(role ? { role } : {}) };
  const params = new URLSearchParams();
  if (options?.scope) params.set("scope", options.scope);
  if (options?.role) params.set("role", options.role);
  const query = params.toString();
  return apiDownload(`/accounts/employees/export/${query ? `?${query}` : ""}`);
};

/** Deactivates. Records are retained for payroll history (audit V-16). */
export const deactivateEmployee = (employeeId: number) =>
  apiDelete(`/accounts/employees/${employeeId}/`);

export const reactivateEmployee = (employeeId: number) =>
  apiPost(`/accounts/employees/${employeeId}/reactivate/`, {});

/**
 * Alias for the old name. It no longer destroys anything: the record and all its
 * payroll history are retained, and the employee is marked inactive (audit V-16).
 */
export const deleteEmployee = deactivateEmployee;
