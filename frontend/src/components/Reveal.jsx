import { motion, useReducedMotion } from "framer-motion";
import { EASE_OUT, fadeUp, staggerContainer } from "./motionConfig";

export default function Reveal({
  as = "div",
  children,
  className = "",
  delay = 0,
  stagger = false,
  once = true,
  ...props
}) {
  const reduced = useReducedMotion();
  const Tag = motion[as] || motion.div;

  return (
    <Tag
      className={className}
      variants={stagger && !reduced ? staggerContainer : fadeUp}
      initial="hidden"
      whileInView="visible"
      viewport={{ once, amount: 0.16 }}
      custom={delay}
      transition={
        reduced
          ? { duration: 0 }
          : { duration: 0.34, ease: EASE_OUT, delay }
      }
      {...props}
    >
      {children}
    </Tag>
  );
}

export function RevealItem({ children, className = "" }) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      variants={reduced ? { hidden: { opacity: 1 }, visible: { opacity: 1 } } : fadeUp}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, amount: 0.2 }}
    >
      {children}
    </motion.div>
  );
}
