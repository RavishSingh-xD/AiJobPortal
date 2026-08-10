import { useState } from "react";
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
  const [submitted, setSubmitted] = useState(false);

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

      setSubmitted(true);
    } catch (err) {
      setError(err.message || "Upload failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <div className="page-inner page-inner--wide">
        <GlassCard>
          <AnimatePresence mode="wait">
            {submitted ? (
              <motion.div
                key="success"
                className="success-state"
                variants={successVariants}
                initial="hidden"
                animate="visible"
              >
                <div className="success-state__icon" aria-hidden="true">
                  ✓
                </div>
                <h2 className="success-state__title">Verification submitted</h2>
                <p className="success-state__text">
                  Your documents are under review. We&apos;ll notify you once
                  your identity has been verified.
                </p>
                <AnimatedButton onClick={() => navigate("/dashboard")}>
                  Go to dashboard
                </AnimatedButton>
              </motion.div>
            ) : (
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
          </AnimatePresence>
        </GlassCard>
      </div>
    </div>
  );
}
