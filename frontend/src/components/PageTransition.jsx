import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { useLocation } from "react-router-dom";
import { EASE_OUT } from "./motionConfig";

const DURATION_PAGE = 0.26;

export default function PageTransition({ children }) {
  const location = useLocation();
  const reduced = useReducedMotion();

  const pageVariants = {
    initial: reduced ? { opacity: 0 } : { opacity: 0, y: 10 },
    animate: {
      opacity: 1,
      y: 0,
      transition: { duration: DURATION_PAGE, ease: EASE_OUT },
    },
    exit: {
      opacity: 0,
      y: reduced ? 0 : -8,
      transition: { duration: 0.18, ease: EASE_OUT },
    },
  };

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={location.pathname}
        variants={pageVariants}
        initial="initial"
        animate="animate"
        exit="exit"
        style={{ width: "100%" }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
