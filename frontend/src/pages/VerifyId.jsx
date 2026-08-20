import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { getUserProfile } from "../services/authService";
import { requestUploadUrl, uploadFileToS3 } from "../services/apiClient";
import GlassCard from "../components/GlassCard";
import AnimatedButton from "../components/AnimatedButton";

const successVariants = {
  hidden: { opacity: 0, scale: 0.92 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] },
  },
};

function FileDropZone({ id, label, icon, file, onChange, disabled }) {
  return (
    <div className={`drop-zone ${file ? "drop-zone--has-file" : ""}`}>
      <input
        id={id}
        className="drop-zone__input"
        type="file"
        accept="image/jpeg,image/jpg,image/png"
        onChange={onChange}
        disabled={disabled}
      />
      <span className="drop-zone__icon" aria-hidden="true">
        {file ? "✓" : icon}
      </span>
      {file ? (
        <span className="drop-zone__filename">{file.name}</span>
      ) : (
        <span className="drop-zone__label">{label}</span>
      )}
    </div>
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
    <div className="page page--auth">
      <div className="page-inner page-inner--wide">
        <GlassCard>
          <AnimatePresence mode="wait">
            {phase === "form" && (
              <motion.div
                key="form"
                initial={{ opacity: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.2 }}
              >
                <div className="glass-card__header">
                  <h1 className="glass-card__title">Verify your identity</h1>
                  <p className="glass-card__subtitle">
                    Upload a selfie and a photo of your college ID card for
                    manual verification
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
                      icon="📷"
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
                      icon="🪪"
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
                className="success-state"
                variants={successVariants}
                initial="hidden"
                animate="visible"
              >
                <div className="success-state__icon" aria-hidden="true">
                  ⏳
                </div>
                <h2 className="success-state__title">Verifying your identity</h2>
                <p className="success-state__text">
                  Your selfie and ID card are being compared automatically.
                  This usually takes just a few seconds.
                </p>
              </motion.div>
            )}

            {phase === "verified" && (
              <motion.div
                key="verified"
                className="success-state"
                variants={successVariants}
                initial="hidden"
                animate="visible"
              >
                <div className="success-state__icon" aria-hidden="true">
                  ✓
                </div>
                <h2 className="success-state__title">You&apos;re verified</h2>
                <p className="success-state__text">
                  Your identity has been confirmed. You can now apply for
                  opportunities on Avyukt.work.
                </p>
                <AnimatedButton onClick={() => navigate("/dashboard")}>
                  Go to dashboard
                </AnimatedButton>
              </motion.div>
            )}

            {phase === "rejected" && (
              <motion.div
                key="rejected"
                className="success-state"
                variants={successVariants}
                initial="hidden"
                animate="visible"
              >
                <div className="success-state__icon" aria-hidden="true">
                  ✕
                </div>
                <h2 className="success-state__title">
                  We couldn&apos;t verify your identity
                </h2>
                <p className="success-state__text">
                  Your selfie and ID photo didn&apos;t match, or the images
                  weren&apos;t clear enough. Try again with a well-lit,
                  front-facing selfie and a clear photo of your ID card.
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
                className="success-state"
                variants={successVariants}
                initial="hidden"
                animate="visible"
              >
                <div className="success-state__icon" aria-hidden="true">
                  ⏳
                </div>
                <h2 className="success-state__title">Still processing</h2>
                <p className="success-state__text">
                  Verification is taking longer than usual. Check your dashboard
                  shortly for an update on your status.
                </p>
                <AnimatedButton onClick={() => navigate("/dashboard")}>
                  Go to dashboard
                </AnimatedButton>
              </motion.div>
            )}
          </AnimatePresence>
        </GlassCard>
      </div>
    </div>
  );
}
