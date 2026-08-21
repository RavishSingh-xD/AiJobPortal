import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { listApplications } from "../services/apiClient";
import GlassCard from "../components/GlassCard";
import AnimatedButton from "../components/AnimatedButton";
import NavBar from "../components/NavBar";
import { LoadingPulse, MotionListItem } from "../components/motionConfig";

const stateVariants = {
  hidden: { opacity: 0, scale: 0.92 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] },
  },
};

function formatAppliedAt(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function Applications() {
  const [uiState, setUiState] = useState("loading");
  const [applications, setApplications] = useState([]);

  const loadApplications = async () => {
    setUiState("loading");
    try {
      const data = await listApplications();
      const items = Array.isArray(data.applications) ? data.applications : [];
      setApplications(items);
      setUiState(items.length > 0 ? "ready" : "empty");
    } catch {
      setUiState("error");
    }
  };

  useEffect(() => {
    loadApplications();
  }, []);

  return (
    <div className="page page--dashboard">
      <div className="dashboard">
        <NavBar />
        <GlassCard className="glass-card--compact" hover={false}>
          <div className="glass-card__header">
            <h1 className="glass-card__title">Applications</h1>
            <p className="glass-card__subtitle">
              Roles you&apos;ve applied to from Avyukt.
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
                <h2 className="success-state__title">Loading your applications</h2>
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
                  📋
                </div>
                <h2 className="success-state__title">No applications yet</h2>
                <p className="success-state__text">
                  When you apply from Find Roles, they&apos;ll show up here.
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
                  We couldn&apos;t load your applications right now.
                </p>
                <AnimatedButton onClick={loadApplications}>Try again</AnimatedButton>
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
                {applications.map((row, index) => (
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
                    <p className="match-listing-card__meta">
                      {row.status || "applied"} · {formatAppliedAt(row.appliedAt)}
                    </p>
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
