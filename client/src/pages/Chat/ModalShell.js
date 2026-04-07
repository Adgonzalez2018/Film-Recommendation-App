import React from "react";

const ModalShell = ({ title, onClose, children, className = "" }) => {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className={`modal-panel ${className}`} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">{title}</span>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
};

export default ModalShell;