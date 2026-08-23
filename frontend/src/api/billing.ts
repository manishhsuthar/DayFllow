import { apiGet, apiPost } from "@/api/client";

export type SubscriptionStatus =
  | "trialing"
  | "active"
  | "past_due"
  | "canceled"
  | "unpaid"
  | "incomplete"
  | "incomplete_expired"
  | "paused";

export interface Plan {
  code: string;
  name: string;
  description: string;
  amount_cents: number;
  /** Major units as a decimal string, for display only. Never do arithmetic on this. */
  amount: string;
  price_display: string;
  currency: string;
  interval: "month" | "year";
  /** null means unlimited. */
  seat_limit: number | null;
  features: string[];
  is_default: boolean;
}

export interface PlansResponse {
  currency: string;
  trial_days: number;
  billing_enabled: boolean;
  publishable_key: string;
  plans: Plan[];
}

export interface Subscription {
  status: SubscriptionStatus;
  plan: Plan | null;
  is_entitled: boolean;
  seats_in_use: number;
  seat_limit: number | null;
  trial_end: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  canceled_at: string | null;
}

export const fetchPlans = () => apiGet("/billing/plans/") as Promise<PlansResponse>;

export const fetchSubscription = () =>
  apiGet("/billing/subscription/") as Promise<Subscription>;

/**
 * Ask the server for a Stripe Checkout session and hand the browser to Stripe.
 * The client never reports what was paid: that arrives by webhook (audit V-10).
 */
export const startCheckout = (planCode: string) =>
  apiPost("/billing/checkout/", { plan_code: planCode }) as Promise<{
    checkout_url: string;
    session_id: string;
  }>;

/** Stripe's hosted portal: payment method, invoices, cancellation. */
export const openBillingPortal = (returnUrl: string) =>
  apiPost("/billing/portal/", { return_url: returnUrl }) as Promise<{ portal_url: string }>;

export const formatMoney = (cents: number, currency = "usd") =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
    minimumFractionDigits: 2,
  }).format(cents / 100);

/** Salary and payroll amounts arrive as decimal strings. */
export const formatAmount = (value: string | number | null | undefined, currency = "USD") => {
  const numeric = typeof value === "number" ? value : Number.parseFloat(String(value ?? "0"));
  if (Number.isNaN(numeric)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(numeric);
};
