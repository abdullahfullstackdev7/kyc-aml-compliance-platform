import { Link } from "react-router-dom";

export function Logo({ className = "" }: { className?: string }) {
  return (
    <Link to="/" className={`flex items-center gap-2 font-semibold ${className}`}>
      <svg width="24" height="24" viewBox="0 0 32 32" aria-hidden="true">
        <path d="M16 2 28 7v9c0 8-5.2 13.7-12 15C9.2 29.7 4 24 4 16V7z" fill="currentColor" />
        <path
          d="M11 16.5l3.5 3.5L21 12"
          stroke="#0FA3B1"
          strokeWidth="2.4"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="text-lg tracking-tight">SentinelKYC</span>
    </Link>
  );
}
