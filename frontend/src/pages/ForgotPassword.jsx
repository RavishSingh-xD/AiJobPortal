import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { requestPasswordReset } from "../services/authService";
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
      <div className="page-inner auth-form-column">
        <Link to="/login" className="auth-back">Back to log in</Link>

        <div className="auth-form-card">
          <h1 className="auth-form-card__title">Forgot password</h1>
          <p className="auth-form-card__subtitle">
            We&apos;ll email a reset code if this address has an account.
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
            <button type="submit" className="auth-submit" disabled={loading}>
              {loading ? "Sending…" : "Send reset code"}
            </button>
          </form>

          <p className="auth-footer">
            Remembered it? <Link to="/login">Log in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
