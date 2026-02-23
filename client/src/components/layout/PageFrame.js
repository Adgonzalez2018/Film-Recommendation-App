// PageFrame — pure CSS border-image, zero JS rendering
// Drop border-pattern.png into your /public folder (or adjust the import path)
import "./PageFrame.css";

export default function PageFrame() {
  return <div className="page-frame-border" aria-hidden="true" />;
}