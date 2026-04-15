import React from "react";
import ModalShell from "./ModalShell";

const UpdatesModal = ({ onClose, version, updates = [] }) => {
  return (
    <ModalShell
      title={`FILM-RECOMMENDER ${version}`}
      onClose={onClose}
      className="updates-modal"
    >
      <div className="updates-modal-body">
        <p className="updates-intro">Latest changes to the system:</p>

        <ul className="updates-list">
          {updates.map((item, idx) => (
            <li key={idx} className="updates-list-item">
              {item}
            </li>
          ))}
        </ul>

        <div className="updates-actions">
          <button className="updates-close-btn" onClick={onClose}>
            CLOSE
          </button>
        </div>
      </div>
    </ModalShell>
  );
};

export default UpdatesModal;