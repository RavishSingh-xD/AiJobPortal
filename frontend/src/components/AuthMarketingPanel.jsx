export default function AuthMarketingPanel() {
  return (
    <aside className="auth-promo" aria-label="About Avyukt">
      <div className="auth-promo__grid" aria-hidden="true" />
      <div className="auth-promo__inner">
        <span className="auth-promo__badge">WELCOME TO AVYUKT</span>
        <h2 className="auth-promo__title">Your internship, matched by AI.</h2>
        <p className="auth-promo__lede">
          Build a profile once, verify your identity, and explore roles ranked to
          your skills — not a generic job board.
        </p>

        <ul className="auth-promo__features">
          <li>
            <span className="auth-promo__feature-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z" />
                <path d="M5 19l1 3 1-3 3-1-3 1-1-3-1 3z" />
              </svg>
            </span>
            <span>Roles ranked to your resume and domain test</span>
          </li>
          <li>
            <span className="auth-promo__feature-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                <path d="M13 2L4 14h7l-1 8 10-14h-7l1-8z" />
              </svg>
            </span>
            <span>Apply with a profile that already knows who you are</span>
          </li>
          <li>
            <span className="auth-promo__feature-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                <path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z" />
              </svg>
            </span>
            <span>Built for students — early access as we grow listings</span>
          </li>
        </ul>

        <div className="auth-promo__profile">
          <div className="auth-promo__profile-main">
            <span className="auth-promo__avatar">You</span>
            <div>
              <p className="auth-promo__profile-name">Your profile</p>
              <p className="auth-promo__profile-role">Skills, resume, and proof of work</p>
            </div>
          </div>
          <span className="auth-promo__match-badge">Ranked matches</span>
        </div>

        <p className="auth-promo__footnote">
          We&apos;re onboarding students and expanding live listings across
          Engineering, Business, and Healthcare.
        </p>
      </div>
    </aside>
  );
}
