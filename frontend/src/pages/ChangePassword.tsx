import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff, ShieldCheck } from "lucide-react";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { ApiError } from "@/api/client";

/**
 * A new hire signs in with a temporary password and lands here.
 *
 * This is no longer just a nudge: while `must_change_password` is set, the API
 * rejects every request except this one, refresh, logout and `me` (audit V-15).
 */
const ChangePassword: React.FC = () => {
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [show, setShow] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { changePassword, isAuthenticated, isLoading, user } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();

  if (!isLoading && !isAuthenticated) {
    navigate("/login", { replace: true });
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (newPassword !== confirmPassword) {
      toast({
        title: "Passwords do not match",
        description: "Please type the same new password twice.",
        variant: "destructive",
      });
      return;
    }

    setIsSubmitting(true);
    try {
      const updated = await changePassword(oldPassword, newPassword);
      toast({ title: "Password updated", description: "You are all set." });
      navigate(
        updated.role === "ADMIN" || updated.role === "HR"
          ? "/dashboard/admin"
          : "/dashboard/employee",
        { replace: true },
      );
    } catch (error) {
      const apiError = error as ApiError;
      toast({
        title: "Could not change password",
        description:
          apiError.fieldErrors?.new_password?.join(" ") || apiError.message || "Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const inputClass =
    "w-full rounded-xl border border-input bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-transparent focus:outline-none focus:ring-2 focus:ring-primary";

  return (
    <AuthLayout
      quote="Security is always excessive until it's not enough."
      author="Robbie Sinclair"
    >
      <div className="rounded-2xl border border-border bg-card p-8 shadow-medium md:p-12">
        <div className="mb-6 flex items-center gap-3">
          <span className="rounded-xl bg-primary/10 p-2 text-primary">
            <ShieldCheck size={22} />
          </span>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Choose a new password</h1>
            <p className="text-sm text-muted-foreground">
              {user?.must_change_password
                ? "Your account still uses the temporary password you were issued."
                : "Update the password for your account."}
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label htmlFor="oldPassword" className="mb-2 block text-sm font-medium text-foreground">
              Current password
            </label>
            <input
              id="oldPassword"
              type={show ? "text" : "password"}
              value={oldPassword}
              onChange={(event) => setOldPassword(event.target.value)}
              className={inputClass}
              required
              autoComplete="current-password"
            />
          </div>

          <div>
            <label htmlFor="newPassword" className="mb-2 block text-sm font-medium text-foreground">
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
                aria-label={show ? "Hide passwords" : "Show passwords"}
              >
                {show ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </div>
            <p className="mt-1.5 text-xs text-muted-foreground">
              At least 10 characters, and not a password in common use.
            </p>
          </div>

          <div>
            <label
              htmlFor="confirmPassword"
              className="mb-2 block text-sm font-medium text-foreground"
            >
              Confirm new password
            </label>
            <input
              id="confirmPassword"
              type={show ? "text" : "password"}
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
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
            {isSubmitting ? "Updating…" : "Update password"}
          </button>
        </form>
      </div>
    </AuthLayout>
  );
};

export default ChangePassword;
