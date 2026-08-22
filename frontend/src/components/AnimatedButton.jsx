import { motion, useReducedMotion } from "framer-motion";
import { EASE_OUT, SPRING } from "./motionConfig";

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
      {...props}
      className={classes}
      whileHover={interactive ? { y: -1 } : undefined}
      whileTap={interactive ? { y: 1, scale: 0.985 } : undefined}
      transition={SPRING}
      disabled={loading || props.disabled}
    >
      {loading && <span className="btn-spinner" aria-hidden="true" />}
      <span className="btn__label">{children}</span>
    </motion.button>
  );
}

export function MotionSubmit({ children, disabled, className = "auth-submit" }) {
  const reduced = useReducedMotion();
  return (
    <motion.button
      type="submit"
      className={className}
      disabled={disabled}
      whileHover={disabled || reduced ? undefined : { y: -1 }}
      whileTap={disabled || reduced ? undefined : { y: 1, scale: 0.985 }}
      transition={{ duration: 0.16, ease: EASE_OUT }}
    >
      {children}
    </motion.button>
  );
}
