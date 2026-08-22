import { motion, useReducedMotion } from "framer-motion";

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
      whileHover={interactive ? { scale: 1.02 } : undefined}
      whileTap={interactive ? { scale: 0.97 } : undefined}
      transition={{ type: "spring", stiffness: 420, damping: 32 }}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading && <span className="btn-spinner" aria-hidden="true" />}
      {children}
    </motion.button>
  );
}
