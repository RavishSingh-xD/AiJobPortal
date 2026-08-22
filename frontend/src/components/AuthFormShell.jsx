import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { fadeUp, staggerContainer } from "./motionConfig";

export default function AuthFormShell({
  backTo = "/login",
  backLabel = "Back to log in",
  wide = false,
  children,
}) {
  return (
    <div className="page page--auth">
      <motion.div
        className={`page-inner auth-form-column${wide ? " page-inner--wide" : ""}`}
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
      >
        <motion.div variants={fadeUp}>
          <Link to={backTo} className="auth-back">
            {backLabel}
          </Link>
        </motion.div>
        <motion.div className="auth-form-card" variants={fadeUp}>
          {children}
        </motion.div>
      </motion.div>
    </div>
  );
}
