import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { loginUser, getUserProfile, PendingVerificationError } from "../services/authService";
import AuthMarketingPanel from "../components/AuthMarketingPanel";
import { getPostLoginPath } from "../utils/verification";

function MailIcon() {
  return (
    <svg className="auth-input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
      <path d="M4 7l8 5 8-5M4 7v10a2 2 0 002 2h12a2 2 0 002-2V7a2 2 0 00-2-2H6a2 2 0 00-2 2z" />
    </svg>
  );
}

function EyeIcon({ open }) {
  if (open) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
        <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
      <path d="M3 3l18 18M10.58 10.58a2 2 0 002.83 2.83M9.88 5.09A10.94 10.94 0 0112 5c7 0 10 7 10 7a18.45 18.45 0 01-5.06 5.94M6.1 6.1A18.45 18.45 0 002 12s3 7 10 7a10.94 10.94 0 014.12-.88" />
    </svg>
  );
}

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await loginUser(email, password);
      const profile = await getUserProfile();
      navigate(getPostLoginPath(profile));
    } catch (err) {
      if (err instanceof PendingVerificationError) {
        navigate("/verify-email", {
          state: {
            email: err.email || email,
            message: err.message,
          },
        });
        return;
      }
      const errName = err?.name || err?.code || "";
      if (errName === "UserNotConfirmedException") {
        navigate("/verify-email", {
          state: {
            email,
            message:
              "Your email isn't verified yet. Enter the code we sent you (check spam too).",
          },
        });
        return;
      }
      setError(err.message || "Login failed. Please check your credentials.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page page--auth-split">
      <div className="auth-split">
        <AuthMarketingPanel />

        <div className="auth-form-column">
          <Link to="/" className="auth-back">← Back to Avyukt</Link>

          <div className="auth-form-card">
            <h1 className="auth-form-card__title">Welcome back</h1>
            <p className="auth-form-card__subtitle">
              Sign in to access your opportunities dashboard
            </p>

            {error && <div className="auth-error">{error}</div>}

            <form onSubmit={handleLogin}>
              <div className="auth-field">
                <label htmlFor="email">Email</label>
                <div className="auth-input-wrap">
                  <MailIcon />
                  <input
                    id="email"
                    className="auth-input"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@college.edu"
                    required
                    disabled={loading}
                    autoComplete="email"
                  />
                </div>
              </div>

              <div className="auth-field">
                <label htmlFor="password">Password</label>
                <div className="auth-input-wrap">
                  <input
                    id="password"
                    className="auth-input auth-input--no-icon"
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Your password"
                    required
                    disabled={loading}
                    autoComplete="current-password"
                    style={{ paddingRight: "2.75rem" }}
                  />
                  <button
                    type="button"
                    className="auth-input-toggle"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    <EyeIcon open={showPassword} />
                  </button>
                </div>
              </div>

              <Link to="/forgot-password" className="auth-forgot">
                Forgot password?
              </Link>

              <button type="submit" className="auth-submit" disabled={loading}>
                {loading ? "Signing in…" : "Log in"}
              </button>
            </form>

            <p className="auth-footer">
              Don&apos;t have an account? <Link to="/signup">Sign up</Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
