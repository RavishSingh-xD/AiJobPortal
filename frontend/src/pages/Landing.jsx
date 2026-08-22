import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import AnimatedButton from "../components/AnimatedButton";
import { fadeUp, staggerContainer } from "../components/motionConfig";

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="page page--landing">
      <motion.div
        className="landing"
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
      >
        <motion.p className="landing__brand" variants={fadeUp}>
          Avyukt
        </motion.p>
        <motion.h1 className="landing__title" variants={fadeUp}>
          Opportunities that fit you
        </motion.h1>
        <motion.p className="landing__lede" variants={fadeUp}>
          Ranked matches from your resume and a short domain test — apply with a
          profile that already knows who you are.
        </motion.p>
        <motion.div className="landing__card surface" variants={fadeUp}>
          <div className="landing__actions">
            <AnimatedButton type="button" className="btn--compact" onClick={() => navigate("/signup")}>
              Create account
            </AnimatedButton>
            <AnimatedButton
              type="button"
              secondary
              className="btn--compact"
              onClick={() => navigate("/login")}
            >
              Log in
            </AnimatedButton>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}
