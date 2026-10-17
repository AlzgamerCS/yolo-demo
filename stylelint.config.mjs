export default {
  extends: ["stylelint-config-standard"],
  rules: {
    // Responsive overrides intentionally follow the base component rules.
    "no-descending-specificity": null,
    // DOM IDs follow the JavaScript camelCase convention; classes remain kebab-case.
    "selector-id-pattern": "^[a-z][a-zA-Z0-9]*$",
  },
};
