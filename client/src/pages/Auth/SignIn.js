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
    setLoading(true);
    setError(null);

    try{
      const data = await loginAction(email, password, navigate);
      // store token
      localStorage.setItem("access_token", data.access_token);
      
      // nav
      navigate("/chat");
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
