import { motion } from "framer-motion";
import { fadeUp, staggerContainer } from "./motionConfig";

const FEATURES = [
  "Roles ranked to your resume and domain test",
  "Apply with a profile that already knows who you are",
  "Built for students — early access as we grow listings",
];

export default function AuthMarketingPanel() {
  return (
    <motion.aside
      className="auth-promo"
      aria-label="About Avyukt"
      variants={staggerContainer}
      initial="hidden"
      animate="visible"
    >
      <div className="auth-promo__inner">
        <motion.span className="auth-promo__badge" variants={fadeUp}>
          Avyukt
        </motion.span>
        <motion.h2 className="auth-promo__title" variants={fadeUp}>
          Your internship, matched.
        </motion.h2>
        <motion.p className="auth-promo__lede" variants={fadeUp}>
          Build a profile once, verify your identity, and explore roles ranked to
          your skills — not a generic job board.
        </motion.p>

        <motion.ul className="auth-promo__features" variants={fadeUp}>
          {FEATURES.map((text, i) => (
            <li key={text}>
              <span className="auth-promo__feature-index">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span>{text}</span>
            </li>
          ))}
        </motion.ul>

        <motion.div className="auth-promo__profile" variants={fadeUp}>
          <div className="auth-promo__profile-main">
            <span className="auth-promo__avatar">You</span>
            <div>
              <p className="auth-promo__profile-name">Your profile</p>
              <p className="auth-promo__profile-role">Skills, resume, proof of work</p>
            </div>
          </div>
          <span className="auth-promo__match-badge">Ranked</span>
        </motion.div>

        <motion.p className="auth-promo__footnote" variants={fadeUp}>
          Onboarding students across Engineering, Business, and Healthcare.
        </motion.p>
      </div>
    </motion.aside>
  );
}
