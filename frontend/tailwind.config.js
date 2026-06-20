/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Clinical night-monitor palette (deep blue-slate, not neutral charcoal)
        ground: "#0C1116",
        surface: "#131C26",
        "surface-2": "#1B2733",
        line: "#26333F",
        text: "#E6EDF3",
        muted: "#8A97A6",
        faint: "#5B6877",
        accent: "#2DD4BF", // teal — vitals / AI
        "accent-dim": "#1B8C7E",
        amber: "#F5B544", // pending human review
        ok: "#34D399", // approved / grounded
        danger: "#F87171", // rejected / ungrounded
      },
      fontFamily: {
        display: ["Space Grotesk", "ui-sans-serif", "system-ui", "sans-serif"],
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        card: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 24px -12px rgba(0,0,0,0.6)",
        glow: "0 0 0 1px rgba(45,212,191,0.25), 0 0 24px -6px rgba(45,212,191,0.35)",
      },
      keyframes: {
        pulseline: {
          "0%, 100%": { opacity: "0.35" },
          "50%": { opacity: "1" },
        },
        scan: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(400%)" },
        },
        rise: {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        pulseline: "pulseline 1.8s ease-in-out infinite",
        scan: "scan 1.4s linear infinite",
        rise: "rise 0.35s ease-out both",
      },
    },
  },
  plugins: [],
};
