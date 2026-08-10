import { motion } from "framer-motion";

export default function AnimatedButton({
  children,
  loading = false,
  className = "",
  secondary = false,
  ...props
}) {
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
      whileHover={!props.disabled && !loading ? { scale: 1.02, filter: "brightness(1.08)" } : {}}
      whileTap={!props.disabled && !loading ? { scale: 0.98 } : {}}
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading && <span className="btn-spinner" aria-hidden="true" />}
      {children}
    </motion.button>
  );
}
