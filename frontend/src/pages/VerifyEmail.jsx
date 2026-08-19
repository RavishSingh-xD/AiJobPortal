import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { resendSignupCode, verifyOtp } from "../services/authService";
import GlassCard from "../components/GlassCard";
import AnimatedButton from "../components/AnimatedButton";

export default function VerifyEmail() {
  const navigate = useNavigate();
  const location = useLocation();
  const presetEmail =
    typeof location.state?.email === "string" ? location.state.email : "";

  const [email, setEmail] = useState(presetEmail);
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState(
    presetEmail ? "Enter the code we sent to your email." : ""
  );

  const handleVerify = async (e) => {
    e.preventDefault();
    setError("");
    setInfo("");
    setLoading(true);
    try {
      await verifyOtp(email, code);
      navigate("/login");
    } catch (err) {
      setError(err.message || "Verification failed. Please check your code.");
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (!email) {
      setError("Enter your email so we can resend a code.");
      return;
    }
    setError("");
    setInfo("");
    setResending(true);
    try {
      await resendSignupCode(email);
      setInfo("A new code is on its way.");
    } catch (err) {
      setError(err.message || "Could not resend the code. Try again.");
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="page page--auth">
      <div className="page-inner">
        <GlassCard>
          <div className="glass-card__header">
            <h1 className="glass-card__title">Verify your email</h1>
            <p className="glass-card__subtitle">
              Enter the confirmation code from your inbox to activate your
              account.
            </p>
          </div>

          {error && <div className="form-error">{error}</div>}
          {info && !error && <p className="form-info">{info}</p>}

          <form onSubmit={handleVerify}>
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
                disabled={loading || resending}
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="code">
                Verification code
              </label>
              <input
                id="code"
                className="form-input"
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="6-digit code"
                required
                disabled={loading || resending}
                autoComplete="one-time-code"
              />
            </div>
            <AnimatedButton type="submit" loading={loading} disabled={resending}>
              {loading ? "Verifying…" : "Verify email"}
            </AnimatedButton>
          </form>

          <p className="form-link">
            <button
              type="button"
              className="form-link__button"
              onClick={handleResend}
              disabled={loading || resending}
            >
              {resending ? "Sending…" : "Resend code"}
            </button>
          </p>
          <p className="form-link">
            Already verified? <Link to="/login">Log in</Link>
          </p>
        </GlassCard>
      </div>
    </div>
  );
}
