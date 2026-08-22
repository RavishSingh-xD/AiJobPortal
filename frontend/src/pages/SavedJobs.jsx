import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { listSavedJobs, unsaveJob } from "../services/apiClient";
import AnimatedButton from "../components/AnimatedButton";
import NavBar from "../components/NavBar";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import { MotionListItem } from "../components/motionConfig";
import { apiErrorMessage } from "../utils/errors";

const stateVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { duration: 0.2, ease: [0.16, 1, 0.3, 1] },
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
        <PageHeader
          label="Saved"
          title="Saved roles"
          subtitle="Bookmarked opportunities to review later."
        />

        <AnimatePresence mode="wait">
          {uiState === "loading" && (
            <motion.div key="loading" variants={stateVariants} initial="hidden" animate="visible" exit="hidden">
              <EmptyState variant="loading" loading title="Loading saved roles" />
            </motion.div>
          )}

          {uiState === "empty" && (
            <motion.div key="empty" variants={stateVariants} initial="hidden" animate="visible" exit="hidden">
              <EmptyState
                title="Nothing saved yet"
                text="Save a role from Find Roles and it will appear here."
              />
            </motion.div>
          )}

          {uiState === "error" && (
            <motion.div key="error" variants={stateVariants} initial="hidden" animate="visible" exit="hidden">
              <EmptyState
                variant="error"
                title="Could not load saved roles"
                text="We couldn't load your saved roles right now."
                action={<AnimatedButton onClick={loadSaved}>Try again</AnimatedButton>}
              />
            </motion.div>
          )}

          {uiState === "ready" && (
            <motion.div
              key="ready"
              className="ledger"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              {rowError && <div className="form-error" style={{ margin: "0.75rem 1rem" }}>{rowError}</div>}
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
  );
}
