import { motion } from "framer-motion";
import { LoadingPulse, EASE_OUT } from "./motionConfig";

export default function EmptyState({
  variant = "empty",
  title,
  text,
  action = null,
  loading = false,
}) {
  const statusLabel =
    variant === "loading"
      ? "Loading"
      : variant === "error"
        ? "Error"
        : variant === "harvesting"
          ? "Sync"
          : "Empty";

  return (
    <motion.div
      className={`empty-state empty-state--${variant}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: EASE_OUT }}
    >
      {loading ? (
        <LoadingPulse>
          <span className="empty-state__marker" aria-hidden="true" />
        </LoadingPulse>
      ) : (
        <span className="empty-state__marker" aria-hidden="true" />
      )}
      <p className="micro-label">{statusLabel}</p>
      <h2 className="empty-state__title">{title}</h2>
      {text && <p className="empty-state__text">{text}</p>}
      {action}
    </motion.div>
  );
}
