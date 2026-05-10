/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,jsx,ts,tsx}",
    "./components/**/*.{js,jsx,ts,tsx}",
    "./lib/**/*.{js,jsx,ts,tsx}",
  ],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        bimi: {
          base: "#0A0A0F",
          card: "rgba(255,255,255,0.04)",
          elevated: "rgba(255,255,255,0.08)",
          glass: "rgba(255,255,255,0.06)",
          "border-subtle": "rgba(255,255,255,0.08)",
          "border-active": "rgba(240,160,96,0.4)",
          "text-primary": "#F0F0F5",
          "text-secondary": "#8B8BA3",
          "text-muted": "#5A5A72",
          accent: "#F0A060",
          "accent-dim": "rgba(240,160,96,0.15)",
          secondary: "#E07A5F",
          success: "#34D399",
          "success-dim": "rgba(52,211,153,0.12)",
          danger: "#F87171",
          "danger-dim": "rgba(248,113,113,0.12)",
          warning: "#FBBF24",
          "warning-dim": "rgba(251,191,36,0.12)",
          info: "#60A5FA",
          "info-dim": "rgba(96,165,250,0.12)",
        },
      },
      fontFamily: {
        sans: ["System"],
      },
      borderRadius: {
        card: "16px",
      },
      spacing: {
        base: "16px",
      },
    },
  },
  plugins: [],
};
