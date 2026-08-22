import { useEffect, useRef } from "react";

export default function LiquidGlassCanvas() {
  const turbulenceRef = useRef(null);
  const frameRef = useRef(0);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    let reduced = media.matches;
    let visible = document.visibilityState === "visible";
    let time = 0;

    const onMotion = (event) => {
      reduced = event.matches;
    };
    const onVisibility = () => {
      visible = document.visibilityState === "visible";
    };

    media.addEventListener("change", onMotion);
    document.addEventListener("visibilitychange", onVisibility);

    const tick = () => {
      frameRef.current = requestAnimationFrame(tick);
      if (reduced || !visible) {
        return;
      }
      time += 0.006;
      const node = turbulenceRef.current;
      if (!node) {
        return;
      }
      const fx = (0.007 + Math.sin(time) * 0.002).toFixed(4);
      const fy = (0.011 + Math.cos(time * 0.65) * 0.003).toFixed(4);
      node.setAttribute("baseFrequency", `${fx} ${fy}`);
    };

    frameRef.current = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frameRef.current);
      media.removeEventListener("change", onMotion);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return (
    <div className="liquid-glass-canvas" aria-hidden="true">
      <svg className="liquid-glass-canvas__svg" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <filter id="liquid-glass-filter" x="-20%" y="-20%" width="140%" height="140%">
            <feTurbulence
              ref={turbulenceRef}
              id="liquidNoise"
              type="fractalNoise"
              baseFrequency="0.008 0.012"
              numOctaves="2"
              seed="3"
              result="noise"
            />
            <feDisplacementMap
              in="SourceGraphic"
              in2="noise"
              scale="28"
              xChannelSelector="R"
              yChannelSelector="G"
            />
            <feGaussianBlur stdDeviation="0.6" />
          </filter>
          <linearGradient id="liquid-glass-grad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#e8a882" stopOpacity="0.32" />
            <stop offset="45%" stopColor="#8fad9a" stopOpacity="0.14" />
            <stop offset="100%" stopColor="#c46d47" stopOpacity="0.2" />
          </linearGradient>
        </defs>
        <rect
          width="100%"
          height="100%"
          fill="url(#liquid-glass-grad)"
          filter="url(#liquid-glass-filter)"
        />
      </svg>
    </div>
  );
}
