import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { getUserProfile } from "../services/authService";
import {
  listApplications,
  listSavedJobs,
  getProfile,
  updateProfile,
} from "../services/apiClient";
import GlassCard from "../components/GlassCard";
import AnimatedButton from "../components/AnimatedButton";
import NavBar from "../components/NavBar";
import PageHeader from "../components/PageHeader";
import { EASE_OUT, DURATION } from "../components/motionConfig";
import { apiErrorMessage } from "../utils/errors";

function formatVerificationStatus(status) {
  if (!status) return { label: "Unknown", variant: "default" };

  const labels = {
    verified: "Verified",
    pending_review: "Pending review",
    rejected: "Rejected",
  };

  return {
    label: labels[status] ?? status.replace(/_/g, " "),
    variant: labels[status] ? status : "default",
  };
}

function StatCard({
  label,
  value,
  delay,
  expanded,
  onToggle,
  extraCollapsed = null,
  children,
}) {
  const reduced = useReducedMotion();

  return (
    <GlassCard
      className={`glass-card--stat glass-card--clickable stat-card${
        expanded ? " stat-card--open" : ""
      }`}
      delay={delay}
    >
      <button
        type="button"
        className="stat-card__header"
        onClick={onToggle}
        aria-expanded={expanded}
      >
        <div className="stat-card__icon" aria-hidden="true" />
        <div className="stat-card__summary">
          <p className="stat-card__label">{label}</p>
          <p className="stat-card__value">{value}</p>
        </div>
        <motion.span
          className="stat-card__chevron"
          aria-hidden="true"
          animate={{ rotate: expanded ? 180 : 0 }}
          transition={{ duration: DURATION, ease: EASE_OUT }}
        >
          ▾
        </motion.span>
      </button>
      {extraCollapsed}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="expand"
            className="stat-card__expand-motion"
            initial={reduced ? { opacity: 0 } : { height: 0, opacity: 0 }}
            animate={reduced ? { opacity: 1 } : { height: "auto", opacity: 1 }}
            exit={reduced ? { opacity: 0 } : { height: 0, opacity: 0 }}
            transition={{ duration: DURATION, ease: EASE_OUT }}
            style={{ overflow: "hidden" }}
          >
            <div className="stat-card__expand-inner">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </GlassCard>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [userAttributes, setUserAttributes] = useState({
    name: "",
    email: "",
    verificationStatus: "",
  });
  const [applicationsCount, setApplicationsCount] = useState(null);
  const [savedCount, setSavedCount] = useState(null);
  const [statsError, setStatsError] = useState("");

  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [completionPct, setCompletionPct] = useState(null);
  const [profileUiState, setProfileUiState] = useState("loading");
  const [profileSaving, setProfileSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});
  const [profileError, setProfileError] = useState("");
  const [openCard, setOpenCard] = useState({
    applications: false,
    saved: false,
    profile: false,
  });

  const toggleCard = (key) => {
    setOpenCard((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  useEffect(() => {
    async function loadUser() {
      const profile = await getUserProfile();
      setUserAttributes({
        name: profile.name || profile.email || "",
        email: profile.email || "",
        verificationStatus: profile.verificationStatus ?? "",
      });
    }
    loadUser();
  }, []);

  useEffect(() => {
    async function loadStats() {
      setStatsError("");
      try {
        const [applicationsData, savedData] = await Promise.all([
          listApplications(),
          listSavedJobs(),
        ]);
        setApplicationsCount(
          Array.isArray(applicationsData.applications)
            ? applicationsData.applications.length
            : 0
        );
        setSavedCount(
          Array.isArray(savedData.savedJobs) ? savedData.savedJobs.length : 0
        );
      } catch (err) {
        setStatsError(
          apiErrorMessage(err, "Could not load your application and saved counts.")
        );
        setApplicationsCount("—");
        setSavedCount("—");
      }
    }
    loadStats();
  }, []);

  useEffect(() => {
    async function loadProfile() {
      setProfileUiState("loading");
      setProfileError("");
      try {
        const data = await getProfile();
        setLinkedinUrl(data.linkedinUrl || "");
        setGithubUrl(data.githubUrl || "");
        setCompletionPct(
          typeof data.completionPct === "number" ? data.completionPct : 0
        );
        setProfileUiState("ready");
      } catch (err) {
        setProfileError(apiErrorMessage(err, "Could not load your profile."));
        setProfileUiState("error");
      }
    }
    loadProfile();
  }, []);

  const handleSaveProfile = async (e) => {
    e.preventDefault();
    setProfileSaving(true);
    setFieldErrors({});
    setProfileError("");
    try {
      const data = await updateProfile({ linkedinUrl, githubUrl });
      setLinkedinUrl(data.linkedinUrl || "");
      setGithubUrl(data.githubUrl || "");
      setCompletionPct(
        typeof data.completionPct === "number" ? data.completionPct : 0
      );
    } catch (err) {
      const errors = err.response?.data?.errors;
      if (errors && typeof errors === "object") {
        setFieldErrors(errors);
      } else {
        setProfileError(apiErrorMessage(err, "Could not save your profile."));
      }
    } finally {
      setProfileSaving(false);
    }
  };

  const badge = formatVerificationStatus(userAttributes.verificationStatus);

  return (
    <div className="page page--dashboard">
      <div className="dashboard">
        <NavBar />

        <div className="dashboard-welcome">
          <PageHeader
            label="Dashboard"
            title={`Welcome back${userAttributes.name ? `, ${userAttributes.name}` : ""}`}
            subtitle={
              userAttributes.verificationStatus
                ? undefined
                : "Your command center for roles, matches, and applications."
            }
            className="dashboard-welcome__header"
          />
          {userAttributes.verificationStatus && (
            <span className={`status-badge status-badge--${badge.variant}`}>
              {badge.label}
            </span>
          )}
        </div>

        {statsError && <div className="form-error">{statsError}</div>}

        <div className="dashboard-stats">
          <StatCard
            label="Applications"
            value={applicationsCount == null ? "…" : applicationsCount}
            delay={0.1}
            expanded={openCard.applications}
            onToggle={() => toggleCard("applications")}
          >
            <AnimatedButton
              className="btn--compact"
              onClick={() => navigate("/applications")}
            >
              View all
            </AnimatedButton>
          </StatCard>
          <StatCard
            label="Saved"
            value={savedCount == null ? "…" : savedCount}
            delay={0.2}
            expanded={openCard.saved}
            onToggle={() => toggleCard("saved")}
          >
            <AnimatedButton
              className="btn--compact"
              onClick={() => navigate("/saved-jobs")}
            >
              View all
            </AnimatedButton>
          </StatCard>
          <StatCard
            label="Profile completion"
            value={
              profileUiState === "loading"
                ? "…"
                : profileUiState === "ready"
                  ? `${completionPct}%`
                  : "—"
            }
            delay={0.3}
            expanded={openCard.profile}
            onToggle={() => toggleCard("profile")}
            extraCollapsed={
              profileUiState === "ready" ? (
                <div
                  className="profile-progress profile-progress--slim"
                  role="progressbar"
                  aria-valuenow={completionPct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div
                    className="profile-progress__bar"
                    style={{ width: `${completionPct}%` }}
                  />
                </div>
              ) : null
            }
          >
            {profileUiState === "error" && (
              <div className="form-error">{profileError}</div>
            )}
            {profileUiState === "ready" && (
              <>
                <div
                  className="profile-progress"
                  role="progressbar"
                  aria-valuenow={completionPct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div
                    className="profile-progress__bar"
                    style={{ width: `${completionPct}%` }}
                  />
                </div>
                <form className="profile-form" onSubmit={handleSaveProfile}>
                  <div className="form-group" style={{ marginBottom: "0.75rem" }}>
                    <label className="form-label" htmlFor="linkedinUrl">
                      LinkedIn URL
                    </label>
                    <input
                      id="linkedinUrl"
                      className="form-input"
                      type="url"
                      value={linkedinUrl}
                      onChange={(e) => setLinkedinUrl(e.target.value)}
                      placeholder="https://linkedin.com/in/you"
                      disabled={profileSaving}
                    />
                    {fieldErrors.linkedinUrl && (
                      <p className="form-error" style={{ marginTop: "0.5rem", marginBottom: 0 }}>
                        {fieldErrors.linkedinUrl}
                      </p>
                    )}
                  </div>
                  <div className="form-group" style={{ marginBottom: "0.75rem" }}>
                    <label className="form-label" htmlFor="githubUrl">
                      GitHub URL
                    </label>
                    <input
                      id="githubUrl"
                      className="form-input"
                      type="url"
                      value={githubUrl}
                      onChange={(e) => setGithubUrl(e.target.value)}
                      placeholder="https://github.com/you"
                      disabled={profileSaving}
                    />
                    {fieldErrors.githubUrl && (
                      <p className="form-error" style={{ marginTop: "0.5rem", marginBottom: 0 }}>
                        {fieldErrors.githubUrl}
                      </p>
                    )}
                  </div>
                  {profileError && <div className="form-error">{profileError}</div>}
                  <AnimatedButton
                    type="submit"
                    className="btn--compact"
                    loading={profileSaving}
                    disabled={profileSaving}
                  >
                    {profileSaving ? "Saving…" : "Save"}
                  </AnimatedButton>
                </form>
              </>
            )}
          </StatCard>
        </div>

        <div className="dashboard-cta-grid">
          <div className="app-panel">
            <div className="dashboard-coming-soon">
              <p className="micro-label">Browse</p>
              <h2 className="dashboard-coming-soon__title">Find roles manually</h2>
              <p className="dashboard-coming-soon__text">
                Search opportunities across Engineering, Healthcare, and Business.
              </p>
              <div className="dashboard-cta-grid__action">
                <AnimatedButton secondary className="btn--compact" onClick={() => navigate("/jobs")}>
                  Browse roles
                </AnimatedButton>
              </div>
            </div>
          </div>

          <div className="app-panel dashboard-cta-card--featured">
            <div className="dashboard-coming-soon">
              <p className="micro-label">Match</p>
              <h2 className="dashboard-coming-soon__title">AI-ranked recommendation</h2>
              <p className="dashboard-coming-soon__text">
                Submit your resume, take a quick domain test, and get a ranked
                best-fit recommendation.
              </p>
              <div className="dashboard-cta-grid__action">
                <AnimatedButton className="btn--compact" onClick={() => navigate("/match")}>
                  Start matching
                </AnimatedButton>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
