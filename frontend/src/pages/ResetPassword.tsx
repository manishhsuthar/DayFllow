import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Eye, EyeOff } from "lucide-react";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { confirmPasswordReset } from "@/api/auth";
import { useToast } from "@/hooks/use-toast";
import type { ApiError } from "@/api/client";

/** Landing page for the emailed reset link. Tokens are single-use and expiring. */
const ResetPassword: React.FC = () => {
  const [searchParams] = useSearchParams();
  const uid = searchParams.get("uid") ?? "";
  const token = searchParams.get("token") ?? "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmValue, setConfirmValue] = useState("");
  const [show, setShow] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const navigate = useNavigate();
  const { toast } = useToast();

  const linkIsMalformed = !uid || !token;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (newPassword !== confirmValue) {
      toast({
        title: "Passwords do not match",
        description: "Please type the same password twice.",
        variant: "destructive",
      });
      return;
    }

    setIsSubmitting(true);
    try {
      await confirmPasswordReset({ uid, token, new_password: newPassword });
      toast({
        title: "Password reset",
        description: "You can log in with your new password now.",
      });
      navigate("/login", { replace: true });
    } catch (error) {
      const apiError = error as ApiError;
      toast({
        title: "Could not reset your password",
        description:
          apiError.fieldErrors?.new_password?.join(" ") ||
          apiError.message ||
          "This link may have expired. Request a new one.",
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const inputClass =
    "w-full rounded-xl border border-input bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-transparent focus:outline-none focus:ring-2 focus:ring-primary";

  return (
    <AuthLayout quote="Simplicity is the ultimate sophistication." author="Leonardo da Vinci">
      <div className="rounded-2xl border border-border bg-card p-8 shadow-medium md:p-12">
        <h1 className="mb-2 text-2xl font-bold text-foreground md:text-3xl">Set a new password</h1>

        {linkIsMalformed ? (
          <>
            <p className="mb-8 text-muted-foreground">
              This reset link is incomplete. Request a fresh one and use the newest email.
            </p>
            <Link
              to="/forgot-password"
              className="inline-block font-semibold text-primary hover:underline"
            >
              Request a new link
            </Link>
          </>
        ) : (
          <>
            <p className="mb-8 text-muted-foreground">
              Choose something you have not used on DayFlow before.
            </p>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label
                  htmlFor="newPassword"
                  className="mb-2 block text-sm font-medium text-foreground"
                >
                  New password
                </label>
                <div className="relative">
                  <input
                    id="newPassword"
                    type={show ? "text" : "password"}
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    className={`${inputClass} pr-12`}
                    required
                    minLength={10}
                    autoComplete="new-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShow((value) => !value)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-primary"
                    aria-label={show ? "Hide password" : "Show password"}
                  >
                    {show ? <EyeOff size={20} /> : <Eye size={20} />}
                  </button>
                </div>
                <p className="mt-1.5 text-xs text-muted-foreground">At least 10 characters.</p>
              </div>

              <div>
                <label
                  htmlFor="confirmValue"
                  className="mb-2 block text-sm font-medium text-foreground"
                >
                  Confirm password
                </label>
                <input
                  id="confirmValue"
                  type={show ? "text" : "password"}
                  value={confirmValue}
                  onChange={(event) => setConfirmValue(event.target.value)}
                  className={inputClass}
                  required
                  autoComplete="new-password"
                />
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full rounded-xl bg-primary py-3.5 font-semibold text-primary-foreground transition-colors hover:bg-orchid-dark disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSubmitting ? "Saving…" : "Reset password"}
              </button>
            </form>
          </>
        )}
      </div>
    </AuthLayout>
  );
};

export default ResetPassword;
