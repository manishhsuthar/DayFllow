import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Check, Loader2 } from "lucide-react";
import { fetchPlans, startCheckout, type Plan } from "@/api/billing";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";

/**
 * Pricing.
 *
 * Prices come from the server, in USD, as integer cents. They used to be
 * hardcoded rupee strings in this file while the backend charged a different
 * hardcoded amount, and "verifying" a payment granted nothing at all (audit V-10).
 *
 * Checkout is Stripe-hosted: this page never sees card details, and never tells
 * the API what was paid.
 */
const PlanSelection: React.FC = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { isAuthenticated, isOwner } = useAuth();
  const [pendingPlan, setPendingPlan] = React.useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["plans"],
    queryFn: fetchPlans,
  });

  const handleChoose = async (plan: Plan) => {
    // Signup has to happen first: a Checkout session belongs to an organization.
    if (!isAuthenticated) {
      navigate("/signup", { state: { selectedPlan: plan.code } });
      return;
    }
    if (!isOwner) {
      toast({
        title: "Ask your administrator",
        description: "Only the organization administrator can change the plan.",
        variant: "destructive",
      });
      return;
    }

    setPendingPlan(plan.code);
    try {
      const { checkout_url } = await startCheckout(plan.code);
      // Hand off to Stripe.
      window.location.href = checkout_url;
    } catch (error: any) {
      setPendingPlan(null);
      toast({
        title: "Could not start checkout",
        description: error?.message ?? "Please try again in a moment.",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="min-h-screen bg-background px-6 py-16 md:py-24">
      <div className="mx-auto max-w-6xl">
        <div className="text-center">
          <h1 className="mt-5 text-3xl font-bold text-foreground md:text-5xl">
            Simple, predictable pricing
          </h1>
          <p className="mx-auto mt-4 max-w-3xl text-base text-muted-foreground md:text-lg">
            Every plan includes the full DayFlow feature set. You are choosing capacity and
            support, not features.
            {data ? ` Start with a ${data.trial_days}-day free trial — no card required.` : ""}
          </p>
        </div>

        {isLoading ? (
          <div className="mt-16 flex justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : isError ? (
          <p className="mt-16 text-center text-muted-foreground">
            Pricing is unavailable right now. Please refresh, or{" "}
            <Link to="/signup" className="text-primary hover:underline">
              start your free trial
            </Link>{" "}
            and choose a plan later.
          </p>
        ) : (
          <>
            {data && !data.billing_enabled ? (
              <p className="mx-auto mt-8 max-w-2xl rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-center text-sm text-amber-700 dark:text-amber-400">
                Checkout is not connected on this deployment yet. You can still start a free
                trial.
              </p>
            ) : null}

            <div className="mt-12 grid gap-6 md:grid-cols-3">
              {data?.plans.map((plan) => {
                const highlighted = plan.code === "growth";
                return (
                  <article
                    key={plan.code}
                    className={`rounded-2xl border bg-card p-6 shadow-soft transition-all duration-300 hover:-translate-y-1 hover:shadow-medium ${
                      highlighted ? "border-primary ring-2 ring-primary/25" : "border-border"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <h2 className="text-2xl font-bold text-foreground">{plan.name}</h2>
                      {highlighted ? (
                        <span className="rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground">
                          Most popular
                        </span>
                      ) : null}
                    </div>

                    <p className="mt-3 text-4xl font-extrabold text-foreground">
                      {plan.price_display}
                      <span className="text-base font-medium text-muted-foreground">
                        {" "}
                        / {plan.interval}
                      </span>
                    </p>
                    <p className="mt-2 text-sm text-muted-foreground">{plan.description}</p>

                    <div className="mt-5 rounded-xl bg-lavender px-3 py-2 text-sm font-medium text-foreground">
                      {plan.seat_limit === null
                        ? "Unlimited employees"
                        : `Up to ${plan.seat_limit} employees`}
                    </div>

                    <ul className="mt-6 space-y-3">
                      {plan.features.map((feature) => (
                        <li
                          key={feature}
                          className="flex items-start gap-2 text-sm text-foreground"
                        >
                          <Check size={16} className="mt-0.5 shrink-0 text-primary" />
                          <span>{feature}</span>
                        </li>
                      ))}
                    </ul>

                    <button
                      type="button"
                      onClick={() => void handleChoose(plan)}
                      disabled={pendingPlan !== null}
                      className={`mt-8 inline-flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-70 ${
                        highlighted
                          ? "bg-primary text-primary-foreground hover:bg-orchid-dark"
                          : "bg-deep-purple text-white hover:bg-deep-purple/90"
                      }`}
                    >
                      {pendingPlan === plan.code ? (
                        <>
                          <Loader2 size={16} className="animate-spin" />
                          Opening checkout…
                        </>
                      ) : (
                        <>
                          {isAuthenticated ? `Choose ${plan.name}` : "Start free trial"}
                          <ArrowRight size={16} />
                        </>
                      )}
                    </button>
                  </article>
                );
              })}
            </div>
          </>
        )}

        <p className="mt-12 text-center text-sm text-muted-foreground">
          Prices in {data?.currency?.toUpperCase() ?? "USD"}. Cancel any time from the billing
          portal.
        </p>
      </div>
    </div>
  );
};

export default PlanSelection;
