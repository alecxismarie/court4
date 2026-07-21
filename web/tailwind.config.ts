import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        court: {
          ink: "#17211b",
          muted: "#5c6f64",
          line: "#d8e1dc",
          panel: "#f7faf8",
          surface: "#ffffff",
          green: "#176b4d",
          lime: "#9cbf33",
          limeDark: "#7f9f24",
          navy: "#061f38",
          blue: "#245c9f",
          amber: "#a05d00",
          red: "#b42318",
        },
      },
      boxShadow: {
        panel: "0 10px 24px rgba(21, 35, 28, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
