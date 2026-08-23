import { apiGet, apiPost, unwrapList } from "@/api/client";
import type { Role } from "@/api/auth";

export type AttendanceStatus = "PRESENT" | "HALF_DAY" | "ABSENT" | "LEAVE";

export interface AttendanceRecord {
  id: number;
  user: number;
  date: string;
  check_in: string | null;
  check_out: string | null;
  total_hours: number;
  status: AttendanceStatus;
  created_at: string;
}

export interface AttendanceListRecord extends AttendanceRecord {
  user_login_id: string;
  user_name: string;
  user_role: Role;
}

interface RangeOptions {
  startDate?: string;
  endDate?: string;
  employeeId?: number;
  status?: AttendanceStatus;
}

/**
 * History is bounded server-side: a 90-day default window and a 366-day maximum
 * (audit V-28). Pass an explicit range to look further back.
 */
const rangeParams = (options?: RangeOptions) => {
  const params = new URLSearchParams({ page_size: "200" });
  if (options?.startDate) params.set("start_date", options.startDate);
  if (options?.endDate) params.set("end_date", options.endDate);
  if (options?.employeeId) params.set("employee_id", String(options.employeeId));
  if (options?.status) params.set("status", options.status);
  return params.toString();
};

export const fetchMyAttendance = async (options?: RangeOptions) =>
  unwrapList<AttendanceRecord>(await apiGet(`/attendance/my/?${rangeParams(options)}`));

export const fetchAllAttendance = async (options?: RangeOptions) =>
  unwrapList<AttendanceListRecord>(await apiGet(`/attendance/all/?${rangeParams(options)}`));

export const checkInAttendance = () =>
  apiPost("/attendance/check-in/", {}) as Promise<{ detail: string; check_in: string }>;

export const checkOutAttendance = () =>
  apiPost("/attendance/check-out/", {}) as Promise<{
    detail: string;
    check_out: string;
    total_hours: number;
    status: AttendanceStatus;
  }>;
