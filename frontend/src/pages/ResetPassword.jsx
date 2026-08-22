import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { confirmPasswordReset } from "../services/authService";
import AuthFormShell from "../components/AuthFormShell";
import { MotionSubmit } from "../components/AnimatedButton";

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
    <AuthFormShell>
      <h1 className="auth-form-card__title">New password</h1>
      <p className="auth-form-card__subtitle">
        Enter the code from your email and a new password. Check spam if the
        email isn&apos;t in your inbox.
      </p>

      {error && <div className="auth-error">{error}</div>}

      <form onSubmit={handleSubmit}>
        <div className="auth-field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            className="auth-input auth-input--no-icon"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@college.edu"
            required
            disabled={loading}
          />
        </div>
        <div className="auth-field">
          <label htmlFor="code">Reset code</label>
          <input
            id="code"
            className="auth-input auth-input--no-icon"
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="6-digit code"
            required
            disabled={loading}
            autoComplete="one-time-code"
          />
          <p className="form-hint">
            Reset codes can end up in spam or junk — check there if your inbox is empty.
          </p>
        </div>
        <div className="auth-field">
          <label htmlFor="password">New password</label>
          <input
            id="password"
            className="auth-input auth-input--no-icon"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
            required
            minLength={8}
            disabled={loading}
          />
        </div>
        <MotionSubmit disabled={loading}>
          {loading ? "Updating…" : "Reset password"}
        </MotionSubmit>
      </form>

      <p className="auth-footer">
        Back to <Link to="/login">log in</Link>
      </p>
    </AuthFormShell>
  );
}
