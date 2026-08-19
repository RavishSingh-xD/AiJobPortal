import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { requestPasswordReset } from "../services/authService";
import GlassCard from "../components/GlassCard";
import AnimatedButton from "../components/AnimatedButton";

export default function ForgotPassword() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await requestPasswordReset(email);
      navigate("/reset-password", { state: { email } });
    } catch (err) {
      setError(err.message || "Could not start a password reset. Try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page page--auth">
      <div className="page-inner">
        <GlassCard>
          <div className="glass-card__header">
            <h1 className="glass-card__title">Forgot password</h1>
            <p className="glass-card__subtitle">
              We&apos;ll email a reset code if this address has an account.
            </p>
          </div>

          {error && <div className="form-error">{error}</div>}

          <form onSubmit={handleSubmit}>
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
            <AnimatedButton type="submit" loading={loading}>
              {loading ? "Sending…" : "Send reset code"}
            </AnimatedButton>
          </form>

          <p className="form-link">
            Remembered it? <Link to="/login">Log in</Link>
          </p>
        </GlassCard>
      </div>
    </div>
  );
}
