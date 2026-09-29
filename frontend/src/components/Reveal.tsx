import { motion } from "framer-motion";
import type { ReactNode } from "react";

/** Fade + rise on scroll into view; respects prefers-reduced-motion via
 * Framer Motion's default behavior of honoring the OS setting. */
export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.28, delay, ease: "easeOut" }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
