import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { EASE_OUT, DURATION } from "./motionConfig";

const cardVariants = {
  hidden: ({ reduced } = {}) => (reduced ? { opacity: 0 } : { opacity: 0, y: 8 }),
  visible: ({ delay = 0, reduced = false } = {}) => ({
    opacity: 1,
    y: 0,
    transition: {
      duration: DURATION,
      ease: EASE_OUT,
      delay: reduced ? 0 : delay,
    },
  }),
};

export default function GlassCard({
  children,
  className = "",
  delay = 0,
  hover = true,
}) {
  const reduced = useReducedMotion();
  const [fineHover, setFineHover] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(hover: hover) and (pointer: fine)");
    const sync = () => setFineHover(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  return (
    <motion.div
      className={`glass-card ${className}`}
      variants={cardVariants}
      custom={{ delay, reduced }}
      initial="hidden"
      animate="visible"
      whileHover={
        !reduced && hover && fineHover
          ? { opacity: 0.96, transition: { duration: 0.15, ease: [0.16, 1, 0.3, 1] } }
          : undefined
      }
    >
      {children}
    </motion.div>
  );
}
