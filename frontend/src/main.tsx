import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { DocumentViewer } from "./pages/DocumentViewer";

// /documents/{id} is a self-hosted "target page" (see DocumentViewer.tsx) —
// ReviewFrame iframes it just like an external app, so it needs its own
// path-based entry point rather than the tabbed App shell. A single extra
// route isn't worth pulling in a router library for.
const documentMatch = window.location.pathname.match(/^\/documents\/([^/]+)/);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {documentMatch ? <DocumentViewer documentId={documentMatch[1]} /> : <App />}
  </React.StrictMode>,
);
