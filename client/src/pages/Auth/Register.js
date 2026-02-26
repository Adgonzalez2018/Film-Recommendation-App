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
      const data = await registerAction(username, password, navigate);
      localStorage.setItem("access_token", data.access_token);

      // navigate 
      navigate("/connect"); 
      
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
