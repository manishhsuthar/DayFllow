import { apiGet, apiPut } from "@/api/client";

export interface CompanyConfig {
  company_name: string;
  departments: string[];
  roles: Array<"EMP" | "INT" | "HR">;
  employment_types: string[];
  logo_url: string;
  bypass_attendance?: boolean;
  updated_at: string | null;
}

export const fetchCompanyConfig = async () => {
  return apiGet("/accounts/company-config/") as Promise<CompanyConfig>;
};

export const saveCompanyConfig = async (payload: {
  departments: string[];
  roles: string[];
  employment_types: string[];
  logo_url: string;
  bypass_attendance?: boolean;
}) => {
  return apiPut("/accounts/company-config/", payload) as Promise<CompanyConfig>;
};
