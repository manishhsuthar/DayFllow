import { apiGet, unwrapList } from "@/api/client";

export interface AuditEntry {
  id: number;
  action: string;
  action_label: string;
  actor_label: string;
  target_type: string;
  target_id: string;
  target_label: string;
  changes: Record<string, { from?: unknown; to?: unknown } | unknown>;
  created_at: string;
}

/** Organization owner only. Append-only server-side (audit V-30). */
export const fetchAuditLog = async (filters?: { action?: string; actor?: string }) => {
  const params = new URLSearchParams({ page_size: "100" });
  if (filters?.action) params.set("action", filters.action);
  if (filters?.actor) params.set("actor", filters.actor);
  return unwrapList<AuditEntry>(await apiGet(`/audit/?${params.toString()}`));
};
