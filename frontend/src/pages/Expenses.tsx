import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, Plus, X } from "lucide-react";
import {
  fetchExpenseClaims,
  reviewExpenseClaim,
  submitExpenseClaim,
  type ExpenseClaim,
} from "@/api/payroll";
import { formatAmount } from "@/api/billing";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";

const STATUS_STYLES: Record<ExpenseClaim["status"], string> = {
  PENDING: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  APPROVED: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  REJECTED: "bg-destructive/10 text-destructive",
};

/**
 * Expense claims.
 *
 * Submitting used to write straight into the employee's outstanding balance with
 * no review, no cap and no way to reverse it (audit V-07). Now a claim is a
 * request; only a manager's approval moves money, and nobody can approve their own.
 */
const Expenses: React.FC = () => {
  const { isManagement, user } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [incurredOn, setIncurredOn] = useState(() => new Date().toISOString().slice(0, 10));

  const claims = useQuery({ queryKey: ["expense-claims"], queryFn: () => fetchExpenseClaims() });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["expense-claims"] });
    queryClient.invalidateQueries({ queryKey: ["salaries"] });
  };

  const submit = useMutation({
    mutationFn: () =>
      submitExpenseClaim({ amount, description, incurred_on: incurredOn }),
    onSuccess: () => {
      toast({
        title: "Claim submitted",
        description: "It will appear on your payslip once approved.",
      });
      setAmount("");
      setDescription("");
      invalidate();
    },
    onError: (error: any) =>
      toast({
        title: "Could not submit the claim",
        description: error?.message ?? "Please check the details and try again.",
        variant: "destructive",
      }),
  });

  const review = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "APPROVE" | "REJECT" }) =>
      reviewExpenseClaim(id, action),
    onSuccess: (claim) => {
      toast({
        title: claim.status === "APPROVED" ? "Claim approved" : "Claim rejected",
        description:
          claim.status === "APPROVED"
            ? "The amount has been added to the employee's outstanding balance."
            : "No balance was changed.",
      });
      invalidate();
    },
    onError: (error: any) =>
      toast({
        title: "Could not review the claim",
        description: error?.message ?? "Please try again.",
        variant: "destructive",
      }),
  });

  const inputClass =
    "w-full rounded-xl border border-input bg-background px-4 py-2.5 text-foreground placeholder:text-muted-foreground focus:border-transparent focus:outline-none focus:ring-2 focus:ring-primary";

  return (
    <div className="p-6 md:p-10">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-foreground">Expenses</h1>
        <p className="mt-1 text-muted-foreground">
          Submit a claim for review. Approved claims are recovered from pay over time, capped so
          take-home pay never falls below zero.
        </p>
      </header>

      <section className="mb-10 rounded-2xl border border-border bg-card p-6 shadow-soft">
        <h2 className="mb-4 text-lg font-semibold text-foreground">New claim</h2>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            submit.mutate();
          }}
          className="grid gap-4 sm:grid-cols-[1fr_2fr_1fr_auto] sm:items-end"
        >
          <div>
            <label htmlFor="amount" className="mb-1.5 block text-sm font-medium text-foreground">
              Amount (USD)
            </label>
            <input
              id="amount"
              type="number"
              min="0.01"
              step="0.01"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="0.00"
              className={inputClass}
              required
            />
          </div>
          <div>
            <label
              htmlFor="description"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              What was it for?
            </label>
            <input
              id="description"
              type="text"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Client travel, software licence…"
              className={inputClass}
              minLength={3}
              maxLength={255}
              required
            />
          </div>
          <div>
            <label
              htmlFor="incurredOn"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Date
            </label>
            <input
              id="incurredOn"
              type="date"
              value={incurredOn}
              max={new Date().toISOString().slice(0, 10)}
              onChange={(event) => setIncurredOn(event.target.value)}
              className={inputClass}
              required
            />
          </div>
          <button
            type="submit"
            disabled={submit.isPending}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-orchid-dark disabled:opacity-50"
          >
            {submit.isPending ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
            Submit
          </button>
        </form>
      </section>

      <section>
        <h2 className="mb-4 text-lg font-semibold text-foreground">
          {isManagement ? "All claims" : "Your claims"}
        </h2>

        {claims.isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        ) : !claims.data?.length ? (
          <p className="rounded-2xl border border-dashed border-border py-12 text-center text-muted-foreground">
            No expense claims yet.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-2xl border border-border bg-card shadow-soft">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-muted/40 text-left">
                <tr>
                  {isManagement ? <th className="px-4 py-3 font-semibold">Employee</th> : null}
                  <th className="px-4 py-3 font-semibold">Description</th>
                  <th className="px-4 py-3 font-semibold">Date</th>
                  <th className="px-4 py-3 text-right font-semibold">Amount</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold">Reviewed by</th>
                  {isManagement ? <th className="px-4 py-3" /> : null}
                </tr>
              </thead>
              <tbody>
                {claims.data.map((claim) => {
                  const isOwnClaim = claim.employee === user?.id;
                  return (
                    <tr key={claim.id} className="border-b border-border last:border-0">
                      {isManagement ? (
                        <td className="px-4 py-3 text-foreground">{claim.employee_name}</td>
                      ) : null}
                      <td className="px-4 py-3 text-foreground">{claim.description}</td>
                      <td className="px-4 py-3 text-muted-foreground">{claim.incurred_on}</td>
                      <td className="px-4 py-3 text-right font-medium text-foreground">
                        {formatAmount(claim.amount)}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`rounded-full px-2.5 py-1 text-xs font-semibold ${STATUS_STYLES[claim.status]}`}
                        >
                          {claim.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {claim.reviewed_by_login_id ?? "—"}
                      </td>
                      {isManagement ? (
                        <td className="px-4 py-3">
                          {claim.status === "PENDING" && !isOwnClaim ? (
                            <div className="flex justify-end gap-2">
                              <button
                                type="button"
                                onClick={() => review.mutate({ id: claim.id, action: "APPROVE" })}
                                disabled={review.isPending}
                                className="inline-flex items-center gap-1 rounded-lg bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-600 hover:bg-emerald-500/20 disabled:opacity-50 dark:text-emerald-400"
                              >
                                <Check size={14} /> Approve
                              </button>
                              <button
                                type="button"
                                onClick={() => review.mutate({ id: claim.id, action: "REJECT" })}
                                disabled={review.isPending}
                                className="inline-flex items-center gap-1 rounded-lg bg-destructive/10 px-3 py-1.5 text-xs font-semibold text-destructive hover:bg-destructive/20 disabled:opacity-50"
                              >
                                <X size={14} /> Reject
                              </button>
                            </div>
                          ) : isOwnClaim && claim.status === "PENDING" ? (
                            <span className="text-xs text-muted-foreground">
                              Awaiting another reviewer
                            </span>
                          ) : null}
                        </td>
                      ) : null}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
};

export default Expenses;
