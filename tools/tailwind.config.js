/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: ['./dist/index.html'],
  corePlugins: {
    float: false, clear: false, skew: false, caretColor: false,
    sepia: false, hueRotate: false, saturate: false,
    backdropBlur: false, backdropBrightness: false, backdropContrast: false,
    backdropGrayscale: false, backdropHueRotate: false, backdropInvert: false,
    backdropOpacity: false, backdropSaturate: false, backdropSepia: false,
    ringOffsetWidth: false, ringOffsetColor: false,
    scrollSnapType: false, scrollSnapAlign: false, touchAction: false,
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
};
