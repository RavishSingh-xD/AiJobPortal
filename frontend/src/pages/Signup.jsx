import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { registerUser, verifyOtp } from "../services/authService";
import GlassCard from "../components/GlassCard";
import AnimatedButton from "../components/AnimatedButton";

const stepVariants = {
  initial: { opacity: 0, x: 24 },
  animate: { opacity: 1, x: 0, transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] } },
  exit: { opacity: 0, x: -24, transition: { duration: 0.25, ease: [0.22, 1, 0.36, 1] } },
};

export default function Signup() {
  const navigate = useNavigate();
  const [step, setStep] = useState("signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSignup = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await registerUser(email, password, name);
      if (result.isSignUpComplete) {
        navigate("/login");
      } else {
        setStep("otp");
      }
    } catch (err) {
      setError(err.message || "Sign up failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleOtp = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await verifyOtp(email, otp);
      navigate("/login");
    } catch (err) {
      setError(err.message || "Verification failed. Please check your code.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <div className="page-inner">
        <GlassCard>
          <div className="glass-card__header">
            <h1 className="glass-card__title">Create account</h1>
            <p className="glass-card__subtitle">
              {step === "signup"
                ? "Join AiJobPortal and start your internship journey"
                : "Enter the verification code sent to your email"}
            </p>
          </div>

          {error && <div className="form-error">{error}</div>}

          <AnimatePresence mode="wait">
            {step === "signup" ? (
              <motion.form
                key="signup-form"
                variants={stepVariants}
                initial="initial"
                animate="animate"
                exit="exit"
                onSubmit={handleSignup}
              >
                <div className="form-group">
                  <label className="form-label" htmlFor="name">
                    Full name
                  </label>
                  <input
                    id="name"
                    className="form-input"
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Jane Doe"
                    required
                    disabled={loading}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="email">
                    Email
                  </label>
                  <input
                    id="email"
                    className="form-input"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@college.edu"
                    required
                    disabled={loading}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="password">
                    Password
                  </label>
                  <input
                    id="password"
                    className="form-input"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="At least 8 characters"
                    required
                    minLength={8}
                    disabled={loading}
                  />
                </div>

                <AnimatedButton type="submit" loading={loading}>
                  {loading ? "Creating account…" : "Sign up"}
                </AnimatedButton>
              </motion.form>
            ) : (
              <motion.form
                key="otp-form"
                variants={stepVariants}
                initial="initial"
                animate="animate"
                exit="exit"
                onSubmit={handleOtp}
              >
                <div className="form-group">
                  <label className="form-label" htmlFor="otp">
                    Verification code
                  </label>
                  <input
                    id="otp"
                    className="form-input"
                    type="text"
                    value={otp}
                    onChange={(e) => setOtp(e.target.value)}
                    placeholder="6-digit code"
                    required
                    disabled={loading}
                    autoComplete="one-time-code"
                  />
                </div>

                <AnimatedButton type="submit" loading={loading}>
                  {loading ? "Verifying…" : "Verify email"}
                </AnimatedButton>
              </motion.form>
            )}
          </AnimatePresence>

          <p className="form-link">
            Already have an account? <Link to="/login">Log in</Link>
          </p>
        </GlassCard>
      </div>
    </div>
  );
}
