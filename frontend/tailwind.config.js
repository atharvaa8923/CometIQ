/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ['"Inter Variable"', "system-ui", "sans-serif"] },
      colors: {
        comet: {
          50: "#ecf7f2", 100: "#d1ecdf", 200: "#a6d9c1", 300: "#6fbf9b", 400: "#3f9f77",
          500: "#23825d", 600: "#17684a", 700: "#12533c", 800: "#0e4231", 900: "#0b3628", 950: "#062019",
        },
        flame: {
          50: "#fff5eb", 100: "#ffe6cc", 200: "#ffc999", 300: "#ffa65c", 400: "#ff8a2e",
          500: "#e87500", 600: "#b45309", 700: "#9c4a04", 800: "#7e3d0b", 900: "#68330c",
        },
        navy: { 500: "#1f4e79", 600: "#173f63", 700: "#11304d" },
      },
      boxShadow: { card: "0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.08)" },
    },
  },
  plugins: [],
};
