import { useNavigate } from "react-router-dom";
import LiquidGlassCanvas from "../components/LiquidGlassCanvas";
import GlassCard from "../components/GlassCard";
import AnimatedButton from "../components/AnimatedButton";

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="page page--landing">
      <LiquidGlassCanvas />
      <div className="landing">
        <p className="landing__brand">Avyukt.work</p>
        <h1 className="landing__title">See the opportunities that actually fit you</h1>
        <p className="landing__lede">
          Ranked matches from your resume and a short domain test — then apply
          with a profile that already knows who you are.
        </p>
        <GlassCard className="landing__card" hover={false}>
          <div className="landing__actions">
            <AnimatedButton type="button" onClick={() => navigate("/signup")}>
              Create account
            </AnimatedButton>
            <AnimatedButton
              type="button"
              secondary
              onClick={() => navigate("/login")}
            >
              Log in
            </AnimatedButton>
          </div>
        </GlassCard>
      </div>
    </div>
  );
}
