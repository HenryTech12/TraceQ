import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0f172a",
        paper: "#0b0e14",
        panel: "#12161f",
        border: "#232936",
        muted: "#8a93a6",
        verified: "#34d399",
        derived: "#fbbf24",
        norecord: "#8a93a6",
        accent: "#6ea8fe",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
