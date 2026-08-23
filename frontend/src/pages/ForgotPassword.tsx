import React, { useState } from "react";
import { Link } from "react-router-dom";
import { MailCheck } from "lucide-react";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { requestPasswordReset } from "@/api/auth";
import { useToast } from "@/hooks/use-toast";

/**
 * There was no password recovery route at all before this (audit V-27): a user
 * who forgot their password had to ask an admin to delete and recreate them,
 * which under the old hard delete destroyed their payroll history.
 */
const ForgotPassword: React.FC = () => {
  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const { toast } = useToast();

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await requestPasswordReset(email);
      setSent(true);
    } catch (error: any) {
      toast({
        title: "Could not send the reset link",
        description: error?.message ?? "Please try again in a moment.",
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthLayout
      quote="The best time to prepare was yesterday. The second best time is now."
      author="DayFlow"
    >
      <div className="rounded-2xl border border-border bg-card p-8 shadow-medium md:p-12">
        {sent ? (
          <div className="text-center">
            <span className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <MailCheck size={26} />
            </span>
            <h1 className="mb-2 text-2xl font-bold text-foreground">Check your inbox</h1>
            {/* Deliberately does not confirm whether the address is registered:
                the endpoint returns an identical response either way so it
                cannot be used to enumerate accounts. */}
            <p className="text-muted-foreground">
              If <span className="font-medium text-foreground">{email}</span> has a DayFlow
              account, a reset link is on its way. The link expires in an hour.
            </p>
            <Link
              to="/login"
              className="mt-8 inline-block font-semibold text-primary hover:underline"
            >
              Back to login
            </Link>
          </div>
        ) : (
          <>
            <h1 className="mb-2 text-2xl font-bold text-foreground md:text-3xl">
              Forgot your password?
            </h1>
            <p className="mb-8 text-muted-foreground">
              Enter your work email and we will send you a link to choose a new one.
            </p>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label htmlFor="email" className="mb-2 block text-sm font-medium text-foreground">
                  Work email
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@company.com"
                  className="w-full rounded-xl border border-input bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-transparent focus:outline-none focus:ring-2 focus:ring-primary"
                  required
                  autoComplete="email"
                />
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full rounded-xl bg-primary py-3.5 font-semibold text-primary-foreground transition-colors hover:bg-orchid-dark disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSubmitting ? "Sending…" : "Send reset link"}
              </button>
            </form>

            <p className="mt-6 text-center text-muted-foreground">
              Remembered it?{" "}
              <Link to="/login" className="font-semibold text-primary hover:underline">
                Log in
              </Link>
            </p>
          </>
        )}
      </div>
    </AuthLayout>
  );
};

export default ForgotPassword;
