import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import {
  startMatchSession,
  requestResumeUploadUrl,
  uploadResumeToS3,
  getMatchSession,
  startDomainTest,
  submitTestAnswer,
  getMatchedJobs,
  getFinalRecommendation,
  createApplication,
} from "../services/apiClient";
import GlassCard from "../components/GlassCard";
import AnimatedButton from "../components/AnimatedButton";
import NavBar from "../components/NavBar";
import { EASE_OUT, DURATION, LoadingPulse, MotionListItem } from "../components/motionConfig";
import { apiErrorMessage } from "../utils/errors";

const POLL_INTERVAL_MS = 3000;
const MAX_POLL_ATTEMPTS = 40;
const MAX_SKILL_TAGS = 5;

const TEST_DOMAINS = ["Engineering", "Business", "Healthcare", "Design"];
const TEST_DIFFICULTIES = [
  { label: "Easy", value: "easy" },
  { label: "Medium", value: "medium" },
  { label: "Hard", value: "hard" },
  { label: "Mixed", value: "mixed" },
];
const SKILL_DEFAULT_BY_DOMAIN = {
  Engineering: "Software",
  Business: "Management",
  Healthcare: "Medicine",
  Design: "UI/UX",
};

function wizardStepMotion(reduced) {
  return {
    initial: reduced ? { opacity: 0 } : { opacity: 0, x: 24 },
    animate: { opacity: 1, x: 0 },
    exit: reduced ? { opacity: 0 } : { opacity: 0, x: -24 },
    transition: { duration: DURATION, ease: EASE_OUT },
  };
}

function isValidResumeFile(file) {
  const name = file.name.toLowerCase();
  return name.endsWith(".pdf") || name.endsWith(".docx");
}

function FileDropZone({ id, label, icon, file, onChange, disabled }) {
  return (
    <div className={`drop-zone ${file ? "drop-zone--has-file" : ""}`}>
      <input
        id={id}
        className="drop-zone__input"
        type="file"
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
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

function SkillTags({ skills }) {
  const tags = Array.isArray(skills) ? skills : [];
  const visible = tags.slice(0, MAX_SKILL_TAGS);
  const remaining = tags.length - MAX_SKILL_TAGS;

  return (
    <div className="match-skill-tags">
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
        <span className="match-skill-tags__more">+{remaining} more</span>
      )}
    </div>
  );
}

function listingToTrackedPayload(job, fallbackDomain) {
  return {
    canonicalId: job.canonical_id,
    jobTitle: job.title,
    company: job.company,
    domain: job.domain || fallbackDomain,
    applyUrl: job.apply_url,
  };
}

function MatchListingCard({
  job,
  index = 0,
  whyThisFits,
  applying = false,
  applyError,
  onApply,
}) {
  return (
    <MotionListItem index={index} className="match-listing-card">
      <h3 className="match-listing-card__title">{job.title || "Untitled role"}</h3>
      <p className="match-listing-card__meta">
        {[job.company, job.employment_type].filter(Boolean).join(" · ")}
      </p>
      <SkillTags skills={job.required_skills} />
      {whyThisFits ? (
        <p className="match-listing-card__why">{whyThisFits}</p>
      ) : null}
      {job.apply_url && onApply ? (
        <div className="job-card__actions match-listing-card__actions">
          <AnimatedButton
            type="button"
            className="btn--compact"
            loading={applying}
            disabled={applying}
            onClick={() => onApply(job)}
          >
            {applying ? "Applying…" : "Apply"}
          </AnimatedButton>
        </div>
      ) : null}
      {applyError ? <div className="form-error">{applyError}</div> : null}
    </MotionListItem>
  );
}

export default function MatchWizard() {
  const navigate = useNavigate();
  const reducedMotion = useReducedMotion();
  const stepMotion = wizardStepMotion(reducedMotion);
  const [step, setStep] = useState(1);
  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [githubHandle, setGithubHandle] = useState("");
  const [leetcodeHandle, setLeetcodeHandle] = useState("");
  const [resume, setResume] = useState(null);
  const [fileError, setFileError] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [powScore, setPowScore] = useState(null);
  const [powBreakdown, setPowBreakdown] = useState("");

  const [testDomain, setTestDomain] = useState("Engineering");
  const [testSkill, setTestSkill] = useState(SKILL_DEFAULT_BY_DOMAIN.Engineering);
  const [testDifficulty, setTestDifficulty] = useState("medium");
  const [currentQuestion, setCurrentQuestion] = useState(null);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [totalQuestions, setTotalQuestions] = useState(15);
  const [selectedIndex, setSelectedIndex] = useState(null);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [scorePercent, setScorePercent] = useState(null);
  const [testSyncError, setTestSyncError] = useState("");

  // Pillar Step 3 (wizard step 7) — matched jobs
  const [matchesUiState, setMatchesUiState] = useState("idle");
  const [matchesError, setMatchesError] = useState("");
  const [matchedInternships, setMatchedInternships] = useState([]);
  const [matchedJobsList, setMatchedJobsList] = useState([]);
  const [matchesMeta, setMatchesMeta] = useState({ domain: "", skill: "" });

  // Pillar Step 4 (wizard step 8) — final recommendation
  const [recUiState, setRecUiState] = useState("idle");
  const [recError, setRecError] = useState("");
  const [rankedJobs, setRankedJobs] = useState([]);
  const [readinessSummary, setReadinessSummary] = useState("");
  const [explanationsAvailable, setExplanationsAvailable] = useState(true);
  const [applyingId, setApplyingId] = useState(null);
  const [applyErrors, setApplyErrors] = useState({});

  const pollCountRef = useRef(0);
  const pollTimerRef = useRef(null);
  const questionTimerRef = useRef(null);
  const submittingRef = useRef(false);
  const currentQuestionRef = useRef(null);
  const sessionIdRef = useRef(null);
  const autoSubmittedForRef = useRef(null);

  const stopPolling = () => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  };

  const stopQuestionTimer = () => {
    if (questionTimerRef.current) {
      clearInterval(questionTimerRef.current);
      questionTimerRef.current = null;
    }
  };

  useEffect(() => {
    return () => {
      stopPolling();
      stopQuestionTimer();
    };
  }, []);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    currentQuestionRef.current = currentQuestion;
  }, [currentQuestion]);

  const applyQuestion = (payload) => {
    submittingRef.current = false;
    autoSubmittedForRef.current = null;
    setSubmitting(false);
    setSelectedIndex(null);
    setError("");
    setTestSyncError("");
    setCurrentQuestion({
      questionId: payload.questionId,
      questionText: payload.questionText,
      options: payload.options,
      timeLimitSeconds: payload.timeLimitSeconds,
    });
    setCurrentQuestionIndex(payload.currentQuestionIndex ?? 0);
    setTotalQuestions(payload.totalQuestions ?? 15);
    setSecondsLeft(payload.timeLimitSeconds ?? 0);
  };

  useEffect(() => {
    if (step !== 5 || !currentQuestion?.questionId) {
      stopQuestionTimer();
      return undefined;
    }

    stopQuestionTimer();
    questionTimerRef.current = setInterval(() => {
      setSecondsLeft((prev) => {
        if (prev <= 1) {
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return stopQuestionTimer;
  }, [step, currentQuestion?.questionId]);

  const canContinue =
    Boolean(linkedinUrl.trim()) && Boolean(resume) && !fileError && !loading;

  const canStartTest =
    Boolean(testDomain) && Boolean(testSkill.trim()) && Boolean(testDifficulty) && !loading;

  const handleResumeChange = (e) => {
    const file = e.target.files?.[0] ?? null;
    if (!file) {
      setResume(null);
      setFileError("");
      return;
    }
    if (!isValidResumeFile(file)) {
      setResume(null);
      setFileError("Resume must be a .pdf or .docx file.");
      return;
    }
    setFileError("");
    setResume(file);
  };

  const handleDomainChange = (value) => {
    setTestDomain(value);
    setTestSkill(SKILL_DEFAULT_BY_DOMAIN[value] || "");
  };

  const startPolling = (id) => {
    stopPolling();
    pollCountRef.current = 0;
    setStep(2);
    setError("");

    pollTimerRef.current = setInterval(async () => {
      pollCountRef.current += 1;

      try {
        const session = await getMatchSession(id);
        if (session.status === "awaiting_test") {
          stopPolling();
          setPowScore(session.powScore);
          setPowBreakdown(session.powBreakdown || "");
          setStep(3);
          return;
        }
        if (session.status === "failed") {
          stopPolling();
          setError(session.errorMessage || "Scoring failed. Please try again.");
          setStep(2);
          return;
        }
      } catch {
        // Transient failure — retry on next tick unless cap is reached
      }

      if (pollCountRef.current >= MAX_POLL_ATTEMPTS) {
        stopPolling();
        setError(
          "Scoring is taking longer than usual. Please try again in a moment."
        );
      }
    }, POLL_INTERVAL_MS);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!linkedinUrl.trim() || !resume) {
      setError("Please add your LinkedIn URL and a PDF or DOCX resume.");
      return;
    }
    if (fileError) {
      return;
    }
    setError("");
    setLoading(true);
    try {
      const started = await startMatchSession();
      const newSessionId = started.sessionId;
      setSessionId(newSessionId);

      const body = { linkedinUrl: linkedinUrl.trim() };
      const github = githubHandle.trim();
      const leetcode = leetcodeHandle.trim();
      if (github) body.githubHandle = github;
      if (leetcode) body.leetcodeHandle = leetcode;

      const { uploadUrl } = await requestResumeUploadUrl(newSessionId, body);
      await uploadResumeToS3(uploadUrl, resume);
      startPolling(newSessionId);
    } catch (err) {
      setError(apiErrorMessage(err, "Could not start matching. Please try again."));
      setStep(1);
    } finally {
      setLoading(false);
    }
  };

  const handleTryAgain = () => {
    stopPolling();
    setError("");
    setLoading(false);
    setStep(1);
  };

  const handleStartOver = () => {
    stopPolling();
    stopQuestionTimer();
    setError("");
    setLoading(false);
    setSessionId(null);
    setPowScore(null);
    setPowBreakdown("");
    setScorePercent(null);
    setCurrentQuestion(null);
    setTestSyncError("");
    setMatchesUiState("idle");
    setMatchesError("");
    setMatchedInternships([]);
    setMatchedJobsList([]);
    setMatchesMeta({ domain: "", skill: "" });
    setRecUiState("idle");
    setRecError("");
    setRankedJobs([]);
    setReadinessSummary("");
    setExplanationsAvailable(true);
    setStep(1);
  };

  const handleLoadMatchedJobs = async () => {
    if (!sessionId) {
      return;
    }
    setMatchesError("");
    setMatchesUiState("loading");
    setMatchedInternships([]);
    setMatchedJobsList([]);
    setStep(7);
    try {
      const data = await getMatchedJobs(sessionId);
      const internships = Array.isArray(data.internships) ? data.internships : [];
      const jobs = Array.isArray(data.jobs) ? data.jobs : [];
      setMatchedInternships(internships);
      setMatchedJobsList(jobs);
      setMatchesMeta({
        domain: data.domain || "",
        skill: data.skill || "",
      });
      setMatchesUiState(internships.length + jobs.length > 0 ? "ready" : "empty");
    } catch (err) {
      setMatchesError(
        apiErrorMessage(err, "Could not load matched jobs. Please try again.")
      );
      setMatchesUiState("error");
    }
  };

  const handleApply = async (job) => {
    const applyUrl = job.apply_url;
    if (!applyUrl) {
      return;
    }

    window.open(applyUrl, "_blank", "noopener,noreferrer");

    const canonicalId = job.canonical_id;
    if (!canonicalId || applyingId) {
      return;
    }

    setApplyingId(canonicalId);
    setApplyErrors((prev) => ({ ...prev, [canonicalId]: "" }));
    try {
      await createApplication(
        listingToTrackedPayload(job, matchesMeta.domain || testDomain)
      );
    } catch (err) {
      setApplyErrors((prev) => ({
        ...prev,
        [canonicalId]: apiErrorMessage(
          err,
          "Opened the listing, but could not record this application."
        ),
      }));
    } finally {
      setApplyingId(null);
    }
  };

  const handleLoadRecommendation = async () => {
    if (!sessionId) {
      return;
    }
    setRecError("");
    setRecUiState("loading");
    setRankedJobs([]);
    setReadinessSummary("");
    setExplanationsAvailable(true);
    setStep(8);
    try {
      const data = await getFinalRecommendation(sessionId);
      const ranked = Array.isArray(data.rankedJobs) ? data.rankedJobs : [];
      setRankedJobs(ranked);
      setReadinessSummary(
        typeof data.readinessSummary === "string" ? data.readinessSummary : ""
      );
      setExplanationsAvailable(data.explanationsAvailable !== false);
      setRecUiState("ready");
    } catch (err) {
      setRecError(
        apiErrorMessage(
          err,
          "Could not generate your recommendation. Please try again."
        )
      );
      setRecUiState("error");
    }
  };

  const handleStartTest = async (e) => {
    e.preventDefault();
    if (!sessionId || !canStartTest) {
      return;
    }
    setError("");
    setLoading(true);
    try {
      const data = await startDomainTest(sessionId, {
        domain: testDomain,
        skill: testSkill.trim(),
        difficulty: testDifficulty,
      });
      applyQuestion(data);
      setStep(5);
    } catch (err) {
      setError(apiErrorMessage(err, "Could not generate your test. Please try again."));
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitAnswer = useCallback(async (index) => {
    if (submittingRef.current) {
      return;
    }
    const question = currentQuestionRef.current;
    const activeSessionId = sessionIdRef.current;
    if (!question || !activeSessionId) {
      return;
    }

    submittingRef.current = true;
    setSubmitting(true);
    stopQuestionTimer();
    setError("");

    const payload = { questionId: question.questionId };
    if (index !== null && index !== undefined) {
      payload.selectedIndex = index;
    }

    try {
      const data = await submitTestAnswer(activeSessionId, payload);
      if (data.testCompleted) {
        stopQuestionTimer();
        setScorePercent(data.scorePercent);
        setTotalQuestions(data.totalQuestions ?? 15);
        setStep(6);
        return;
      }
      applyQuestion(data);
      setStep(5);
    } catch (err) {
      stopQuestionTimer();
      const status = err.response?.status;
      if (status === 409) {
        setTestSyncError(
          apiErrorMessage(
            err,
            "This test session is out of sync — it may be open in another tab. There's no way to resume from here."
          )
        );
        return;
      }
      setTestSyncError(
        apiErrorMessage(err, "Could not submit your answer. Please return to the dashboard.")
      );
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }, []);

  useEffect(() => {
    if (step !== 5 || secondsLeft !== 0 || !currentQuestion) {
      return;
    }
    if (submittingRef.current || testSyncError) {
      return;
    }
    if (autoSubmittedForRef.current === currentQuestion.questionId) {
      return;
    }
    autoSubmittedForRef.current = currentQuestion.questionId;
    handleSubmitAnswer(null);
  }, [secondsLeft, step, currentQuestion, testSyncError, handleSubmitAnswer]);

  const correctCount =
    scorePercent == null || !totalQuestions
      ? null
      : Math.round((scorePercent / 100) * totalQuestions);

  return (
    <div className="page page--dashboard">
      <div className="dashboard">
        <NavBar />
        <GlassCard hover={false} className="glass-card--section">
          <AnimatePresence mode="wait">
            {step === 1 && (
              <motion.div key="profile" {...stepMotion}>
                <div className="glass-card__header">
                  <h1 className="glass-card__title">Get matched by AI</h1>
                  <p className="glass-card__subtitle">
                    Share your profile links and resume so we can score your
                    proof of work.
                  </p>
                </div>

                {error && (
                  <div className="form-error">
                    {error}
                    <div style={{ marginTop: "0.75rem" }}>
                      <AnimatedButton
                        type="button"
                        secondary
                        className="btn--compact"
                        onClick={handleTryAgain}
                      >
                        Try again
                      </AnimatedButton>
                    </div>
                  </div>
                )}

                <form onSubmit={handleSubmit}>
                  <div className="form-group">
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
                      required
                      disabled={loading}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label" htmlFor="githubHandle">
                      GitHub handle (optional)
                    </label>
                    <input
                      id="githubHandle"
                      className="form-input"
                      type="text"
                      value={githubHandle}
                      onChange={(e) => setGithubHandle(e.target.value)}
                      placeholder="your-username"
                      disabled={loading}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label" htmlFor="leetcodeHandle">
                      LeetCode handle (optional)
                    </label>
                    <input
                      id="leetcodeHandle"
                      className="form-input"
                      type="text"
                      value={leetcodeHandle}
                      onChange={(e) => setLeetcodeHandle(e.target.value)}
                      placeholder="your-username"
                      disabled={loading}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label" htmlFor="resume">
                      Resume
                    </label>
                    <FileDropZone
                      id="resume"
                      icon="📄"
                      label="Upload a PDF or DOCX resume"
                      file={resume}
                      onChange={handleResumeChange}
                      disabled={loading}
                    />
                    {fileError && (
                      <p className="form-error" style={{ marginTop: "0.75rem", marginBottom: 0 }}>
                        {fileError}
                      </p>
                    )}
                  </div>

                  <AnimatedButton type="submit" loading={loading} disabled={!canContinue}>
                    {loading ? "Uploading…" : "Continue"}
                  </AnimatedButton>
                </form>
              </motion.div>
            )}

            {step === 2 && (
              <motion.div key="waiting" className="success-state" {...stepMotion}>
                {error ? (
                  <>
                    <div className="success-state__icon" aria-hidden="true">
                      ✕
                    </div>
                    <h2 className="success-state__title">We couldn&apos;t score your profile</h2>
                    <p className="success-state__text">{error}</p>
                    <AnimatedButton onClick={handleStartOver}>Start over</AnimatedButton>
                  </>
                ) : (
                  <>
                    <LoadingPulse>
                      <div className="success-state__icon" aria-hidden="true">
                        ⏳
                      </div>
                    </LoadingPulse>
                    <h2 className="success-state__title">Scoring your profile...</h2>
                    <p className="success-state__text">
                      We&apos;re reading your resume and scoring proof of work.
                      This usually takes a few seconds.
                    </p>
                  </>
                )}
              </motion.div>
            )}

            {step === 3 && (
              <motion.div key="result" className="success-state" {...stepMotion}>
                <p className="match-score__label">Proof of work</p>
                <p className="match-score">
                  {powScore ?? "—"}
                  <span className="match-score__out-of">/50</span>
                </p>
                {powBreakdown && (
                  <p className="success-state__text match-score__breakdown">
                    {powBreakdown}
                  </p>
                )}

                <div className="match-next-step">
                  <div className="match-next-step__heading">
                    <h3 className="match-next-step__title">Continue to domain test</h3>
                  </div>
                  <p className="success-state__text" style={{ marginBottom: "1rem" }}>
                    Take a short timed quiz so we can match you to roles that
                    fit how you actually work.
                  </p>
                  <AnimatedButton
                    type="button"
                    onClick={() => {
                      setError("");
                      setStep(4);
                    }}
                  >
                    Continue to domain test
                  </AnimatedButton>
                </div>

                <div style={{ marginTop: "1.25rem" }}>
                  <AnimatedButton
                    type="button"
                    secondary
                    onClick={() => navigate("/dashboard")}
                  >
                    Back to Dashboard
                  </AnimatedButton>
                </div>
              </motion.div>
            )}

            {step === 4 && (
              <motion.div key="test-setup" {...stepMotion}>
                <div className="glass-card__header">
                  <h1 className="glass-card__title">Domain test</h1>
                  <p className="glass-card__subtitle">
                    Pick a domain and skill. We&apos;ll generate 15 timed
                    questions from what&apos;s hiring right now.
                  </p>
                </div>

                {error && <div className="form-error">{error}</div>}

                {loading ? (
                  <div className="success-state">
                    <LoadingPulse>
                      <div className="success-state__icon" aria-hidden="true">
                        ⏳
                      </div>
                    </LoadingPulse>
                    <h2 className="success-state__title">Generating your test...</h2>
                    <p className="success-state__text">
                      This can take a few seconds while we write your questions.
                    </p>
                  </div>
                ) : (
                  <form onSubmit={handleStartTest}>
                    <div className="form-group">
                      <label className="form-label" htmlFor="testDomain">
                        Domain
                      </label>
                      <select
                        id="testDomain"
                        className="form-input filter-input"
                        value={testDomain}
                        onChange={(e) => handleDomainChange(e.target.value)}
                      >
                        {TEST_DOMAINS.map((domain) => (
                          <option key={domain} value={domain}>
                            {domain}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="form-group">
                      <label className="form-label" htmlFor="testSkill">
                        Skill
                      </label>
                      <input
                        id="testSkill"
                        className="form-input"
                        type="text"
                        value={testSkill}
                        onChange={(e) => setTestSkill(e.target.value)}
                        placeholder="e.g. Python"
                        required
                      />
                    </div>

                    <div className="form-group">
                      <label className="form-label" htmlFor="testDifficulty">
                        Difficulty
                      </label>
                      <select
                        id="testDifficulty"
                        className="form-input filter-input"
                        value={testDifficulty}
                        onChange={(e) => setTestDifficulty(e.target.value)}
                      >
                        {TEST_DIFFICULTIES.map((item) => (
                          <option key={item.value} value={item.value}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <AnimatedButton type="submit" disabled={!canStartTest}>
                      Start Test
                    </AnimatedButton>
                  </form>
                )}
              </motion.div>
            )}

            {step === 5 && currentQuestion && (
              <motion.div
                key={`question-${currentQuestion.questionId}`}
                {...stepMotion}
              >
                {testSyncError ? (
                  <div className="success-state">
                    <div className="success-state__icon" aria-hidden="true">
                      ✕
                    </div>
                    <h2 className="success-state__title">Test session out of sync</h2>
                    <p className="success-state__text">{testSyncError}</p>
                    <AnimatedButton
                      type="button"
                      onClick={() => navigate("/dashboard")}
                    >
                      Back to Dashboard
                    </AnimatedButton>
                  </div>
                ) : (
                  <>
                    <div className="match-question-meta">
                      <p className="match-progress">
                        Question {currentQuestionIndex + 1} of {totalQuestions}
                      </p>
                      <p
                        className={`match-timer${secondsLeft <= 10 ? " match-timer--urgent" : ""}`}
                      >
                        {secondsLeft}s
                      </p>
                    </div>
                    <h2 className="match-question-text">{currentQuestion.questionText}</h2>
                    <div className="match-options" role="radiogroup" aria-label="Answer options">
                      {currentQuestion.options.map((option, index) => (
                        <button
                          key={`${currentQuestion.questionId}-${index}`}
                          type="button"
                          className={`match-option${selectedIndex === index ? " match-option--selected" : ""}`}
                          onClick={() => setSelectedIndex(index)}
                          disabled={submitting}
                          aria-pressed={selectedIndex === index}
                        >
                          <span className="match-option__letter">
                            {String.fromCharCode(65 + index)}
                          </span>
                          <span>{option}</span>
                        </button>
                      ))}
                    </div>
                    <AnimatedButton
                      type="button"
                      loading={submitting}
                      disabled={selectedIndex === null || submitting}
                      onClick={() => handleSubmitAnswer(selectedIndex)}
                    >
                      {submitting ? "Submitting…" : "Submit Answer"}
                    </AnimatedButton>
                  </>
                )}
              </motion.div>
            )}

            {step === 6 && (
              <motion.div key="test-result" className="success-state" {...stepMotion}>
                <p className="match-score__label">Domain test</p>
                <p className="match-score">
                  {scorePercent ?? "—"}
                  <span className="match-score__out-of">%</span>
                </p>
                {correctCount != null && (
                  <p className="success-state__text">
                    {correctCount} of {totalQuestions} correct
                  </p>
                )}

                <div className="match-next-step">
                  <div className="match-next-step__heading">
                    <h3 className="match-next-step__title">See matched jobs</h3>
                  </div>
                  <p className="success-state__text" style={{ marginBottom: "1rem" }}>
                    Based on your PoW score and domain test, we&apos;ll show
                    internships and jobs you qualify for.
                  </p>
                  <AnimatedButton type="button" onClick={handleLoadMatchedJobs}>
                    See matched jobs
                  </AnimatedButton>
                </div>

                <div style={{ marginTop: "1.25rem" }}>
                  <AnimatedButton
                    type="button"
                    secondary
                    onClick={() => navigate("/dashboard")}
                  >
                    Back to Dashboard
                  </AnimatedButton>
                </div>
              </motion.div>
            )}

            {step === 7 && (
              <motion.div key="matched-jobs" {...stepMotion}>
                <div className="glass-card__header">
                  <h1 className="glass-card__title">Matched roles</h1>
                  <p className="glass-card__subtitle">
                    {matchesMeta.domain || matchesMeta.skill
                      ? `Open listings that fit your ${[
                          matchesMeta.skill,
                          matchesMeta.domain,
                        ]
                          .filter(Boolean)
                          .join(" · ")} results.`
                      : "Open listings that fit your PoW score and domain test."}
                  </p>
                </div>

                {matchesUiState === "loading" && (
                  <div className="success-state">
                    <LoadingPulse>
                      <div className="success-state__icon" aria-hidden="true">
                        ⏳
                      </div>
                    </LoadingPulse>
                    <h2 className="success-state__title">Finding matched roles...</h2>
                    <p className="success-state__text">
                      Checking active internships and jobs against your scores.
                    </p>
                  </div>
                )}

                {matchesUiState === "error" && (
                  <div className="form-error">
                    {matchesError}
                    <div style={{ marginTop: "0.75rem" }}>
                      <AnimatedButton type="button" onClick={handleLoadMatchedJobs}>
                        Try again
                      </AnimatedButton>
                    </div>
                  </div>
                )}

                {matchesUiState === "empty" && (
                  <div className="success-state">
                    <div className="success-state__icon" aria-hidden="true">
                      📭
                    </div>
                    <h2 className="success-state__title">No matches right now</h2>
                    <p className="success-state__text">
                      No open listings currently match your skill and PoW score.
                      You can still get a readiness recommendation with tips on
                      what to strengthen next.
                    </p>
                  </div>
                )}

                {matchesUiState === "ready" && (
                  <div className="match-listings">
                    {matchedInternships.length > 0 && (
                      <section className="match-listings__section">
                        <h2 className="match-listings__heading">Internships</h2>
                        {matchedInternships.map((job, index) => (
                          <MatchListingCard
                            key={job.canonical_id || job.title}
                            job={job}
                            index={index}
                            applying={applyingId === job.canonical_id}
                            applyError={applyErrors[job.canonical_id]}
                            onApply={handleApply}
                          />
                        ))}
                      </section>
                    )}
                    {matchedJobsList.length > 0 && (
                      <section className="match-listings__section">
                        <h2 className="match-listings__heading">Jobs</h2>
                        {matchedJobsList.map((job, index) => (
                          <MatchListingCard
                            key={job.canonical_id || job.title}
                            job={job}
                            index={index}
                            applying={applyingId === job.canonical_id}
                            applyError={applyErrors[job.canonical_id]}
                            onApply={handleApply}
                          />
                        ))}
                      </section>
                    )}
                  </div>
                )}

                {(matchesUiState === "ready" || matchesUiState === "empty") && (
                  <div className="match-next-step" style={{ marginTop: "1.5rem" }}>
                    <div className="match-next-step__heading">
                      <h3 className="match-next-step__title">
                        Get final recommendation
                      </h3>
                    </div>
                    <p className="success-state__text" style={{ marginBottom: "1rem" }}>
                      We&apos;ll rank your best-fit roles and explain how ready
                      you look for them.
                    </p>
                    <AnimatedButton
                      type="button"
                      onClick={handleLoadRecommendation}
                    >
                      Get final recommendation
                    </AnimatedButton>
                  </div>
                )}

                {matchesUiState !== "loading" && (
                  <div style={{ marginTop: "1.25rem" }}>
                    <AnimatedButton
                      type="button"
                      secondary
                      onClick={() => navigate("/dashboard")}
                    >
                      Back to Dashboard
                    </AnimatedButton>
                  </div>
                )}
              </motion.div>
            )}

            {step === 8 && (
              <motion.div key="recommendation" {...stepMotion}>
                <div className="glass-card__header">
                  <h1 className="glass-card__title">Your recommendation</h1>
                  <p className="glass-card__subtitle">
                    Ranked best-fit roles based on your PoW score, domain test,
                    and skill overlap.
                  </p>
                </div>

                {recUiState === "loading" && (
                  <div className="success-state">
                    <LoadingPulse>
                      <div className="success-state__icon" aria-hidden="true">
                        ⏳
                      </div>
                    </LoadingPulse>
                    <h2 className="success-state__title">
                      Building your recommendation...
                    </h2>
                    <p className="success-state__text">
                      Ranking roles and writing a short readiness summary. This
                      can take a few seconds.
                    </p>
                  </div>
                )}

                {recUiState === "error" && (
                  <div className="form-error">
                    {recError}
                    <div style={{ marginTop: "0.75rem" }}>
                      <AnimatedButton
                        type="button"
                        onClick={handleLoadRecommendation}
                      >
                        Try again
                      </AnimatedButton>
                    </div>
                  </div>
                )}

                {recUiState === "ready" && (
                  <>
                    {readinessSummary && (
                      <div className="match-readiness">
                        <p className="match-score__label">Readiness summary</p>
                        <p className="match-readiness__text">{readinessSummary}</p>
                      </div>
                    )}

                    {!explanationsAvailable && rankedJobs.length > 0 && (
                      <p className="match-explanations-note">
                        Detailed explanations aren&apos;t available right now.
                        Rankings below are still based on your scores.
                      </p>
                    )}

                    {rankedJobs.length > 0 ? (
                      <div className="match-listings">
                        <section className="match-listings__section">
                          <h2 className="match-listings__heading">Ranked roles</h2>
                          {rankedJobs.map((job, index) => (
                            <MatchListingCard
                              key={job.canonical_id || job.title}
                              job={job}
                              index={index}
                              whyThisFits={
                                explanationsAvailable ? job.whyThisFits : ""
                              }
                              applying={applyingId === job.canonical_id}
                              applyError={applyErrors[job.canonical_id]}
                              onApply={handleApply}
                            />
                          ))}
                        </section>
                      </div>
                    ) : (
                      !readinessSummary && (
                        <p className="success-state__text">
                          No ranked roles to show for this session yet.
                        </p>
                      )
                    )}
                  </>
                )}

                {recUiState !== "loading" && (
                  <div style={{ marginTop: "1.5rem" }}>
                    <AnimatedButton
                      type="button"
                      onClick={() => navigate("/dashboard")}
                    >
                      Back to Dashboard
                    </AnimatedButton>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </GlassCard>
      </div>
    </div>
  );
}
