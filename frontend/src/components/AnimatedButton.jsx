import { motion, useReducedMotion } from "framer-motion";
import { EASE_OUT } from "./motionConfig";

export default function AnimatedButton({
  children,
  loading = false,
  className = "",
  secondary = false,
  ...props
}) {
  const reduced = useReducedMotion();
  const interactive = !props.disabled && !loading && !reduced;
  const classes = [
    "btn",
    secondary ? "btn--secondary" : "",
    loading ? "btn--loading btn--loading-pulse" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <motion.button
      className={classes}
      whileHover={interactive ? { opacity: 0.88 } : undefined}
      whileTap={interactive ? { opacity: 0.75 } : undefined}
      transition={{ duration: 0.15, ease: EASE_OUT }}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading && <span className="btn-spinner" aria-hidden="true" />}
      {children}
    </motion.button>
  );
}
