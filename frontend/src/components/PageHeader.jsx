import { motion, useReducedMotion } from "framer-motion";
import { EASE_OUT } from "./motionConfig";

export default function PageHeader({ label, title, subtitle, className = "" }) {
  const reduced = useReducedMotion();

  return (
    <motion.header
      className={`app-page-header ${className}`.trim()}
      initial={reduced ? { opacity: 0 } : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: EASE_OUT }}
    >
      {label && <p className="micro-label">{label}</p>}
      <h1 className="display-title app-page-header__title">{title}</h1>
      {subtitle && <p className="app-page-header__subtitle">{subtitle}</p>}
    </motion.header>
  );
}
