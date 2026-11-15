import { NavLink, Route, Routes } from "react-router-dom";
import Applications from "./pages/Applications";
import Coach from "./pages/Coach";
import Companies from "./pages/Companies";
import Jobs from "./pages/Jobs";
import Overview from "./pages/Overview";
import Prep from "./pages/Prep";
import Profile from "./pages/Profile";
import Settings from "./pages/Settings";

const LIVE = [
  { to: "/", label: "Overview" },
  { to: "/jobs", label: "Jobs" },
  { to: "/companies", label: "Companies" },
  { to: "/applications", label: "Applications" },
  { to: "/prep", label: "Interview prep" },
  { to: "/coach", label: "Coach" },
  { to: "/profile", label: "Profile facts" },
  { to: "/settings", label: "Settings" },
];

// Shown greyed out so the full shape of the product is visible from day one.
const UPCOMING = [
  { label: "Compare", phase: "2b" },
  { label: "Resumes", phase: 3 },
  { label: "Reports", phase: 7 },
];

export default function App() {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">JobPilot</div>
        <nav>
          {LIVE.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"} className="nav-link">
              {item.label}
            </NavLink>
          ))}
          <div className="nav-section">Coming next</div>
          {UPCOMING.map((item) => (
            <span key={item.label} className="nav-link disabled" title={`Arrives in Phase ${item.phase}`}>
              {item.label}
              <span className="phase">P{item.phase}</span>
            </span>
          ))}
        </nav>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/companies" element={<Companies />} />
          <Route path="/applications" element={<Applications />} />
          <Route path="/prep" element={<Prep />} />
          <Route path="/coach" element={<Coach />} />
          <Route path="/coach/:id" element={<Coach />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
