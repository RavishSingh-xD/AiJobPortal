const FEATURES = [
  "Roles ranked to your resume and domain test",
  "Apply with a profile that already knows who you are",
  "Built for students — early access as we grow listings",
];

export default function AuthMarketingPanel() {
  return (
    <aside className="auth-promo" aria-label="About Avyukt">
      <div className="auth-promo__inner">
        <span className="auth-promo__badge">Avyukt</span>
        <h2 className="auth-promo__title">Your internship, matched.</h2>
        <p className="auth-promo__lede">
          Build a profile once, verify your identity, and explore roles ranked to
          your skills — not a generic job board.
        </p>

        <ul className="auth-promo__features">
          {FEATURES.map((text, i) => (
            <li key={text}>
              <span className="auth-promo__feature-index">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span>{text}</span>
            </li>
          ))}
        </ul>

        <div className="auth-promo__profile">
          <div className="auth-promo__profile-main">
            <span className="auth-promo__avatar">You</span>
            <div>
              <p className="auth-promo__profile-name">Your profile</p>
              <p className="auth-promo__profile-role">Skills, resume, proof of work</p>
            </div>
          </div>
          <span className="auth-promo__match-badge">Ranked</span>
        </div>

        <p className="auth-promo__footnote">
          Onboarding students across Engineering, Business, and Healthcare.
        </p>
      </div>
    </aside>
  );
}
