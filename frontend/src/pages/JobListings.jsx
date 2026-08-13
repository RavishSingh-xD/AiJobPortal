import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { listJobs } from "../services/apiClient";
import GlassCard from "../components/GlassCard";
import AnimatedButton from "../components/AnimatedButton";

const DOMAINS = ["Engineering", "Business", "Healthcare"];
const MAX_SKILL_TAGS = 5;

const DOMAIN_SKILL_EXAMPLES = {
  Engineering: "e.g. Python, React, AWS",
  Healthcare: "e.g. Cardiology, Nursing, ECG",
  Business: "e.g. Marketing, Sales, Finance",
};

const stateVariants = {
  hidden: { opacity: 0, scale: 0.92 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] },
  },
};

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

function JobCard({ job, index }) {
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
      {job.apply_url && (
        <a
          href={job.apply_url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn"
          style={{
            width: "auto",
            display: "inline-flex",
            textDecoration: "none",
          }}
        >
          Apply
        </a>
      )}
    </GlassCard>
  );
}

export default function JobListings() {
  const [domain, setDomain] = useState("Engineering");
  const [skill, setSkill] = useState("");
  const [employmentType, setEmploymentType] = useState("");
  const [jobs, setJobs] = useState([]);
  const [nextToken, setNextToken] = useState(null);
  const [uiState, setUiState] = useState("loading");
  const [loadingMore, setLoadingMore] = useState(false);

  const fetchJobs = useCallback(
    async ({ reset = true, token = null } = {}) => {
      if (reset) {
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

  return (
    <div className="page page--dashboard">
      <div className="dashboard job-listings">
        <GlassCard className="glass-card--compact">
          <div className="glass-card__header" style={{ marginBottom: "1.5rem" }}>
            <h1 className="glass-card__title">Find best roles for you</h1>
            <p className="glass-card__subtitle">
              Browse opportunities by domain, role type, and skill
            </p>
          </div>

          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "1rem",
              alignItems: "flex-end",
            }}
          >
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
                Skill (optional)
              </label>
              <input
                id="skill"
                type="text"
                className="form-input filter-input"
                placeholder={DOMAIN_SKILL_EXAMPLES[domain] ?? "e.g. skill or keyword"}
                value={skill}
                onChange={(e) => setSkill(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              />
            </div>

            <AnimatedButton
              className="btn--compact"
              style={{ width: "auto", flex: "0 0 auto" }}
              onClick={handleSearch}
            >
              Search
            </AnimatedButton>
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
                <div className="success-state__icon" aria-hidden="true">
                  ⏳
                </div>
                <h2 className="success-state__title">Finding the best roles for you</h2>
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
                <h2 className="success-state__title">No internships found</h2>
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
                  We couldn&apos;t load internships right now.
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
                {jobs.map((job, index) => (
                  <JobCard
                    key={job.canonical_id ?? `${job.title}-${index}`}
                    job={job}
                    index={index}
                  />
                ))}
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
