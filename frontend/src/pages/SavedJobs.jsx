import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { listSavedJobs, unsaveJob } from "../services/apiClient";
import GlassCard from "../components/GlassCard";
import AnimatedButton from "../components/AnimatedButton";
import NavBar from "../components/NavBar";
import { LoadingPulse, MotionListItem } from "../components/motionConfig";
import { apiErrorMessage } from "../utils/errors";

const stateVariants = {
  hidden: { opacity: 0, scale: 0.92 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] },
  },
};

export default function SavedJobs() {
  const [uiState, setUiState] = useState("loading");
  const [savedJobs, setSavedJobs] = useState([]);
  const [unsavingId, setUnsavingId] = useState(null);
  const [rowError, setRowError] = useState("");

  const loadSaved = async () => {
    setUiState("loading");
    setRowError("");
    try {
      const data = await listSavedJobs();
      const items = Array.isArray(data.savedJobs) ? data.savedJobs : [];
      setSavedJobs(items);
      setUiState(items.length > 0 ? "ready" : "empty");
    } catch {
      setUiState("error");
    }
  };

  useEffect(() => {
    loadSaved();
  }, []);

  const handleUnsave = async (canonicalId) => {
    if (!canonicalId || unsavingId) {
      return;
    }
    setUnsavingId(canonicalId);
    setRowError("");
    try {
      await unsaveJob(canonicalId);
      setSavedJobs((prev) => {
        const next = prev.filter((row) => row.canonicalId !== canonicalId);
        setUiState(next.length > 0 ? "ready" : "empty");
        return next;
      });
    } catch (err) {
      setRowError(apiErrorMessage(err, "Could not unsave this role."));
    } finally {
      setUnsavingId(null);
    }
  };

  return (
    <div className="page page--dashboard">
      <div className="dashboard">
        <NavBar />
        <GlassCard className="glass-card--compact" hover={false}>
          <div className="glass-card__header">
            <h1 className="glass-card__title">Saved opportunities</h1>
            <p className="glass-card__subtitle">
              Roles you&apos;ve bookmarked to come back to later.
            </p>
          </div>
        </GlassCard>

        <div style={{ marginTop: "1.5rem" }}>
          <AnimatePresence mode="wait">
            {uiState === "loading" && (
              <motion.div
                key="loading"
                className="success-state"
                variants={stateVariants}
                initial="hidden"
                animate="visible"
                exit="hidden"
              >
                <LoadingPulse>
                  <div className="success-state__icon" aria-hidden="true">
                    ⏳
                  </div>
                </LoadingPulse>
                <h2 className="success-state__title">Loading saved roles</h2>
              </motion.div>
            )}

            {uiState === "empty" && (
              <motion.div
                key="empty"
                className="success-state"
                variants={stateVariants}
                initial="hidden"
                animate="visible"
                exit="hidden"
              >
                <div className="success-state__icon" aria-hidden="true">
                  ⭐
                </div>
                <h2 className="success-state__title">Nothing saved yet</h2>
                <p className="success-state__text">
                  Save a role from Find Roles and it will appear here.
                </p>
              </motion.div>
            )}

            {uiState === "error" && (
              <motion.div
                key="error"
                className="success-state"
                variants={stateVariants}
                initial="hidden"
                animate="visible"
                exit="hidden"
              >
                <div className="success-state__icon" aria-hidden="true">
                  ⚠️
                </div>
                <h2 className="success-state__title">Something went wrong</h2>
                <p className="success-state__text">
                  We couldn&apos;t load your saved roles right now.
                </p>
                <AnimatedButton onClick={loadSaved}>Try again</AnimatedButton>
              </motion.div>
            )}

            {uiState === "ready" && (
              <motion.div
                key="ready"
                className="match-listings"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              >
                {rowError && <div className="form-error">{rowError}</div>}
                {savedJobs.map((row, index) => (
                  <MotionListItem
                    key={row.canonicalId}
                    index={index}
                    className="match-listing-card"
                  >
                    <h3 className="match-listing-card__title">
                      {row.jobTitle || "Untitled role"}
                    </h3>
                    <p className="match-listing-card__meta">
                      {[row.company, row.domain].filter(Boolean).join(" · ")}
                    </p>
                    <div className="job-card__actions">
                      <AnimatedButton
                        secondary
                        className="btn--compact"
                        loading={unsavingId === row.canonicalId}
                        disabled={unsavingId === row.canonicalId}
                        onClick={() => handleUnsave(row.canonicalId)}
                      >
                        Unsave
                      </AnimatedButton>
                    </div>
                  </MotionListItem>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
