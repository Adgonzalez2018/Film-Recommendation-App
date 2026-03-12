import React, {useState} from "react";
import { useNavigate } from "react-router-dom";

import "./Auth.css";
import backgroundImg from "../../assets/images/shining.png";
import AuthForm from "./components/AuthForm";

import { registerAction } from "../../api/auth";
import { useAuth } from "../../hooks/useAuth";


export default function SignUp() {
  const navigate = useNavigate();
  const { setAccessToken, setRefreshToken } = useAuth();
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSignUp = async ({ email, password }) => {
    const cleanEmail = (email || "").trim().toLowerCase();

    setLoading(true);
    setError(null);

    try {
      const data = await registerAction({email: cleanEmail, password});
      
      // backend returns access and refresh
      if (data?.access_token) setAccessToken(data.access_token);
      if (data?.refresh) setRefreshToken(data.refresh);
      navigate("/app"); 
    } catch (err) {
      setError(err.message || "Sign up failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthForm
      mode="signup"
      title="SIGN UP"
      backgroundImg={backgroundImg}
      onSubmit={handleSignUp}
      error={error}
      loading={loading}
    />
  );
}
