import { useNavigate } from "react-router-dom";
import AnimatedButton from "../components/AnimatedButton";

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="page page--landing">
      <div className="landing">
        <p className="landing__brand">Avyukt</p>
        <h1 className="landing__title">Opportunities that fit you</h1>
        <p className="landing__lede">
          Ranked matches from your resume and a short domain test — apply with a
          profile that already knows who you are.
        </p>
        <div className="landing__card">
          <div className="landing__actions">
            <AnimatedButton type="button" className="btn--compact" onClick={() => navigate("/signup")}>
              Create account
            </AnimatedButton>
            <AnimatedButton
              type="button"
              secondary
              className="btn--compact"
              onClick={() => navigate("/login")}
            >
              Log in
            </AnimatedButton>
          </div>
        </div>
      </div>
    </div>
  );
}
