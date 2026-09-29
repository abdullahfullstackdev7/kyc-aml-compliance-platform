import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "1rem", screens: { xl: "1280px" } },
    extend: {
      colors: {
        navy: "#0B1F3A",
        "deep-blue": "#123B6D",
        teal: "#0FA3B1",
        amber: "#F2A541",
        "risk-red": "#C8102E",
        "success-green": "#1F8A5B",
        neutral: {
          50: "#F7F9FC",
          900: "#1E2530",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        serif: ["Source Serif 4", "Georgia", "serif"],
      },
      borderRadius: { card: "12px" },
      boxShadow: { subtle: "0 1px 3px rgba(11, 31, 58, 0.08)" },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [],
} satisfies Config;
