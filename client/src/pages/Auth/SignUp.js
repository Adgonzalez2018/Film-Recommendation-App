import React, {useState} from "react";
import { useNavigate } from "react-router-dom";

import "./Auth.css";
import backgroundImg from "../../assets/images/shining.png";
import AuthForm from "./components/AuthForm";

import { registerAction } from "../../api/auth";



export default function SignUp() {
  const navigate = useNavigate();
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSignUp = async ({ username, password }) => {
    setLoading(true);
    setError(null);
    try {
      await registerAction(username, password, navigate);
    } catch (err) {
      setError(err.message);
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
