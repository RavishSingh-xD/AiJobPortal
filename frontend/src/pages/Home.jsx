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
    text: "Browse internships and jobs across Engineering, Business, and Healthcare.",
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
    pct: "94% Match",
    domain: "Engineering",
    title: "Software Engineering Intern",
    skills: ["React", "Python", "AWS", "DSA"],
    reasons: [
      "Strong frontend experience",
      "Relevant technical skills",
      "Matching career interests",
    ],
  },
  {
    pct: "87% Match",
    domain: "Engineering",
    title: "AI/ML Intern",
    skills: ["Python", "Machine Learning", "Data Analysis"],
    reasons: [
      "Python depth on your profile",
      "Project work in ML",
      "Aligned with your goals",
    ],
  },
  {
    pct: "91% Match",
    domain: "Business",
    title: "Data Analyst Intern",
    skills: ["SQL", "Tableau", "Statistics", "Python"],
    reasons: [
      "Analytics skill overlap",
      "Clear domain fit",
      "Ready to apply now",
    ],
  },
];

function HomeNav({ onLogin, onStart, onHow, onWhy }) {
  return (
    <header className="home-nav">
      <div className="home-nav__brand">
        <span className="home-nav__mark" aria-hidden="true">
          A
        </span>
        Avyukt
      </div>
      <nav className="home-nav__links" aria-label="Page">
        <button type="button" className="home-nav__link" onClick={onHow}>
          How It Works
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
          Get Started
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
          <div className="home-orb" aria-hidden="true">
            <span className="home-orb__ring home-orb__ring--1" />
            <span className="home-orb__ring home-orb__ring--2" />
            <div className="home-orb__tile">A</div>
          </div>
          <span className="home-chip home-chip--verified">✓ Verified</span>
        </div>
        <div className="home-hero__copy">
          <p className="home-kicker">AI-powered internship matching</p>
          <h1 className="home-hero__title">
            Find work that actually <span>fits you.</span>
          </h1>
          <p className="home-lede">
            AI-powered internship matching built around your skills, interests
            and career goals.
          </p>
          <div className="home-hero__cta">
            <button type="button" className="home-btn home-btn--primary" onClick={goStart}>
              Find My Internships →
            </button>
            <button type="button" className="home-btn home-btn--ghost" onClick={goHow}>
              See How It Works ↓
            </button>
          </div>
          <div className="home-hero__badges">
            <span className="home-chip">94% Match</span>
            <span className="home-chip">AI Ranked</span>
          </div>
        </div>
      </section>

      <div className="home-flow" aria-hidden="true">
        <span>👤 Student Profile</span>
        <i>→</i>
        <span>🧠 Skills</span>
        <i>→</i>
        <span>✨ AI Matching</span>
        <i>→</i>
        <span className="home-flow__accent">📊 94% Match</span>
        <i>→</i>
        <span>💼 Internship</span>
      </div>

      <section className="home-section home-problem">
        <div className="home-problem__copy">
          <p className="home-kicker home-kicker--accent">The problem</p>
          <h2 className="home-h2">Stop applying randomly.</h2>
          <p className="home-lede">
            Students spend weeks hunting internships across listings that were
            never ranked for them — then apply into the dark.
          </p>
          <ul className="home-bullets">
            <li>Search through hundreds of listings</li>
            <li>Apply to irrelevant roles</li>
            <li>Spend hours searching</li>
            <li>Never know which roles actually fit your skills</li>
            <li>Struggle to prioritize opportunities</li>
          </ul>
        </div>
        <div className="home-problem__stack">
          <article className="home-stat-card">
            <span className="home-stat-card__icon home-stat-card__icon--blue">📭</span>
            <div>
              <strong>50+ applications</strong>
              <p>sent without ever knowing if they fit.</p>
            </div>
          </article>
          <div className="home-stat-card__arrow">↓</div>
          <article className="home-stat-card">
            <span className="home-stat-card__icon home-stat-card__icon--pink">◎</span>
            <div>
              <strong>Low relevance</strong>
              <p>roles that don&apos;t match your skills at all.</p>
            </div>
          </article>
          <div className="home-stat-card__arrow">↓</div>
          <article className="home-stat-card home-stat-card--glow">
            <span className="home-stat-card__icon home-stat-card__icon--gold">⏳</span>
            <div>
              <strong>Hours wasted</strong>
              <p>searching, applying, and waiting to hear back.</p>
            </div>
          </article>
        </div>
      </section>

      <p className="home-better">There&apos;s a better way.</p>

      <section className="home-section" id="how-it-works">
        <p className="home-kicker">How Avyukt works</p>
        <h2 className="home-h2">From profile to internship.</h2>
        <p className="home-lede">
          Six simple steps between you and work that actually fits.
        </p>
        <div className="home-steps">
          {STEPS.map((step) => (
            <article key={step.n} className="home-step">
              <span className="home-step__n">{step.n}</span>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="home-section">
        <p className="home-kicker">Matching</p>
        <h2 className="home-h2">
          Not just jobs.
          <br />
          <span className="home-gradient-text">The right jobs.</span>
        </h2>
        <p className="home-lede">
          Every opportunity is ranked against your profile — so you can focus
          on the roles that genuinely fit.
        </p>
        <div className="home-matches">
          {MATCHES.map((job) => (
            <article key={job.title} className="home-match">
              <div className="home-match__top">
                <span className="home-match__pct">● {job.pct}</span>
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
                Get matched →
              </button>
            </article>
          ))}
        </div>
      </section>

      <section className="home-section" id="why-avyukt">
        <p className="home-kicker home-kicker--accent">Why Avyukt</p>
        <div className="home-why">
          <div>
            <h3 className="home-gradient-text">Personalized</h3>
            <p>Your opportunities should reflect your profile.</p>
          </div>
          <div>
            <h3 className="home-gradient-text">Intelligent</h3>
            <p>Find relevant roles instead of scrolling endlessly.</p>
          </div>
          <div>
            <h3 className="home-gradient-text">Verified</h3>
            <p>Trust matters when opportunities are involved.</p>
          </div>
        </div>
      </section>

      <section className="home-section home-cta-panel">
        <div className="home-cta-panel__inner">
          <h2 className="home-h2 home-h2--center">
            Your next
            <br />
            opportunity
            <br />
            <span className="home-gradient-text">is out there.</span>
          </h2>
          <p className="home-lede home-lede--center">Let Avyukt help you find it.</p>
          <button type="button" className="home-btn home-btn--primary" onClick={goStart}>
            Create Your Profile →
          </button>
        </div>
      </section>

      <section className="home-section home-profile">
        <div className="home-profile__copy">
          <p className="home-kicker">Your profile</p>
          <h2 className="home-h2">
            Here&apos;s what Avyukt understands{" "}
            <span className="home-gradient-text">about you.</span>
          </h2>
          <p className="home-lede">
            Avyukt reads your resume, skills, and proof of work so matching
            isn&apos;t a keyword lottery.
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
              <dd>Internships, projects, and the links that prove it.</dd>
            </div>
          </dl>
        </div>
        <article className="home-id-card">
          <div className="home-id-card__head">
            <span className="home-id-card__avatar" aria-hidden="true">
              A
            </span>
            <div>
              <strong>Aarav Sharma</strong>
              <p>Engineering • B.Tech CSE</p>
            </div>
            <span className="home-chip home-chip--verified">Verified</span>
          </div>
          <p className="home-match__why-label">Match score</p>
          <p className="home-id-card__score">
            <span>94</span>/100
          </p>
          <div className="home-id-card__bar" aria-hidden="true">
            <i style={{ width: "94%" }} />
          </div>
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
          <p className="home-id-card__meta">2 internships • 3 projects</p>
          <p className="home-id-card__meta">✓ resume.pdf</p>
        </article>
      </section>
    </div>
  );
}
