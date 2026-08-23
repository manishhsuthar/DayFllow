import React from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CreditCard, ExternalLink, Loader2, Users } from "lucide-react";
import {
  fetchPlans,
  fetchSubscription,
  openBillingPortal,
  startCheckout,
  type Plan,
} from "@/api/billing";
import { useToast } from "@/hooks/use-toast";

const STATUS_COPY: Record<string, { label: string; tone: string }> = {
  trialing: { label: "Free trial", tone: "bg-primary/10 text-primary" },
  active: { label: "Active", tone: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
  past_due: { label: "Payment failed", tone: "bg-amber-500/10 text-amber-700 dark:text-amber-400" },
  canceled: { label: "Cancelled", tone: "bg-destructive/10 text-destructive" },
  unpaid: { label: "Unpaid", tone: "bg-destructive/10 text-destructive" },
  incomplete: { label: "Incomplete", tone: "bg-muted text-muted-foreground" },
  incomplete_expired: { label: "Expired", tone: "bg-destructive/10 text-destructive" },
  paused: { label: "Paused", tone: "bg-muted text-muted-foreground" },
};

const formatDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" }) : "—";

const Billing: React.FC = () => {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();

  const subscription = useQuery({ queryKey: ["subscription"], queryFn: fetchSubscription });
  const plans = useQuery({ queryKey: ["plans"], queryFn: fetchPlans });

  // Stripe redirects back here after Checkout. The subscription itself is
  // updated by webhook, not by this redirect, so refetch rather than assume.
  React.useEffect(() => {
    const outcome = searchParams.get("checkout");
    if (!outcome) return;

    if (outcome === "success") {
      toast({
        title: "Payment received",
        description: "Your subscription is being activated. This can take a few seconds.",
      });
      // The webhook may land a moment after the redirect.
      const timers = [1000, 3000, 6000].map((delay) =>
        window.setTimeout(
          () => queryClient.invalidateQueries({ queryKey: ["subscription"] }),
          delay,
        ),
      );
      searchParams.delete("checkout");
      setSearchParams(searchParams, { replace: true });
      return () => timers.forEach(window.clearTimeout);
    }

    toast({ title: "Checkout cancelled", description: "No charge was made." });
    searchParams.delete("checkout");
    setSearchParams(searchParams, { replace: true });
  }, [searchParams, setSearchParams, toast, queryClient]);

  const checkout = useMutation({
    mutationFn: (planCode: string) => startCheckout(planCode),
    onSuccess: ({ checkout_url }) => {
      window.location.href = checkout_url;
    },
    onError: (error: any) =>
      toast({
        title: "Could not start checkout",
        description: error?.message ?? "Please try again.",
        variant: "destructive",
      }),
  });

  const portal = useMutation({
    mutationFn: () => openBillingPortal(`${window.location.origin}${window.location.pathname}#/billing`),
    onSuccess: ({ portal_url }) => {
      window.location.href = portal_url;
    },
    onError: (error: any) =>
      toast({
        title: "Could not open the billing portal",
        description: error?.message ?? "Please try again.",
        variant: "destructive",
      }),
  });

  if (subscription.isLoading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  const current = subscription.data;
  const status = current ? STATUS_COPY[current.status] ?? STATUS_COPY.incomplete : null;
  const seatLabel =
    current?.seat_limit === null
      ? `${current?.seats_in_use ?? 0} employees (unlimited)`
      : `${current?.seats_in_use ?? 0} of ${current?.seat_limit ?? 0} seats used`;

  return (
    <div className="p-6 md:p-10">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-foreground">Billing</h1>
        <p className="mt-1 text-muted-foreground">
          Manage your DayFlow subscription, payment method and invoices.
        </p>
      </header>

      <section className="mb-10 rounded-2xl border border-border bg-card p-6 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-semibold text-foreground">
                {current?.plan?.name ?? "No plan selected"}
              </h2>
              {status ? (
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${status.tone}`}>
                  {status.label}
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-muted-foreground">
              {current?.plan
                ? `${current.plan.price_display} per ${current.plan.interval}`
                : "Choose a plan to continue after your trial."}
            </p>
          </div>

          <button
            type="button"
            onClick={() => portal.mutate()}
            disabled={portal.isPending}
            className="inline-flex items-center gap-2 rounded-xl border border-border bg-background px-4 py-2.5 text-sm font-semibold text-foreground transition-colors hover:bg-muted disabled:opacity-60"
          >
            {portal.isPending ? <Loader2 size={16} className="animate-spin" /> : <CreditCard size={16} />}
            Payment method &amp; invoices
            <ExternalLink size={14} className="text-muted-foreground" />
          </button>
        </div>

        <dl className="mt-6 grid gap-4 border-t border-border pt-6 sm:grid-cols-3">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">Seats</dt>
            <dd className="mt-1 flex items-center gap-2 font-medium text-foreground">
              <Users size={16} className="text-muted-foreground" />
              {seatLabel}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">
              {current?.status === "trialing" ? "Trial ends" : "Renews"}
            </dt>
            <dd className="mt-1 font-medium text-foreground">
              {formatDate(
                current?.status === "trialing" ? current.trial_end : current?.current_period_end ?? null,
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">Cancellation</dt>
            <dd className="mt-1 font-medium text-foreground">
              {current?.cancel_at_period_end ? "Ends at period end" : "Not scheduled"}
            </dd>
          </div>
        </dl>
      </section>

      <section>
        <h2 className="mb-4 text-xl font-semibold text-foreground">
          {current?.plan ? "Change plan" : "Choose a plan"}
        </h2>

        {plans.data && !plans.data.billing_enabled ? (
          <p className="mb-6 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-400">
            Stripe is not configured on this deployment, so checkout is unavailable. Set
            STRIPE_SECRET_KEY and run <code>manage.py seed_plans --sync-stripe</code>.
          </p>
        ) : null}

        <div className="grid gap-4 md:grid-cols-3">
          {plans.data?.plans.map((plan: Plan) => {
            const isCurrent = current?.plan?.code === plan.code;
            const seatsExceeded =
              plan.seat_limit !== null && (current?.seats_in_use ?? 0) > plan.seat_limit;

            return (
              <article
                key={plan.code}
                className={`rounded-2xl border bg-card p-5 shadow-soft ${
                  isCurrent ? "border-primary ring-2 ring-primary/20" : "border-border"
                }`}
              >
                <div className="flex items-baseline justify-between">
                  <h3 className="text-lg font-semibold text-foreground">{plan.name}</h3>
                  {isCurrent ? (
                    <span className="text-xs font-semibold text-primary">Current</span>
                  ) : null}
                </div>
                <p className="mt-2 text-2xl font-bold text-foreground">
                  {plan.price_display}
                  <span className="text-sm font-medium text-muted-foreground">
                    {" "}
                    / {plan.interval}
                  </span>
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {plan.seat_limit === null ? "Unlimited employees" : `Up to ${plan.seat_limit} employees`}
                </p>

                <button
                  type="button"
                  onClick={() => checkout.mutate(plan.code)}
                  disabled={isCurrent || seatsExceeded || checkout.isPending || !plans.data?.billing_enabled}
                  className="mt-5 w-full rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-orchid-dark disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isCurrent
                    ? "Current plan"
                    : seatsExceeded
                      ? `Too many employees for ${plan.name}`
                      : checkout.isPending
                        ? "Opening…"
                        : `Switch to ${plan.name}`}
                </button>

                {seatsExceeded ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Deactivate employees down to {plan.seat_limit} to move to this plan.
                  </p>
                ) : null}
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
};

export default Billing;
