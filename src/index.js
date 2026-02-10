import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import React, { useState, useEffect } from "react";
import "./styles.css";
import App from "./App";

const rootElement = document.getElementById("root");
const root = createRoot(rootElement);

root.render(
  <StrictMode>
    <App />
  </StrictMode>
);
