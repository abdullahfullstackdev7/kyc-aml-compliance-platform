import { useState } from "react";
import { Link } from "react-router-dom";
import { Logo } from "@/components/layout/Logo";
import { Button } from "@/components/ui/button";

export default function ForgotPassword() {
  const [sent, setSent] = useState(false);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-6 py-16">
      <div className="mb-8">
        <Logo className="text-navy dark:text-white" />
      </div>
      <div className="w-full max-w-sm">
        <h1 className="text-2xl font-semibold text-navy dark:text-white">Reset your password</h1>
        {sent ? (
          <p className="mt-4 text-sm text-neutral-900/70 dark:text-white/70">
            If an account exists for that email, a reset link has been sent.
          </p>
        ) : (
          <form
            className="mt-6 space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              setSent(true);
            }}
          >
            <input
              type="email"
              required
              placeholder="you@company.com"
              className="w-full rounded-lg border border-black/10 px-3 py-2 text-sm outline-none focus:border-teal focus:ring-1 focus:ring-teal dark:border-white/20 dark:bg-transparent"
            />
            <Button type="submit" className="w-full">
              Send reset link
            </Button>
          </form>
        )}
        <Link to="/login" className="mt-6 inline-block text-sm text-teal">
          Back to sign in
        </Link>
      </div>
    </div>
  );
}
