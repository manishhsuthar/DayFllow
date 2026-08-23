import { apiGet, apiPost, unwrapList } from "@/api/client";
import type { Role } from "@/api/auth";

export type LeaveType = "CASUAL" | "SICK" | "PAID";
export type LeaveStatus = "PENDING" | "APPROVED" | "REJECTED";

export interface LeaveRequestResponse {
  id: number;
  user: number;
  user_name: string;
  user_role: Role | null;
  leave_type: LeaveType;
  start_date: string;
  end_date: string;
  total_days: number;
  reason: string;
  status: LeaveStatus;
  created_at: string;
}

export interface ApplyLeavePayload {
  leave_type: LeaveType;
  start_date: string;
  end_date: string;
  reason: string;
}

/** A single request may not exceed this; enforced server-side too (audit V-05). */
export const MAX_LEAVE_DAYS = 90;
export const MAX_BACKDATE_DAYS = 30;

export const fetchMyLeaves = async (status?: LeaveStatus) => {
  const query = status ? `?status=${status}&page_size=200` : "?page_size=200";
  return unwrapList<LeaveRequestResponse>(await apiGet(`/leave/my/${query}`));
};

export const fetchAllLeaves = async (options?: { status?: LeaveStatus; employeeId?: number }) => {
  const params = new URLSearchParams({ page_size: "200" });
  if (options?.status) params.set("status", options.status);
  if (options?.employeeId) params.set("employee_id", String(options.employeeId));
  return unwrapList<LeaveRequestResponse>(await apiGet(`/leave/all/?${params.toString()}`));
};

export const applyLeaveRequest = (payload: ApplyLeavePayload) =>
  apiPost("/leave/apply/", payload);

export const reviewLeaveRequest = (leaveId: number, action: "APPROVE" | "REJECT") =>
  apiPost(`/leave/action/${leaveId}/`, { action });
