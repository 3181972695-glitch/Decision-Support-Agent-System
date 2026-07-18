import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import HomePage from "./pages/HomePage";
import DebatePage from "./pages/DebatePage";
import ExpertPage from "./pages/ExpertPage";
import ExpertDebatePage from "./pages/ExpertDebatePage";

function App() {
  return (
    <BrowserRouter>
      <nav className="nav-bar">
        <Link to="/" className="nav-bar__link">Debate</Link>
        <Link to="/expert" className="nav-bar__link">Expert</Link>
        <Link to="/expert/debate" className="nav-bar__link">Expert Debate</Link>
      </nav>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/debate/:debateId" element={<DebatePage />} />
        <Route path="/expert" element={<ExpertPage />} />
        <Route path="/expert/debate" element={<ExpertDebatePage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
