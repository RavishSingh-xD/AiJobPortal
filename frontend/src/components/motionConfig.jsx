import { motion, useReducedMotion } from "framer-motion";

export const EASE_OUT = [0.22, 1, 0.36, 1];
export const DURATION = 0.28;

export function LoadingPulse({ children, className = "" }) {
  const reduced = useReducedMotion();

  return (
    <motion.div
      className={className}
      animate={reduced ? { opacity: 1 } : { opacity: [0.45, 1, 0.45] }}
      transition={
        reduced
          ? { duration: 0 }
          : { duration: 1.6, repeat: Infinity, ease: "easeInOut" }
      }
    >
      {children}
    </motion.div>
  );
}

export function MotionListItem({ children, index = 0, className = "" }) {
  const reduced = useReducedMotion();

  return (
    <motion.div
      className={className}
      initial={reduced ? { opacity: 0 } : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={reduced ? undefined : { scale: 1.02 }}
      transition={{
        duration: DURATION,
        ease: EASE_OUT,
        delay: reduced ? 0 : index * 0.05,
        scale: { type: "spring", stiffness: 420, damping: 32 },
      }}
    >
      {children}
    </motion.div>
  );
}
