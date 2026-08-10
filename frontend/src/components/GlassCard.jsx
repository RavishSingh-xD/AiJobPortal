import { motion } from "framer-motion";

const cardVariants = {
  hidden: { opacity: 0, scale: 0.96, y: 12 },
  visible: (delay = 0) => ({
    opacity: 1,
    scale: 1,
    y: 0,
    transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1], delay },
  }),
};

export default function GlassCard({ children, className = "", delay = 0 }) {
  return (
    <motion.div
      className={`glass-card ${className}`}
      variants={cardVariants}
      custom={delay}
      initial="hidden"
      animate="visible"
      whileHover={{ y: -2, transition: { duration: 0.2 } }}
    >
      {children}
    </motion.div>
  );
}
