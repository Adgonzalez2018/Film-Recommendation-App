import React, { useState } from "react";
import ModalShell from "./ModalShell";

const ConfirmDeleteModal = ({ title, message, onCancel, onConfirm }) => {
  return (
    <ModalShell title={title} onClose={onCancel} className="confirm-modal">
      <div className="confirm-body">
        <p>{message}</p>
        <div className="confirm-actions">
          <button className="fb-cancel-btn" onClick={onCancel}>
            CANCEL
          </button>
          <button className="fb-submit-btn" onClick={onConfirm}>
            DELETE
          </button>
        </div>
      </div>
    </ModalShell>
  );
};

export default ConfirmDeleteModal;