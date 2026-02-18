import React, {useState} from "react";
import "./Auth.css";
import { useNavigate } from "react-router-dom";
import AuthForm from "./components/AuthForm";

import backgroundImg from "../../assets/images/shining.png";

const registerAction = async (username, password, navigate) => {
  const response = await fetch("/api/register/", {
    method: "POST",
    body: JSON.stringify({ username, password }),
    headers: { "Content-Type": "application/json" },
  });
  
  const myJson = await response.json();
  if (response.status === 201) {
    localStorage.setItem("access_token", myJson.access_token);
    localStorage.setItem("username", username);
    navigate("/chat");
  }
  else {
    throw new Error(myJson.error || "Registration failed");
  }
}


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
