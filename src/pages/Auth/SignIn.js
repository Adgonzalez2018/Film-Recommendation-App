import React from "react";
import "./Auth.css";
import { useNavigate } from "react-router-dom";
import AuthForm from "./components/AuthForm";
import backgroundImg from "../../assets/images/shining.png";

export default function SignIn() {
  const navigate = useNavigate();

  const handleSignIn = ({ username }) => {
    // MVP fake login
    localStorage.setItem("username", username);
    localStorage.setItem("authed", "true");
    navigate("/chat");
  };

  return (
    <AuthForm
      mode="signin"
      title="SIGN IN"
      backgroundImg={backgroundImg}
      onSubmit={handleSignIn}
    />
  );
}
