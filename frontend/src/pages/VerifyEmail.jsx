import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { resendSignupCode, verifyOtp } from "../services/authService";

export default function VerifyEmail() {
  const navigate = useNavigate();
  const location = useLocation();
  const presetEmail =
    typeof location.state?.email === "string" ? location.state.email : "";
  const presetMessage =
    typeof location.state?.message === "string" ? location.state.message : "";

  const [email, setEmail] = useState(presetEmail);
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState(presetMessage || "");

  const SPAM_OTP_NOTICE =
    "If you don't see the OTP in your inbox, check your spam or junk folder — verification codes often land there.";

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
      setInfo("A new OTP is on its way. Check your inbox and spam folder if it doesn't appear.");
    } catch (err) {
      setError(err.message || "Could not resend the code. Try again.");
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="page page--auth">
      <div className="page-inner auth-form-column">
        <Link to="/login" className="auth-back">Back to log in</Link>

        <div className="auth-form-card">
          <h1 className="auth-form-card__title">Verify email</h1>
          <p className="auth-form-card__subtitle">
            Enter the confirmation code we emailed you to activate your account.
          </p>

          <p className="form-notice" role="note">
            <strong>Check spam for your OTP.</strong> {SPAM_OTP_NOTICE}
          </p>

          {error && <div className="auth-error">{error}</div>}
          {info && !error && <p className="form-info">{info}</p>}

          <form onSubmit={handleVerify}>
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
                disabled={loading || resending}
              />
            </div>
            <div className="auth-field">
              <label htmlFor="code">Verification code</label>
              <input
                id="code"
                className="auth-input auth-input--no-icon"
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="6-digit code"
                required
                disabled={loading || resending}
                autoComplete="one-time-code"
              />
              <p className="form-hint">
                Still nothing? Look in spam, junk, and promotions before you resend.
              </p>
            </div>
            <button type="submit" className="auth-submit" disabled={loading || resending}>
              {loading ? "Verifying…" : "Verify email"}
            </button>
          </form>

          <p className="auth-footer">
            <button
              type="button"
              className="form-link__button"
              onClick={handleResend}
              disabled={loading || resending}
            >
              {resending ? "Sending…" : "Resend code"}
            </button>
          </p>
          <p className="auth-footer">
            Already verified? <Link to="/login">Log in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
