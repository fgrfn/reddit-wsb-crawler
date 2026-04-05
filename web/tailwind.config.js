/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#FF4500",
          dark: "#cc3700",
        },
      },
    },
  },
  plugins: [],
};
