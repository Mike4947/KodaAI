import { Link, Route, Routes, useLocation } from "react-router-dom";
import Home from "./pages/Home";
import Scan from "./pages/Scan";
import Prompts from "./pages/Prompts";
import Pentests from "./pages/Pentests";

export default function App() {
  const location = useLocation();

  return (
    <div className="app-layout">
      <nav className="sidebar">
        <h1>KodaAI</h1>
        <Link to="/" className={location.pathname === "/" ? "active" : ""}>
          Analyze
        </Link>
        <Link
          to="/pentests"
          className={location.pathname.startsWith("/pentests") || location.pathname.startsWith("/scan/") ? "active" : ""}
        >
          Pentests
        </Link>
        <Link to="/prompts" className={location.pathname === "/prompts" ? "active" : ""}>
          System Prompts
        </Link>
      </nav>
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/pentests" element={<Pentests />} />
          <Route path="/scan/:scanId" element={<Scan />} />
          <Route path="/prompts" element={<Prompts />} />
        </Routes>
      </main>
    </div>
  );
}
