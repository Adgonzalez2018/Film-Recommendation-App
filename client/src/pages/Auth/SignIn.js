import React, {useState} from "react";
import "./Auth.css";
import { useNavigate } from "react-router-dom";
import AuthForm from "./components/AuthForm";
import backgroundImg from "../../assets/images/shining.png";

const loginAction = async (username, password, navigate) => {
  const response = await fetch("/api/login/", {
    method: "POST",
    body: JSON.stringify({ username, password }),
    headers: { "Content-Type": "application/json" },
  });

  // gives me back the token and status
  const myJson = await response.json();
  // if status is 200, then we save the token and username in localStorage and set authed to true
  if (response.status === 200) {
    localStorage.setItem("access_token", myJson.access_token);
    localStorage.setItem("username", username);
    navigate("/connect");
  } else {
    throw new Error(myJson.error || "Login failed");
  }
} 

export default function SignIn() {
  const navigate = useNavigate();
  const[error, setError] = useState(null);
  const [loading, setLoading] = useState(false); 

  const handleSignIn = async ({ username, password }) => {
    setLoading(true);
    setError(null);
    try{
      await loginAction(username, password, navigate);
    } catch (err) {
      setError(err.message);
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
