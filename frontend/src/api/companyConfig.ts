import { apiGet, apiPut } from "@/api/client";

/** Company settings. Backed by the Organization model now, not CompanyConfig. */
export interface OrganizationSettings {
  name: string;
  slug: string;
  timezone: string;
  logo_url: string;
  departments: string[];
  roles: Array<"EMP" | "INT" | "HR">;
  employment_types: string[];
  bypass_attendance: boolean;
  updated_at: string | null;
}

export const fetchCompanyConfig = () =>
  apiGet("/accounts/company-config/") as Promise<OrganizationSettings>;

/**
 * Partial update. The server rejects removing a role or department that active
 * employees still hold (audit V-25), and requires an https logo URL (audit V-09).
 */
export const saveCompanyConfig = (payload: Partial<OrganizationSettings>) =>
  apiPut("/accounts/company-config/", payload) as Promise<OrganizationSettings>;

/** Kept as an alias so existing imports keep resolving. */
export type CompanyConfig = OrganizationSettings;
