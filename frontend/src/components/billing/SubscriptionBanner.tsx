import React from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CreditCard } from "lucide-react";
import { fetchSubscription } from "@/api/billing";
import { useAuth } from "@/contexts/AuthContext";

const dayCount = (iso: string | null) => {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  return Math.max(0, Math.ceil(ms / 86_400_000));
};

/**
 * Tells people what state their subscription is in before they hit a 403.
 *
 * A lapsed subscription blocks creating new work but never blocks reading or
 * reaching billing, so this is a banner rather than a wall (audit V-10).
 */
export const SubscriptionBanner: React.FC = () => {
  const { isAuthenticated, isOwner } = useAuth();
  const { data } = useQuery({
    queryKey: ["subscription"],
    queryFn: fetchSubscription,
    enabled: isAuthenticated,
    staleTime: 60_000,
  });

  if (!data) return null;

  const trialDaysLeft = data.status === "trialing" ? dayCount(data.trial_end) : null;
  const seatsLeft =
    data.seat_limit === null ? null : Math.max(0, data.seat_limit - data.seats_in_use);

  let tone: "warning" | "danger" | "info" | null = null;
  let message: React.ReactNode = null;

  if (!data.is_entitled) {
    tone = "danger";
    message =
      data.status === "trialing"
        ? "Your free trial has ended. Choose a plan to keep adding employees and running payroll."
        : "Your subscription is not active. Your data is safe and readable, but new records cannot be created.";
  } else if (data.status === "past_due") {
    tone = "warning";
    message = "Your last payment failed. Update your payment method to avoid interruption.";
  } else if (trialDaysLeft !== null && trialDaysLeft <= 5) {
    tone = "warning";
    message = `${trialDaysLeft} day${trialDaysLeft === 1 ? "" : "s"} left in your free trial.`;
  } else if (data.cancel_at_period_end) {
    tone = "info";
    message = "Your subscription is set to cancel at the end of the current period.";
  } else if (seatsLeft !== null && seatsLeft === 0) {
    tone = "warning";
    message = `All ${data.seat_limit} seats on ${data.plan?.name ?? "your plan"} are in use.`;
  }

  if (!message) return null;

  const styles = {
    danger: "bg-destructive/10 text-destructive border-destructive/30",
    warning: "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-400",
    info: "bg-primary/10 text-primary border-primary/30",
  }[tone!];

  return (
    <div className={`flex items-center justify-between gap-4 border-b px-6 py-3 text-sm ${styles}`}>
      <span className="flex items-center gap-2">
        <AlertTriangle size={16} className="shrink-0" />
        {message}
      </span>
      {isOwner ? (
        <Link
          to="/billing"
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-current/10 px-3 py-1.5 font-semibold hover:bg-current/20"
        >
          <CreditCard size={14} />
          Manage billing
        </Link>
      ) : null}
    </div>
  );
};

export default SubscriptionBanner;
