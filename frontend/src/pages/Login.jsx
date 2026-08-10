import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { loginUser, getUserProfile } from "../services/authService";
import GlassCard from "../components/GlassCard";
import AnimatedButton from "../components/AnimatedButton";

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await loginUser(email, password);
      const profile = await getUserProfile();
      if (
        profile.verificationType === "manual" &&
        profile.verificationStatus === "pending_review"
      ) {
        navigate("/verify-id");
      } else {
        navigate("/dashboard");
      }
    } catch (err) {
      setError(err.message || "Login failed. Please check your credentials.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <div className="page-inner">
        <GlassCard>
          <div className="glass-card__header">
            <h1 className="glass-card__title">Welcome back</h1>
            <p className="glass-card__subtitle">
              Sign in to access your internship dashboard
            </p>
          </div>

          {error && <div className="form-error">{error}</div>}

          <form onSubmit={handleLogin}>
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
                placeholder="Your password"
                required
                disabled={loading}
              />
            </div>

            <AnimatedButton type="submit" loading={loading}>
              {loading ? "Signing in…" : "Log in"}
            </AnimatedButton>
          </form>

          <p className="form-link">
            Don&apos;t have an account? <Link to="/signup">Sign up</Link>
          </p>
        </GlassCard>
      </div>
    </div>
  );
}
