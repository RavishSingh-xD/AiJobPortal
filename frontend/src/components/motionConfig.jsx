import { motion, useReducedMotion } from "framer-motion";

export const EASE_OUT = [0.16, 1, 0.3, 1];
export const DURATION = 0.2;
export const SPRING = { type: "spring", stiffness: 420, damping: 32, mass: 0.7 };

export const staggerContainer = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.045, delayChildren: 0.04 },
  },
};

export const fadeUp = {
  hidden: { opacity: 0, y: 10 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.32, ease: EASE_OUT },
  },
};

export function LoadingPulse({ children, className = "" }) {
  const reduced = useReducedMotion();

  return (
    <motion.div
      className={className}
      animate={reduced ? { opacity: 1 } : { opacity: [0.42, 1, 0.42] }}
      transition={
        reduced
          ? { duration: 0 }
          : { duration: 1.4, repeat: Infinity, ease: "easeInOut" }
      }
    >
      {children}
    </motion.div>
  );
}

export function MotionListItem({ children, index = 0, className = "", as = "div" }) {
  const reduced = useReducedMotion();
  const Tag = motion[as] || motion.div;

  return (
    <Tag
      className={className}
      initial={reduced ? { opacity: 0 } : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={reduced ? undefined : { backgroundColor: "rgba(26, 38, 56, 0.55)" }}
      transition={{
        duration: DURATION,
        ease: EASE_OUT,
        delay: reduced ? 0 : index * 0.04,
      }}
    >
      {children}
    </Tag>
  );
}
