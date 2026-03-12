import React, {useState} from "react";
import "./Auth.css";
import { useNavigate } from "react-router-dom";
import AuthForm from "./components/AuthForm";
import backgroundImg from "../../assets/images/shining.png";
import { loginAction } from "../../api/auth";

export default function SignIn() {
  const navigate = useNavigate();
  const[error, setError] = useState(null);
  const [loading, setLoading] = useState(false); 

  const handleSignIn = async ({ email, password }) => {
    const cleanEmail = (email || "").trim().toLowerCase();

    setLoading(true);
    setError(null);

    try{
      const data = await loginAction({email: cleanEmail, password});
      // store token & refresh
      if (data?.access_token) localStorage.setItem("access_token", data.access_token);
      if (data?.refresh) localStorage.setItem("refresh", data.refresh);
      // navigate
      navigate("/chat");
    } catch (err) {
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
