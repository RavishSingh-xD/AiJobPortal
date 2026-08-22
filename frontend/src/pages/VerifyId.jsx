import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { getUserProfile } from "../services/authService";
import { requestUploadUrl, uploadFileToS3 } from "../services/apiClient";
import AnimatedButton from "../components/AnimatedButton";
import AuthFormShell from "../components/AuthFormShell";
import { EASE_OUT } from "../components/motionConfig";

const successVariants = {
  hidden: { opacity: 0, y: 8 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.28, ease: EASE_OUT },
  },
  exit: { opacity: 0, y: -6, transition: { duration: 0.18, ease: EASE_OUT } },
};

function FileDropZone({ id, label, file, onChange, disabled }) {
  return (
    <motion.div
      className={`drop-zone ${file ? "drop-zone--has-file" : ""}`}
      whileHover={disabled ? undefined : { y: -1 }}
      transition={{ duration: 0.16, ease: EASE_OUT }}
    >
      <input
        id={id}
        className="drop-zone__input"
        type="file"
        accept="image/jpeg,image/jpg,image/png"
        onChange={onChange}
        disabled={disabled}
      />
      <span className="drop-zone__icon" aria-hidden="true">
        {file ? "OK" : "Upload"}
      </span>
      {file ? (
        <span className="drop-zone__filename">{file.name}</span>
      ) : (
        <span className="drop-zone__label">{label}</span>
      )}
    </motion.div>
  );
}

export default function VerifyId() {
  const navigate = useNavigate();
  const [selfie, setSelfie] = useState(null);
  const [idCard, setIdCard] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [phase, setPhase] = useState("form");
  const pollCountRef = useRef(0);
  const pollTimerRef = useRef(null);

  const stopPolling = () => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  };

  useEffect(() => {
    async function loadStatus() {
      try {
        const profile = await getUserProfile();
        if (profile.verificationStatus === "rejected") {
          setPhase("rejected");
        } else if (profile.verificationStatus === "verified") {
          setPhase("verified");
        }
      } catch {
        // Stay on form; ProtectedRoute already requires auth
      }
    }
    loadStatus();
    return stopPolling;
  }, []);

  const startPolling = () => {
    stopPolling();
    pollCountRef.current = 0;
    setPhase("polling");

    pollTimerRef.current = setInterval(async () => {
      pollCountRef.current += 1;

      try {
        const profile = await getUserProfile();
        const status = profile.verificationStatus;

        if (status === "verified") {
          stopPolling();
          setPhase("verified");
          return;
        }

        if (status === "rejected") {
          stopPolling();
          setPhase("rejected");
          return;
        }
      } catch {
        // Transient failure — retry on next tick unless cap is reached
      }

      if (pollCountRef.current >= 40) {
        stopPolling();
        setPhase("timeout");
      }
    }, 3000);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selfie || !idCard) {
      setError("Please upload both a selfie and your ID card.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const profile = await getUserProfile();
      const userId = profile.userId;

      const selfieUrl = await requestUploadUrl(userId, "selfie");
      await uploadFileToS3(selfieUrl.uploadUrl, selfie);

      const idCardUrl = await requestUploadUrl(userId, "id_card");
      await uploadFileToS3(idCardUrl.uploadUrl, idCard);

      startPolling();
    } catch (err) {
      setError(err.message || "Upload failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthFormShell backTo="/dashboard" backLabel="Back" wide>
      <AnimatePresence mode="wait">
            {phase === "form" && (
              <motion.div
                key="form"
                variants={successVariants}
                initial="hidden"
                animate="visible"
                exit="exit"
              >
                <div className="glass-card__header">
                  <h1 className="auth-form-card__title">Verify identity</h1>
                  <p className="auth-form-card__subtitle">
                    Upload a selfie and a photo of your college ID card. We
                    automatically compare your face and verify the name on your
                    ID matches your account name.
                  </p>
                </div>

                {error && <div className="form-error">{error}</div>}

                <form onSubmit={handleSubmit}>
                  <div className="form-group">
                    <label className="form-label" htmlFor="selfie">
                      Selfie
                    </label>
                    <FileDropZone
                      id="selfie"
                      label="Click or drag to upload your selfie"
                      file={selfie}
                      onChange={(e) => setSelfie(e.target.files?.[0] ?? null)}
                      disabled={loading}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label" htmlFor="idCard">
                      College ID card
                    </label>
                    <FileDropZone
                      id="idCard"
                      label="Click or drag to upload your ID card"
                      file={idCard}
                      onChange={(e) => setIdCard(e.target.files?.[0] ?? null)}
                      disabled={loading}
                    />
                  </div>

                  <AnimatedButton type="submit" loading={loading}>
                    {loading ? "Uploading…" : "Submit for review"}
                  </AnimatedButton>
                </form>
              </motion.div>
            )}

            {phase === "polling" && (
              <motion.div
                key="polling"
                className="empty-state"
                variants={successVariants}
                initial="hidden"
                animate="visible"
                exit="exit"
              >
                <p className="micro-label">Processing</p>
                <h2 className="empty-state__title">Verifying identity</h2>
                <p className="empty-state__text">
                  Your selfie and ID photo are being compared automatically,
                  including a name check on your ID card. This usually takes
                  just a few seconds.
                </p>
              </motion.div>
            )}

            {phase === "verified" && (
              <motion.div
                key="verified"
                className="empty-state"
                variants={successVariants}
                initial="hidden"
                animate="visible"
                exit="exit"
              >
                <p className="micro-label">Verified</p>
                <h2 className="empty-state__title">Identity confirmed</h2>
                <p className="empty-state__text">
                  Your identity has been confirmed. You can now apply for
                  opportunities on Avyukt.
                </p>
                <AnimatedButton onClick={() => navigate("/dashboard")}>
                  Go to dashboard
                </AnimatedButton>
              </motion.div>
            )}

            {phase === "rejected" && (
              <motion.div
                key="rejected"
                className="empty-state empty-state--error"
                variants={successVariants}
                initial="hidden"
                animate="visible"
                exit="exit"
              >
                <p className="micro-label">Failed</p>
                <h2 className="empty-state__title">Verification failed</h2>
                <p className="empty-state__text">
                  Your selfie and ID photo didn&apos;t match, the name on your ID
                  didn&apos;t match your account, or the images weren&apos;t clear
                  enough. Use the same full name as on your ID, a well-lit
                  front-facing selfie, and a sharp photo of the card.
                </p>
                <AnimatedButton
                  onClick={() => {
                    setSelfie(null);
                    setIdCard(null);
                    setPhase("form");
                  }}
                >
                  Try again
                </AnimatedButton>
              </motion.div>
            )}

            {phase === "timeout" && (
              <motion.div
                key="timeout"
                className="empty-state"
                variants={successVariants}
                initial="hidden"
                animate="visible"
                exit="exit"
              >
                <p className="micro-label">Pending</p>
                <h2 className="empty-state__title">Still processing</h2>
                <p className="empty-state__text">
                  Verification is taking longer than usual. Please wait a moment
                  and try submitting again if your status does not update.
                </p>
                <AnimatedButton
                  onClick={() => {
                    setSelfie(null);
                    setIdCard(null);
                    setPhase("form");
                  }}
                >
                  Try again
                </AnimatedButton>
              </motion.div>
            )}
          </AnimatePresence>
    </AuthFormShell>
  );
}
