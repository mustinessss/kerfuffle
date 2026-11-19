import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import PublicApp from "./PublicApp";
import "./index.css";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PublicApp />
  </StrictMode>,
);
