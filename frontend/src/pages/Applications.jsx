import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { listApplications } from "../services/apiClient";
import AnimatedButton from "../components/AnimatedButton";
import NavBar from "../components/NavBar";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import { MotionListItem } from "../components/motionConfig";

const stateVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { duration: 0.2, ease: [0.16, 1, 0.3, 1] },
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
        <PageHeader
          label="Track"
          title="Applications"
          subtitle="Roles you've applied to from Avyukt."
        />

        <AnimatePresence mode="wait">
          {uiState === "loading" && (
            <motion.div key="loading" variants={stateVariants} initial="hidden" animate="visible" exit="hidden">
              <EmptyState variant="loading" loading title="Loading applications" />
            </motion.div>
          )}

          {uiState === "empty" && (
            <motion.div key="empty" variants={stateVariants} initial="hidden" animate="visible" exit="hidden">
              <EmptyState
                title="No applications yet"
                text="When you apply from Find Roles, they'll show up here."
              />
            </motion.div>
          )}

          {uiState === "error" && (
            <motion.div key="error" variants={stateVariants} initial="hidden" animate="visible" exit="hidden">
              <EmptyState
                variant="error"
                title="Could not load applications"
                text="We couldn't load your applications right now."
                action={<AnimatedButton onClick={loadApplications}>Try again</AnimatedButton>}
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
                  <p className="match-listing-card__meta tabular-nums">
                    {row.status || "applied"} · {formatAppliedAt(row.appliedAt)}
                  </p>
                </MotionListItem>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
