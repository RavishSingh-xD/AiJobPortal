import { motion, useReducedMotion } from "framer-motion";
import { EASE_OUT } from "./motionConfig";

export default function ProgressRail({
  value = 0,
  max = 100,
  slim = false,
  label,
}) {
  const reduced = useReducedMotion();
  const pct = Math.max(0, Math.min(100, (Number(value) / max) * 100));

  return (
    <div
      className={`progress-rail${slim ? " progress-rail--slim" : ""}`}
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-label={label}
    >
      <motion.div
        className="progress-rail__bar"
        initial={reduced ? false : { width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.55, ease: EASE_OUT }}
      />
    </div>
  );
}
