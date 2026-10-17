import js from "@eslint/js";
import globals from "globals";

export default [
  { ignores: ["node_modules/**", "runtime/**", "build/**", ".venv*/**"] },
  {
    files: ["src/yolo_studio/web/static/*.js"],
    languageOptions: { sourceType: "script", globals: globals.browser },
    rules: { ...js.configs.recommended.rules },
  },
  {
    files: ["src/yolo_studio/web/static/app.js", "src/yolo_studio/web/static/monitor.js"],
    languageOptions: {
      globals: {
        toggleViewerFullscreen: "readonly",
        serverAudio: "readonly",
        clientMicrophone: "readonly",
        PCMPlayer: "readonly",
      },
    },
  },
  {
    files: [
      "src/yolo_studio/web/static/audio.js",
      "src/yolo_studio/web/static/viewer.js",
      "src/yolo_studio/web/static/client-audio.js",
      "src/yolo_studio/web/static/pcm-player.js",
    ],
    rules: {
      "no-unused-vars": [
        "error",
        { varsIgnorePattern: "^(serverAudio|toggleViewerFullscreen|clientMicrophone|PCMPlayer)$" },
      ],
    },
  },
  {
    files: ["src/yolo_studio/web/static/client-audio-worklet.js"],
    languageOptions: {
      globals: {
        AudioWorkletProcessor: "readonly",
        sampleRate: "readonly",
        registerProcessor: "readonly",
      },
    },
  },
];
