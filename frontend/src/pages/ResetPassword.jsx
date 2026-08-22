import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { confirmPasswordReset } from "../services/authService";
import GlassCard from "../components/GlassCard";
import AnimatedButton from "../components/AnimatedButton";

export default function ResetPassword() {
  const navigate = useNavigate();
  const location = useLocation();
  const presetEmail =
    typeof location.state?.email === "string" ? location.state.email : "";

  const [email, setEmail] = useState(presetEmail);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await confirmPasswordReset(email, code, password);
      navigate("/login");
    } catch (err) {
      setError(err.message || "Could not reset your password. Check the code.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page page--auth">
      <div className="page-inner">
        <GlassCard>
          <div className="glass-card__header">
            <h1 className="glass-card__title">Choose a new password</h1>
            <p className="glass-card__subtitle">
              Enter the code from your email and a new password. If you don&apos;t
              see the email, check your spam or junk folder.
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
            <div className="form-group">
              <label className="form-label" htmlFor="code">
                Reset code
              </label>
              <input
                id="code"
                className="form-input"
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="6-digit code"
                required
                disabled={loading}
                autoComplete="one-time-code"
              />
              <p className="form-hint">
                Reset codes can end up in spam or junk — check there if your
                inbox is empty.
              </p>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="password">
                New password
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
              {loading ? "Updating…" : "Reset password"}
            </AnimatedButton>
          </form>

          <p className="form-link">
            Back to <Link to="/login">log in</Link>
          </p>
        </GlassCard>
      </div>
    </div>
  );
}
