import { apiDownload, apiGet, apiPost, apiDelete } from "@/api/client";

export const fetchEmployees = async (scope?: "non_admin" | "employees_only") => {
  const query = scope ? `?scope=${scope}` : "";
  return apiGet(`/accounts/employees/${query}`);
};

export const createEmployee = async (payload: {
  first_name: string;
  last_name: string;
  email: string;
  role: "EMP" | "INT" | "HR";
  date_of_joining: string;
  department?: string;
  employment_type?: string;
  salary?: number;
}) => {
  return apiPost("/auth/create-employee/", payload);
};

export const exportEmployees = async (scope?: "non_admin" | "employees_only", role?: "HR" | "EMP" | "INT") => {
  const params = new URLSearchParams();
  if (scope) {
    params.set("scope", scope);
  }
  if (role) {
    params.set("role", role);
  }

  const query = params.toString();
  const path = query ? `/accounts/employees/export/?${query}` : "/accounts/employees/export/";
  return apiDownload(path);
};

export const deleteEmployee = async (employeeId: number) => {
  return apiDelete(`/accounts/employees/${employeeId}/`);
};
