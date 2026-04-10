/** @type {import('tailwindcss').Config} */
// https://coolors.co/ed1d24-007cba-01bcf4-e2efde-9b7e46
module.exports = {
  darkMode: "class",
  content: [
    "./apps/**/*.{html,js,py}",
    "./config/**/*.{html,js}",
    "./node_modules/flowbite/**/*.js",
  ],
  plugins: [require("flowbite/plugin")],
};
