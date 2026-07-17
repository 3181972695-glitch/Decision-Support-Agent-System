import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import HomePage from "./pages/HomePage";
import DebatePage from "./pages/DebatePage";
import ExpertPage from "./pages/ExpertPage";

function App() {
  return (
    <BrowserRouter>
      <nav className="nav-bar">
        <Link to="/" className="nav-bar__link">Debate</Link>
        <Link to="/expert" className="nav-bar__link">Expert</Link>
      </nav>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/debate/:debateId" element={<DebatePage />} />
        <Route path="/expert" element={<ExpertPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
