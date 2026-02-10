import React, { useState } from "react";
import { Link } from "react-router-dom";

export default function AuthForm({
  mode = "signin", // "signin" | "signup"
  title = "SIGN IN",
  backgroundImg,
  onSubmit,
}) {
  const isSignIn = mode === "signin";

  const [formData, setFormData] = useState({
    username: "",
    password: "",
    confirmPassword: "",
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    const { username, password, confirmPassword } = formData;

    if (!username || !password) {
      alert("Please fill in all fields!");
      return;
    }

    if (!isSignIn && password !== confirmPassword) {
      alert("Passwords do not match!");
      return;
    }

    onSubmit?.({ username, password });
  };

  return (
    <div className="auth-container">
      <div
        className="auth-background"
        style={{ backgroundImage: `url(${backgroundImg})` }}
      />

      <div className="auth-box">
        <h2 className="auth-title">{title}</h2>

        <form onSubmit={handleSubmit}>
          <div className="auth-group">
            <label className="auth-label">USERNAME</label>
            <input
              className="neon-field"
              type="text"
              name="username"
              placeholder="Enter your Letterboxd username"
              value={formData.username}
              onChange={handleChange}
              required
            />
          </div>

          <div className="auth-group">
            <label className="auth-label">PASSWORD</label>
            <input
              className="neon-field"
              type="password"
              name="password"
              placeholder="Enter password"
              value={formData.password}
              onChange={handleChange}
              required
            />
          </div>

          {!isSignIn && (
            <div className="auth-group">
              <label className="auth-label">CONFIRM PASSWORD</label>
              <input
                className="neon-field"
                type="password"
                name="confirmPassword"
                placeholder="Confirm password"
                value={formData.confirmPassword}
                onChange={handleChange}
                required
              />
            </div>
          )}

          <button type="submit" className="auth-button">
            {isSignIn ? "ENTER" : "CREATE ACCOUNT"}
          </button>
        </form>

        <p className="auth-switch">
          {isSignIn ? (
            <>
              Need an account?{" "}
              <Link to="/signup" className="auth-link">
                Sign Up
              </Link>
            </>
          ) : (
            <>
              Already have an account?
              <Link to="/signin" className="auth-link">
                Sign In
              </Link>
            </>
          )}
        </p>
      </div>
    </div>
  );
}
