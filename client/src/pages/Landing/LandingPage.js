import React from "react";
import "./LandingPage.css";
import { useNavigate } from "react-router-dom";

// the thing background
import backgroundImg from "../../assets/images/thething.png";

export default function LandingPage() {
  const navigate = useNavigate();
  const handleSignIn = () => {
    navigate("/signin");
  };

  return (
    <div
      className="landing-page"
      style={{
        backgroundImage: `url(${backgroundImg})`,
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundRepeat: "no-repeat",
      }}
    >
      <div className="film-grain"></div>
      <div className="vignette"></div>
      <div className="content">
        <h2 className="creator-name">ALEX G'S</h2>
        <h1 className="title">
          THE FILM
          <br />
          RECOMMENDER
        </h1>

        {/* Sign In button - fades in last */}
        <button className="sign-in-button" onClick={handleSignIn}>
          SIGN IN
        </button>
      </div>
    </div>
  );
}
