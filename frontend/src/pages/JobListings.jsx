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
import AnimatedButton from "../components/AnimatedButton";
import NavBar from "../components/NavBar";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import { MotionListItem } from "../components/motionConfig";
import { apiErrorMessage } from "../utils/errors";
import { getSubdomainSuggestions, DOMAIN_SKILL_EXAMPLES } from "../utils/subdomainSuggestions";

const DOMAINS = ["Engineering", "Business", "Healthcare"];
const MAX_COMPARE = 4;
const MAX_SKILL_TAGS = 5;
const MAX_POLL_ATTEMPTS = 40;

const stateVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { duration: 0.2, ease: [0.16, 1, 0.3, 1] },
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
    <MotionListItem index={index} className="match-listing-card">
      <h3 className="match-listing-card__title">{job.title}</h3>
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
      <p className="match-listing-card__meta">
        {job.company}
        {job.company && job.location ? " · " : ""}
        {job.location}
      </p>
      <SkillTags skills={job.required_skills} />
      <p className="match-listing-card__meta">
        {[job.employment_type, job.source].filter(Boolean).join(" · ")}
      </p>
      <div className="job-card__actions">
        <AnimatedButton className="btn--compact" onClick={onGetMatched}>
          Get matched
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
    </MotionListItem>
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
        <PageHeader
          label="Browse"
          title="Find roles"
          subtitle="Browse opportunities by domain, role type, and skill."
        />

        <div className="app-panel">
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
        </div>

        <AnimatePresence mode="wait">
            {uiState === "loading" && (
              <motion.div key="loading" variants={stateVariants} initial="hidden" animate="visible" exit="hidden">
                <EmptyState variant="loading" loading title="Finding roles" />
              </motion.div>
            )}

            {uiState === "harvesting" && (
              <motion.div key="harvesting" variants={stateVariants} initial="hidden" animate="visible" exit="hidden">
                <EmptyState
                  variant="harvesting"
                  loading
                  title={`Finding ${harvestDomain || domain} roles`}
                  text={
                    harvestTimedOut
                      ? "This is taking longer than usual — try searching again in a moment."
                      : harvestMessage
                  }
                  action={
                    harvestTimedOut ? (
                      <AnimatedButton onClick={() => fetchJobs({ reset: true })}>
                        Try again
                      </AnimatedButton>
                    ) : null
                  }
                />
              </motion.div>
            )}

            {uiState === "empty" && (
              <motion.div key="empty" variants={stateVariants} initial="hidden" animate="visible" exit="hidden">
                <EmptyState
                  title="No opportunities found"
                  text="Try a different domain or skill filter."
                />
              </motion.div>
            )}

            {uiState === "error" && (
              <motion.div key="error" variants={stateVariants} initial="hidden" animate="visible" exit="hidden">
                <EmptyState
                  variant="error"
                  title="Could not load roles"
                  text="We couldn't load opportunities right now."
                  action={
                    <AnimatedButton onClick={() => fetchJobs({ reset: true })}>
                      Try again
                    </AnimatedButton>
                  }
                />
              </motion.div>
            )}

            {uiState === "results" && (
              <motion.div
                key="results"
                className="ledger"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
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
