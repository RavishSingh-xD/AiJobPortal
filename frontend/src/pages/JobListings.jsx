import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  listJobs,
  listSubdomains,
  saveJob,
  unsaveJob,
  listSavedJobs,
  createSavedSearch,
} from "../services/apiClient";
import GlassCard from "../components/GlassCard";
import AnimatedButton from "../components/AnimatedButton";
import NavBar from "../components/NavBar";
import { LoadingPulse } from "../components/motionConfig";
import { apiErrorMessage } from "../utils/errors";
import { getSubdomainSuggestions, DOMAIN_SKILL_EXAMPLES } from "../utils/subdomainSuggestions";

const DOMAINS = ["Engineering", "Business", "Healthcare"];
const MAX_COMPARE = 4;
const MAX_SKILL_TAGS = 5;
const MAX_POLL_ATTEMPTS = 40;

const stateVariants = {
  hidden: { opacity: 0, scale: 0.92 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] },
  },
};

function listingToTrackedPayload(job, fallbackDomain) {
  return {
    canonicalId: job.canonical_id,
    jobTitle: job.title,
    company: job.company,
    domain: job.domain || fallbackDomain,
    applyUrl: job.apply_url,
  };
}

function SkillTags({ skills }) {
  if (!skills?.length) return null;

  const visible = skills.slice(0, MAX_SKILL_TAGS);
  const remaining = skills.length - MAX_SKILL_TAGS;

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "0.5rem",
        alignItems: "center",
        marginBottom: "0.25rem",
      }}
    >
      {visible.map((skill) => (
        <span
          key={skill}
          className="status-badge status-badge--default"
          style={{ textTransform: "none", letterSpacing: 0 }}
        >
          {skill}
        </span>
      ))}
      {remaining > 0 && (
        <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
          +{remaining} more
        </span>
      )}
    </div>
  );
}

function JobCard({
  job,
  index,
  isSaved,
  saving,
  saveError,
  onGetMatched,
  onToggleSave,
  compareSelected,
  onCompareToggle,
}) {
  return (
    <GlassCard className="glass-card--compact" delay={index * 0.05}>
      <h3
        style={{
          fontSize: "1.25rem",
          fontWeight: 700,
          letterSpacing: "-0.02em",
          marginBottom: "0.375rem",
          color: "var(--text-primary)",
        }}
      >
        {job.title}
      </h3>
      {onCompareToggle && job.canonical_id ? (
        <label className="compare-check" style={{ marginBottom: "0.5rem" }}>
          <input
            type="checkbox"
            checked={compareSelected}
            onChange={() => onCompareToggle(job)}
          />
          Compare
        </label>
      ) : null}
      <p
        style={{
          fontSize: "0.9375rem",
          color: "var(--text-secondary)",
          marginBottom: "0.75rem",
        }}
      >
        {job.company}
        {job.company && job.location ? " · " : ""}
        {job.location}
      </p>
      <SkillTags skills={job.required_skills} />
      <p
        style={{
          fontSize: "0.8125rem",
          color: "var(--text-muted)",
          marginTop: "0.75rem",
          marginBottom: "1rem",
        }}
      >
        {[job.employment_type, job.source].filter(Boolean).join(" · ")}
      </p>
      <div className="job-card__actions">
        <AnimatedButton
          className="btn--compact"
          onClick={onGetMatched}
        >
          Get Matched
        </AnimatedButton>
        <AnimatedButton
          secondary
          className="btn--compact"
          loading={saving}
          disabled={saving || !job.canonical_id}
          onClick={() => onToggleSave(job)}
        >
          {isSaved ? "Saved" : "Save"}
        </AnimatedButton>
      </div>
      {saveError && <div className="form-error">{saveError}</div>}
    </GlassCard>
  );
}

export default function JobListings() {
  const navigate = useNavigate();
  const [domain, setDomain] = useState("Engineering");
  const [skill, setSkill] = useState("");
  const [employmentType, setEmploymentType] = useState("");
  const [jobs, setJobs] = useState([]);
  const [nextToken, setNextToken] = useState(null);
  const [uiState, setUiState] = useState("loading");
  const [loadingMore, setLoadingMore] = useState(false);
  const [harvestMessage, setHarvestMessage] = useState("");
  const [harvestDomain, setHarvestDomain] = useState("");
  const [harvestTimedOut, setHarvestTimedOut] = useState(false);
  const [savedIds, setSavedIds] = useState(() => new Set());
  const [savingId, setSavingId] = useState(null);
  const [cardErrors, setCardErrors] = useState({});
  const [compareIds, setCompareIds] = useState([]);
  const [saveSearchMessage, setSaveSearchMessage] = useState("");
  const [saveSearchLoading, setSaveSearchLoading] = useState(false);
  const pollCountRef = useRef(0);
  const pollTimerRef = useRef(null);
  const pollParamsRef = useRef(null);
  const [skillSuggestions, setSkillSuggestions] = useState(
    () => getSubdomainSuggestions("Engineering")
  );

  useEffect(() => {
    let cancelled = false;
    async function loadSubdomains() {
      try {
        const data = await listSubdomains(domain);
        if (!cancelled && data?.subdomains?.length) {
          setSkillSuggestions(data.subdomains.map((row) => row.label).filter(Boolean));
          return;
        }
      } catch {
        // fall back to static list
      }
      if (!cancelled) {
        setSkillSuggestions(getSubdomainSuggestions(domain));
      }
    }
    loadSubdomains();
    return () => {
      cancelled = true;
    };
  }, [domain]);

  const stopPolling = () => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  };

  useEffect(() => {
    return stopPolling;
  }, []);

  useEffect(() => {
    async function loadSaved() {
      try {
        const data = await listSavedJobs();
        const ids = (data.savedJobs || []).map((row) => row.canonicalId).filter(Boolean);
        setSavedIds(new Set(ids));
      } catch {
        setSavedIds(new Set());
      }
    }
    loadSaved();
  }, []);

  const applyJobsResult = (data) => {
    const fetched = data.jobs ?? [];
    setJobs(fetched);
    setNextToken(data.nextToken ?? null);
    setUiState(fetched.length > 0 ? "results" : "empty");
  };

  const startHarvestPolling = (params) => {
    stopPolling();
    pollCountRef.current = 0;
    pollParamsRef.current = params;
    setHarvestTimedOut(false);

    pollTimerRef.current = setInterval(async () => {
      pollCountRef.current += 1;
      const { domain: pollDomain, options } = pollParamsRef.current;

      try {
        const data = await listJobs(pollDomain, options);

        if (data.status === "harvesting") {
          if (data.message) {
            setHarvestMessage(data.message);
          }
          if (pollCountRef.current >= MAX_POLL_ATTEMPTS) {
            stopPolling();
            setHarvestTimedOut(true);
          }
          return;
        }

        if (Array.isArray(data.jobs)) {
          stopPolling();
          applyJobsResult(data);
          return;
        }
      } catch {
        // Transient failure — retry on next tick unless cap is reached
      }

      if (pollCountRef.current >= MAX_POLL_ATTEMPTS) {
        stopPolling();
        setHarvestTimedOut(true);
      }
    }, 3000);
  };

  const fetchJobs = useCallback(
    async ({ reset = true, token = null } = {}) => {
      if (reset) {
        stopPolling();
        setHarvestTimedOut(false);
        setUiState("loading");
        setJobs([]);
        setNextToken(null);
      } else {
        setLoadingMore(true);
      }

      try {
        const options = { limit: 20 };
        if (skill.trim()) {
          options.skill = skill.trim();
        }
        if (employmentType) {
          options.employmentType = employmentType;
        }
        if (token) {
          options.nextToken = token;
        }

        const data = await listJobs(domain, options);

        if (reset && data.status === "harvesting") {
          setHarvestDomain(data.domain || domain);
          setHarvestMessage(data.message || "");
          setUiState("harvesting");
          startHarvestPolling({ domain, options });
          return;
        }

        const fetched = data.jobs ?? [];

        if (reset) {
          setJobs(fetched);
          setNextToken(data.nextToken ?? null);
          setUiState(fetched.length > 0 ? "results" : "empty");
        } else {
          setJobs((prev) => [...prev, ...fetched]);
          setNextToken(data.nextToken ?? null);
        }
      } catch {
        if (reset) {
          setUiState("error");
        }
      } finally {
        if (!reset) {
          setLoadingMore(false);
        }
      }
    },
    [domain, skill, employmentType]
  );

  useEffect(() => {
    fetchJobs({ reset: true });
  }, []);

  const handleSearch = () => {
    fetchJobs({ reset: true });
  };

  const handleLoadMore = () => {
    if (nextToken && !loadingMore) {
      fetchJobs({ reset: false, token: nextToken });
    }
  };

  const setCardError = (canonicalId, field, message) => {
    setCardErrors((prev) => ({
      ...prev,
      [canonicalId]: { ...prev[canonicalId], [field]: message },
    }));
  };

  const handleGetMatched = () => {
    navigate("/match");
  };

  const handleCompareToggle = (job) => {
    const id = job.canonical_id;
    if (!id) {
      return;
    }
    setCompareIds((prev) => {
      if (prev.includes(id)) {
        return prev.filter((row) => row !== id);
      }
      if (prev.length >= MAX_COMPARE) {
        return prev;
      }
      return [...prev, id];
    });
  };

  const handleOpenCompare = () => {
    if (compareIds.length < 2) {
      return;
    }
    const params = new URLSearchParams({
      domain,
      ids: compareIds.join(","),
    });
    navigate(`/compare?${params.toString()}`);
  };

  const handleSaveSearch = async () => {
    setSaveSearchLoading(true);
    setSaveSearchMessage("");
    try {
      await createSavedSearch({
        domain,
        skill: skill.trim(),
        employmentType: employmentType || "",
        label: [domain, skill.trim(), employmentType].filter(Boolean).join(" · "),
      });
      setSaveSearchMessage("Search saved — we'll alert you when new roles match.");
    } catch (err) {
      setSaveSearchMessage(apiErrorMessage(err, "Could not save this search."));
    } finally {
      setSaveSearchLoading(false);
    }
  };

  const handleToggleSave = async (job) => {
    const canonicalId = job.canonical_id;
    if (!canonicalId || savingId) {
      return;
    }

    setSavingId(canonicalId);
    setCardError(canonicalId, "save", "");
    const currentlySaved = savedIds.has(canonicalId);
    try {
      if (currentlySaved) {
        await unsaveJob(canonicalId);
        setSavedIds((prev) => {
          const next = new Set(prev);
          next.delete(canonicalId);
          return next;
        });
      } else {
        await saveJob(listingToTrackedPayload(job, domain));
        setSavedIds((prev) => new Set(prev).add(canonicalId));
      }
    } catch (err) {
      setCardError(
        canonicalId,
        "save",
        apiErrorMessage(
          err,
          currentlySaved ? "Could not unsave this role." : "Could not save this role."
        )
      );
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="page page--dashboard">
      <div className="dashboard job-listings">
        <NavBar />
        <GlassCard className="glass-card--compact" hover={false}>
          <div className="glass-card__header" style={{ marginBottom: "1.5rem" }}>
            <h1 className="glass-card__title">Find best roles for you</h1>
            <p className="glass-card__subtitle">
              Browse opportunities by domain, role type, and skill
            </p>
          </div>

          <div className="listings-filters">
            <div className="form-group" style={{ flex: "1 1 160px", marginBottom: 0 }}>
              <label className="form-label" htmlFor="domain">
                Domain
              </label>
              <select
                id="domain"
                className="form-input filter-input"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
              >
                {DOMAINS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group" style={{ flex: "1 1 140px", marginBottom: 0 }}>
              <label className="form-label" htmlFor="employmentType">
                Role type
              </label>
              <select
                id="employmentType"
                className="form-input filter-input"
                value={employmentType}
                onChange={(e) => setEmploymentType(e.target.value)}
              >
                <option value="">All</option>
                <option value="Internship">Internship</option>
                <option value="Job">Job</option>
              </select>
            </div>

            <div className="form-group" style={{ flex: "1 1 200px", marginBottom: 0 }}>
              <label className="form-label" htmlFor="skill">
                Sub-domain / Skill (optional)
              </label>
              <datalist id="skill-suggestions">
                {skillSuggestions.map((suggestion) => (
                  <option key={suggestion} value={suggestion} />
                ))}
              </datalist>
              <input
                id="skill"
                type="text"
                className="form-input filter-input"
                placeholder={DOMAIN_SKILL_EXAMPLES[domain] ?? "e.g. skill or keyword"}
                list="skill-suggestions"
                value={skill}
                onChange={(e) => setSkill(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              />
            </div>

            <AnimatedButton
              className="btn--compact listings-filters__search"
              onClick={handleSearch}
            >
              Search
            </AnimatedButton>
            <AnimatedButton
              secondary
              className="btn--compact"
              loading={saveSearchLoading}
              onClick={handleSaveSearch}
            >
              Save search
            </AnimatedButton>
            <AnimatedButton
              secondary
              className="btn--compact"
              onClick={() => navigate("/search-alerts")}
            >
              Alerts
            </AnimatedButton>
          </div>
          {saveSearchMessage && (
            <p className="compare-muted" style={{ marginTop: "0.75rem" }}>
              {saveSearchMessage}
            </p>
          )}
          {compareIds.length >= 2 && (
            <div className="compare-actions" style={{ marginTop: "0.75rem" }}>
              <AnimatedButton type="button" className="btn--compact" onClick={handleOpenCompare}>
                Compare {compareIds.length} roles
              </AnimatedButton>
            </div>
          )}
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
                <h2 className="success-state__title">Finding the best roles for you</h2>
              </motion.div>
            )}

            {uiState === "harvesting" && (
              <motion.div
                key="harvesting"
                className="success-state"
                variants={stateVariants}
                initial="hidden"
                animate="visible"
                exit="hidden"
              >
                <LoadingPulse>
                  <div className="success-state__icon" aria-hidden="true">
                    ✨
                  </div>
                </LoadingPulse>
                <h2 className="success-state__title">
                  Finding {harvestDomain || domain} roles for you
                </h2>
                <p className="success-state__text">
                  {harvestTimedOut
                    ? "This is taking longer than usual — try searching again in a moment"
                    : harvestMessage}
                </p>
                {harvestTimedOut && (
                  <AnimatedButton onClick={() => fetchJobs({ reset: true })}>
                    Try again
                  </AnimatedButton>
                )}
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
                  🔍
                </div>
                <h2 className="success-state__title">No opportunities found</h2>
                <p className="success-state__text">
                  Try a different domain or skill filter to discover more
                  opportunities.
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
                  We couldn&apos;t load opportunities right now.
                </p>
                <AnimatedButton onClick={() => fetchJobs({ reset: true })}>
                  Try again
                </AnimatedButton>
              </motion.div>
            )}

            {uiState === "results" && (
              <motion.div
                key="results"
                style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
              >
                {jobs.map((job, index) => {
                  const id = job.canonical_id;
                  const errors = cardErrors[id] || {};
                  return (
                    <JobCard
                      key={id ?? `${job.title}-${index}`}
                      job={job}
                      index={index}
                      isSaved={Boolean(id && savedIds.has(id))}
                      saving={savingId === id}
                      saveError={errors.save}
                      onGetMatched={handleGetMatched}
                      onToggleSave={handleToggleSave}
                      compareSelected={Boolean(id && compareIds.includes(id))}
                      onCompareToggle={handleCompareToggle}
                    />
                  );
                })}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {uiState === "results" && nextToken && (
          <div style={{ marginTop: "1.25rem", textAlign: "center" }}>
            <AnimatedButton
              secondary
              loading={loadingMore}
              onClick={handleLoadMore}
            >
              {loadingMore ? "Loading…" : "Load more"}
            </AnimatedButton>
          </div>
        )}
      </div>
    </div>
  );
}
