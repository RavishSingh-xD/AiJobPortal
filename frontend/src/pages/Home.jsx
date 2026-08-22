import { useNavigate } from "react-router-dom";

const STEPS = [
  {
    n: "01",
    title: "Build your profile",
    text: "Tell Avyukt who you are — education, experience, and the links that prove it.",
  },
  {
    n: "02",
    title: "Add your skills",
    text: "List the technologies and tools you actually work with.",
  },
  {
    n: "03",
    title: "Verify your identity",
    text: "Confirm you're a real student. Trust matters when opportunities are involved.",
  },
  {
    n: "04",
    title: "Discover opportunities",
    text: "Browse opportunities across Engineering, Business, and Healthcare.",
  },
  {
    n: "05",
    title: "Get matched",
    text: "AI ranks roles by how well they fit your skills, interests, and career goals.",
  },
  {
    n: "06",
    title: "Apply",
    text: "Apply with a profile that already knows who you are — no blind applications.",
  },
];

const MATCHES = [
  {
    fitLabel: "Strong fit",
    domain: "Engineering",
    title: "Software Engineering Intern",
    skills: ["React", "Python", "AWS", "DSA"],
    reasons: [
      "Frontend and backend skills on your profile",
      "Relevant technical stack",
      "Aligned with engineering roles",
    ],
  },
  {
    fitLabel: "Good fit",
    domain: "Engineering",
    title: "AI/ML Intern",
    skills: ["Python", "Machine Learning", "Data Analysis"],
    reasons: [
      "Python experience highlighted",
      "Project work in ML",
      "Matches your stated interests",
    ],
  },
  {
    fitLabel: "Strong fit",
    domain: "Business",
    title: "Data Analyst Intern",
    skills: ["SQL", "Tableau", "Statistics", "Python"],
    reasons: [
      "Analytics skills overlap",
      "Clear business domain fit",
      "Ready to review and apply",
    ],
  },
];

function HomeNav({ onLogin, onStart, onHow, onWhy }) {
  return (
    <header className="home-nav">
      <div className="home-nav__brand">
        <img src="/avyukt-logo.png" alt="" />
        Avyukt
      </div>
      <nav className="home-nav__links" aria-label="Page">
        <button type="button" className="home-nav__link" onClick={onHow}>
          How it works
        </button>
        <button type="button" className="home-nav__link" onClick={onWhy}>
          Why Avyukt
        </button>
      </nav>
      <div className="home-nav__actions">
        <button type="button" className="home-btn home-btn--ghost" onClick={onLogin}>
          Log in
        </button>
        <button type="button" className="home-btn home-btn--primary" onClick={onStart}>
          Get started
        </button>
      </div>
    </header>
  );
}

export default function Home() {
  const navigate = useNavigate();
  const goStart = () => navigate("/signup");
  const goLogin = () => navigate("/login");
  const goHow = () =>
    document.getElementById("how-it-works")?.scrollIntoView({ behavior: "smooth" });
  const goWhy = () =>
    document.getElementById("why-avyukt")?.scrollIntoView({ behavior: "smooth" });

  return (
    <div className="page page--home">
      <HomeNav onLogin={goLogin} onStart={goStart} onHow={goHow} onWhy={goWhy} />

      <section className="home-hero">
        <div className="home-hero__visual">
          <div className="home-hero__mark">
            <img src="/avyukt-logo.png" alt="" />
          </div>
          <span className="home-hero__index">Avyukt / 2026</span>
        </div>
        <div className="home-hero__copy">
          <p className="home-kicker">Opportunity matching</p>
          <h1 className="home-hero__title">
            Find work that <span>fits you.</span>
          </h1>
          <p className="home-lede">
            Ranked roles across Engineering, Business, and Healthcare — matched to
            your skills, interests, and career goals.
          </p>
          <div className="home-hero__cta">
            <button type="button" className="home-btn home-btn--primary" onClick={goStart}>
              Start profile
            </button>
            <button type="button" className="home-btn home-btn--ghost" onClick={goHow}>
              How it works
            </button>
          </div>
          <div className="home-hero__meta">
            <span><strong>Skill-ranked</strong> listings</span>
            <span><strong>Verified</strong> students</span>
            <span><strong>3</strong> domains</span>
          </div>
        </div>
      </section>

      <div className="home-flow" aria-hidden="true">
        <span>Profile</span>
        <i>/</i>
        <span>Skills</span>
        <i>/</i>
        <span>Match</span>
        <i>/</i>
        <span className="home-flow__accent">Rank</span>
        <i>/</i>
        <span>Apply</span>
      </div>

      <section className="home-section home-problem">
        <div className="home-problem__copy">
          <p className="home-kicker home-kicker--accent">The problem</p>
          <h2 className="home-h2">Stop applying randomly.</h2>
          <p className="home-lede">
            Students spend weeks hunting listings that were never ranked for them —
            then apply into the dark.
          </p>
          <ul className="home-bullets">
            <li>Search through endless listings</li>
            <li>Apply to irrelevant roles</li>
            <li>Spend hours searching</li>
            <li>Never know which roles actually fit your skills</li>
            <li>Struggle to prioritize opportunities</li>
          </ul>
        </div>
        <div className="home-problem__stack">
          <article className="home-stat-card">
            <span className="home-stat-card__index">01</span>
            <div>
              <strong>Blind applications</strong>
              <p>Sent without knowing whether the role actually fits.</p>
            </div>
          </article>
          <article className="home-stat-card">
            <span className="home-stat-card__index">02</span>
            <div>
              <strong>Low relevance</strong>
              <p>Roles that don&apos;t match your skills at all.</p>
            </div>
          </article>
          <article className="home-stat-card">
            <span className="home-stat-card__index">03</span>
            <div>
              <strong>Hours wasted</strong>
              <p>Searching, applying, and waiting to hear back.</p>
            </div>
          </article>
        </div>
      </section>

      <p className="home-better">There&apos;s a better way.</p>

      <section className="home-section" id="how-it-works">
        <p className="home-kicker">Process</p>
        <h2 className="home-h2">From profile to opportunity.</h2>
        <p className="home-lede">
          Six steps between you and work that actually fits.
        </p>
        <div className="home-steps">
          {STEPS.map((step) => (
            <article key={step.n} className="home-step">
              <span className="home-step__n">{step.n}</span>
              <div>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="home-section">
        <p className="home-kicker">Matching</p>
        <h2 className="home-h2">
          Not just jobs.
          <br />
          <span className="home-accent-text">The right jobs.</span>
        </h2>
        <p className="home-lede">
          Every opportunity is ranked against your profile — focus on roles that
          genuinely fit.
        </p>
        <div className="home-matches">
          {MATCHES.map((job) => (
            <article key={job.title} className="home-match">
              <div className="home-match__top">
                <span className="home-match__pct">{job.fitLabel}</span>
                <span className="home-match__domain">{job.domain}</span>
              </div>
              <h3>{job.title}</h3>
              <div className="home-match__skills">
                {job.skills.map((s) => (
                  <span key={s}>{s}</span>
                ))}
              </div>
              <p className="home-match__why-label">Why this matches</p>
              <ul>
                {job.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              <button type="button" className="home-btn home-btn--primary home-btn--sm" onClick={goStart}>
                Get matched
              </button>
            </article>
          ))}
        </div>
      </section>

      <section className="home-section" id="why-avyukt">
        <p className="home-kicker home-kicker--accent">Why Avyukt</p>
        <div className="home-why">
          <div>
            <h3>Personalized</h3>
            <p>Your opportunities should reflect your profile.</p>
          </div>
          <div>
            <h3>Intelligent</h3>
            <p>Find relevant roles instead of scrolling endlessly.</p>
          </div>
          <div>
            <h3>Verified</h3>
            <p>Trust matters when opportunities are involved.</p>
          </div>
        </div>
      </section>

      <section className="home-section home-cta-panel">
        <h2 className="home-h2 home-h2--center">
          Your next opportunity
          <br />
          <span className="home-accent-text">is out there.</span>
        </h2>
        <p className="home-lede home-lede--center">Build your profile. Get ranked.</p>
        <button type="button" className="home-btn home-btn--primary" onClick={goStart}>
          Create profile
        </button>
      </section>

      <section className="home-section home-profile">
        <div className="home-profile__copy">
          <p className="home-kicker">Your profile</p>
          <h2 className="home-h2">
            What Avyukt understands
            <span className="home-accent-text"> about you.</span>
          </h2>
          <p className="home-lede">
            Resume, skills, and proof of work — matching that isn&apos;t a keyword
            lottery.
          </p>
          <dl className="home-facts">
            <div>
              <dt>Skills</dt>
              <dd>The tools and languages you actually use.</dd>
            </div>
            <div>
              <dt>Domains</dt>
              <dd>Engineering, Business, Healthcare — ranked to you.</dd>
            </div>
            <div>
              <dt>Experience</dt>
              <dd>Opportunities, projects, and the links that prove it.</dd>
            </div>
          </dl>
        </div>
        <article className="home-id-card" aria-label="Example profile layout">
          <div className="home-id-card__head">
            <span className="home-id-card__avatar" aria-hidden="true">You</span>
            <div>
              <strong>Your profile</strong>
              <p>Engineering · student</p>
            </div>
            <span className="home-id-card__badge">Verified</span>
          </div>
          <p className="home-match__why-label">How matching works</p>
          <p className="home-id-card__meta">
            We read your resume, skills, and proof-of-work score, then rank open
            roles in Engineering, Business, and Healthcare.
          </p>
          <p className="home-match__why-label">Skills</p>
          <div className="home-match__skills">
            <span>React</span>
            <span>Python</span>
            <span>AWS</span>
          </div>
          <p className="home-match__why-label">Domains</p>
          <div className="home-match__skills">
            <span>Engineering</span>
          </div>
          <p className="home-id-card__meta">Resume and profile links on file</p>
        </article>
      </section>
    </div>
  );
}
