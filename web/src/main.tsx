import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./theme/tokens.css";
import "./app/app.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { initTheme } from "./theme/theme";

initTheme();

const container = document.getElementById("root");
if (container === null) {
  throw new Error("index.html must provide a #root element");
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
