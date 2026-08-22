import { motion, useReducedMotion } from "framer-motion";
import { EASE_OUT } from "./motionConfig";

export default function Surface({
  children,
  className = "",
  delay = 0,
  hover = true,
  flush = false,
}) {
  const reduced = useReducedMotion();
  const classes = ["surface", flush ? "surface--flush" : "", className]
    .filter(Boolean)
    .join(" ");

  return (
    <motion.div
      className={classes}
      initial={reduced ? { opacity: 0 } : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={
        !reduced && hover
          ? { y: -1, transition: { duration: 0.18, ease: EASE_OUT } }
          : undefined
      }
      transition={{ duration: 0.28, ease: EASE_OUT, delay: reduced ? 0 : delay }}
    >
      {children}
    </motion.div>
  );
}
