import { useEffect, useState } from "react";
import { useReducedMotion } from "framer-motion";

export default function CountUp({ value, suffix = "", duration = 520 }) {
  const reduced = useReducedMotion();
  const numeric = typeof value === "number" && Number.isFinite(value);
  const [display, setDisplay] = useState(numeric ? 0 : value);

  useEffect(() => {
    if (!numeric) {
      setDisplay(value);
      return;
    }
    if (reduced) {
      setDisplay(value);
      return;
    }

    const start = performance.now();
    let frame;

    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(Math.round(eased * value));
      if (t < 1) frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, numeric, reduced, duration]);

  if (!numeric) {
    return <span className="tabular-nums">{value}</span>;
  }

  return (
    <span className="tabular-nums">
      {display}
      {suffix}
    </span>
  );
}
