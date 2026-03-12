import React, {useState} from "react";
import "./Auth.css";
import { useNavigate } from "react-router-dom";
import AuthForm from "./components/AuthForm";
import backgroundImg from "../../assets/images/shining.png";
import { loginAction } from "../../api/auth";
import { useAuth } from "../../hooks/useAuth";

export default function SignIn() {
  const navigate = useNavigate();
  const { setAccessToken, setRefreshToken } = useAuth();

  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSignIn = async ({ email, password }) => {
    const cleanEmail = (email || "").trim().toLowerCase();

    setLoading(true);
    setError(null);

    try {
      const data = await loginAction({ email: cleanEmail, password });

      if (data?.access_token) setAccessToken(data.access_token);
      if (data?.refresh) setRefreshToken(data.refresh);

      navigate("/app");
    } catch (err){
      setError(err.message || "Sign in failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthForm
      mode="signin"
      title="SIGN IN"
      backgroundImg={backgroundImg}
      onSubmit={handleSignIn}
      error={error}
      loading={loading}
    />
  );
}
