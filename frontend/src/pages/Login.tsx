import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ShieldCheck, Info, AlertCircle } from "lucide-react";
import { Logo } from "@/components/layout/Logo";
import { Button } from "@/components/ui/button";
import { useAuth, isApiError } from "@/lib/auth";

type Step = "credentials" | "mfa";

export default function Login() {
  const { login, verifyMfa } = useAuth();
  const navigate = useNavigate();

  const [step, setStep] = useState<Step>("credentials");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantId, setTenantId] = useState("1");
  const [mfaUserId, setMfaUserId] = useState<number | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleCredentialsSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = await login(email, password, Number(tenantId));
      if (result.status === "mfa_required") {
        setMfaUserId(result.user_id);
        setStep("mfa");
      } else {
        navigate("/app");
      }
    } catch (err) {
      setError(isApiError(err) ? err.message : "Sign in failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleMfaSubmit(e: FormEvent) {
    e.preventDefault();
    if (mfaUserId === null) return;
    setError(null);
    setBusy(true);
    try {
      await verifyMfa(mfaUserId, code, Number(tenantId));
      navigate("/app");
    } catch (err) {
      setError(isApiError(err) ? err.message : "Invalid code. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen md:grid-cols-2">
      <div className="hidden flex-col justify-between bg-navy p-10 text-white md:flex">
        <Logo className="text-white" />
        <div>
          <ShieldCheck className="h-10 w-10 text-teal" />
          <h2 className="mt-4 font-serif text-2xl font-semibold">
            Your session is protected end to end
          </h2>
          <p className="mt-3 max-w-sm text-white/70">
            Every sign-in is rate-limited, MFA-enforced for staff roles, and recorded to the
            immutable audit log the moment it succeeds or fails.
          </p>
        </div>
        <p className="text-xs text-white/40">&copy; {new Date().getFullYear()} SentinelKYC</p>
      </div>

      <div className="flex flex-col justify-center px-6 py-16 md:px-16">
        <div className="mx-auto w-full max-w-sm">
          <div className="mb-8 md:hidden">
            <Logo className="text-navy" />
          </div>

          {error && (
            <div className="mb-4 flex items-start gap-2 rounded-lg border border-risk-red/30 bg-risk-red/10 p-3 text-sm text-risk-red">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              {error}
            </div>
          )}

          {step === "credentials" ? (
            <>
              <h1 className="text-2xl font-semibold text-navy dark:text-white">Sign in</h1>
              <p className="mt-1 text-sm text-neutral-900/60 dark:text-white/60">
                Compliance console and applicant portal access.
              </p>
              <form className="mt-8 space-y-4" onSubmit={handleCredentialsSubmit}>
                <div>
                  <label htmlFor="tenantId" className="text-sm font-medium">
                    Tenant ID
                  </label>
                  <input
                    id="tenantId"
                    type="number"
                    required
                    value={tenantId}
                    onChange={(e) => setTenantId(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-black/10 px-3 py-2 text-sm outline-none focus:border-teal focus:ring-1 focus:ring-teal dark:border-white/20 dark:bg-transparent"
                  />
                </div>
                <div>
                  <label htmlFor="email" className="text-sm font-medium">
                    Email
                  </label>
                  <input
                    id="email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-black/10 px-3 py-2 text-sm outline-none focus:border-teal focus:ring-1 focus:ring-teal dark:border-white/20 dark:bg-transparent"
                  />
                </div>
                <div>
                  <label htmlFor="password" className="text-sm font-medium">
                    Password
                  </label>
                  <input
                    id="password"
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-black/10 px-3 py-2 text-sm outline-none focus:border-teal focus:ring-1 focus:ring-teal dark:border-white/20 dark:bg-transparent"
                  />
                </div>
                <div className="flex items-center justify-between text-sm">
                  <Link to="/forgot-password" className="text-teal">
                    Forgot password
                  </Link>
                  <span
                    title="Available on Enterprise"
                    className="cursor-not-allowed text-neutral-900/40 dark:text-white/40"
                  >
                    SSO
                  </span>
                </div>
                <Button type="submit" className="w-full" disabled={busy}>
                  {busy ? "Signing in..." : "Continue"}
                </Button>
              </form>
            </>
          ) : (
            <>
              <h1 className="text-2xl font-semibold text-navy dark:text-white">
                Enter your MFA code
              </h1>
              <p className="mt-1 flex items-start gap-2 text-sm text-neutral-900/60 dark:text-white/60">
                <Info className="mt-0.5 h-4 w-4 shrink-0" />
                Open your authenticator app and enter the 6-digit code for {email || "your account"}
                .
              </p>
              <form className="mt-8 space-y-4" onSubmit={handleMfaSubmit}>
                <input
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  placeholder="000000"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  className="w-full rounded-lg border border-black/10 px-3 py-2 text-center text-lg tracking-[0.5em] outline-none focus:border-teal focus:ring-1 focus:ring-teal dark:border-white/20 dark:bg-transparent"
                />
                <Button type="submit" className="w-full" disabled={busy}>
                  {busy ? "Verifying..." : "Verify and sign in"}
                </Button>
                <button
                  type="button"
                  onClick={() => setStep("credentials")}
                  className="w-full text-center text-sm text-neutral-900/60 dark:text-white/60"
                >
                  Back
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
