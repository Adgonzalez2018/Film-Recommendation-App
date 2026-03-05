import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";

export default function AuthForm({
  mode = "signin",
  title = "SIGN IN",
  backgroundImg,
  onSubmit,
  error,
  loading,
}) {
  const isSignIn = mode === "signin";

  const [formData, setFormData] = useState({
    email: "",
    password: "",
    confirmPassword: "",
  });

  const [formError, setFormError] = useState(null);

  const canSubmit = useMemo(() => {
    const emailOk = (formData.email || "").trim().length > 0;
    const passOk = (formData.password || "").length >0;
    const confirmOk = isSignIn ? true : (formData.confirmPassword || "").length > 0;
    return emailOk && passOk && confirmOk && !loading;
  }, [formData, isSignIn, loading]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormError(null);
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setFormError(null);
    
    const email = (formData.email || "").trim();
    const password = formData.password || "";
    const confirmPassword = formData.confirmPassword || "";
    
    if (!email || !password) {
      alert("Please fill in all fields!");
      return;
    }

    if (!isSignIn && password !== confirmPassword) {
      alert("Passwords do not match!");
      return;
    }

    onSubmit?.({ email, password });
  };

  return (
    <div className="auth-container">
      <div
        className="auth-background"
        style={{ backgroundImage: `url(${backgroundImg})` }}
      />

      <div className="auth-box">
        <h2 className="auth-title">{title}</h2>

        {(error || formError) && ( <div className="auth-error">{error}</div>)}
        
        <form onSubmit={handleSubmit}>
          <div className="auth-group">
            <label className="auth-label">EMAIL</label>
            <input
              className="neon-field"
              type="email"
              name="email"
              placeholder="Enter your email"
              value={formData.email}
              onChange={handleChange}
              required
              disabled={loading}
              autoComplete="email"
              inputMode="email"
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
              disabled={loading}
              autoComplete={isSignIn ? "current-password" : "new-password"}
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
                disabled={loading}
                autoComplete="new-password"
              />
            </div>
          )}

          <button type="submit" className="auth-button" disabled={!canSubmit}>
            {loading ? "Loading..." : isSignIn ? "ENTER" : "CREATE ACCOUNT"}
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
              Already have an account?{" "}
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