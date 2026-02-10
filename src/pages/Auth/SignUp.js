import React from "react";
import "./Auth.css";
import { useNavigate } from "react-router-dom";
import AuthForm from "./components/AuthForm";

// background image (you can swap later)
import backgroundImg from "../../assets/images/shining.png";

export default function SignUp() {
  const navigate = useNavigate();

  const handleSignUp = ({ username, password }) => {
    // MVP fake signup
    localStorage.setItem("username", username);
    localStorage.setItem("authed", "true");

    console.log("User signed up:", { username, password });
    navigate("/chat");
  };

  return (
    <AuthForm
      mode="signup"
      title="SIGN UP"
      backgroundImg={backgroundImg}
      onSubmit={handleSignUp}
    />
  );
}
