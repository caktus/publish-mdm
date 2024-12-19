/** @type {import('tailwindcss').Config} */
// https://coolors.co/ed1d24-007cba-01bcf4-e2efde-9b7e46
module.exports = {
  darkMode: "class",
  content: [
    "./apps/**/*.{html,js}",
    "./config/**/*.{html,js}",
    "./node_modules/flowbite/**/*.js",
    "./apps/chat/templatetags/chat_tags.py",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          light: "#D2CEDE",
          100: "#33BBFF",
          200: "#1FB4FF",
          300: "#0AADFF",
          400: "#00A3F5",
          500: "#0096E0",
          600: "#0088CC",
          700: "#007CBA",
          800: "#006DA3",
          900: "#005F85",
          dark: "#363249",
        },
        brand: {
          primary: {
            light: "#595379",
            medium: "#413C58",
            dark: "#363249",
          },
          accent: {
            light: "#E8E7EE", // input bg
            medium: "#363249", // input border
          },
          gray: {
            light: "rgb(107 114 128)",
            medium: "rgb(107 114 128)",
          },
          danger: {
            light: "rgb(254 229 229)",
            medium: "rgb(244 72 77)",
          },
        },
      },
    },
    fontFamily: {
      body: [
        "Inter",
        "ui-sans-serif",
        "system-ui",
        "-apple-system",
        "system-ui",
        "Segoe UI",
        "Roboto",
        "Helvetica Neue",
        "Arial",
        "Noto Sans",
        "sans-serif",
        "Apple Color Emoji",
        "Segoe UI Emoji",
        "Segoe UI Symbol",
        "Noto Color Emoji",
      ],
      sans: [
        "Inter",
        "ui-sans-serif",
        "system-ui",
        "-apple-system",
        "system-ui",
        "Segoe UI",
        "Roboto",
        "Helvetica Neue",
        "Arial",
        "Noto Sans",
        "sans-serif",
        "Apple Color Emoji",
        "Segoe UI Emoji",
        "Segoe UI Symbol",
        "Noto Color Emoji",
      ],
    },
  },
  plugins: [require("flowbite/plugin")],
};
