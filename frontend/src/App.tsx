import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import { useAuth, type Role } from "./lib/auth";
import Org from "./pages/admin/Org";
import Users from "./pages/admin/Users";
import Catalog from "./pages/Catalog";
import Home from "./pages/Home";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Analysis from "./pages/gap/Analysis";
import ForgeEditor from "./pages/forge/ForgeEditor";
import ForgeHome from "./pages/forge/ForgeHome";
import ForgeNew from "./pages/forge/ForgeNew";
import PathHome from "./pages/path/PathHome";
import MatchHome from "./pages/match/MatchHome";
import Verifications from "./pages/Verifications";
import Advising from "./pages/Advising";
import GapHome from "./pages/gap/GapHome";
import NewSyllabus from "./pages/gap/NewSyllabus";

function Guard({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <Spinner />;
  if (!user) return <Navigate to="/login" replace />;
  if (roles && user.role !== "admin" && !roles.includes(user.role)) return <Navigate to="/app" replace />;
  return <>{children}</>;
}

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner />;
  return (
    <Routes>
      <Route path="/" element={user ? <Navigate to="/app" replace /> : <Landing />} />
      <Route path="/login" element={user ? <Navigate to="/app" replace /> : <Login />} />
      <Route path="/register" element={user ? <Navigate to="/app" replace /> : <Register />} />
      <Route element={<Guard><Layout /></Guard>}>
        <Route path="/app" element={<Home />} />
        <Route path="/catalog" element={<Catalog />} />
        <Route path="/gap" element={<Guard roles={["faculty"]}><GapHome /></Guard>} />
        <Route path="/gap/new" element={<Guard roles={["faculty"]}><NewSyllabus /></Guard>} />
        <Route path="/gap/analysis/:id" element={<Guard roles={["faculty"]}><Analysis /></Guard>} />
        <Route path="/forge" element={<Guard roles={["faculty"]}><ForgeHome /></Guard>} />
        <Route path="/forge/new" element={<Guard roles={["faculty"]}><ForgeNew /></Guard>} />
        <Route path="/forge/:id" element={<Guard roles={["faculty"]}><ForgeEditor /></Guard>} />
        <Route path="/path" element={<Guard roles={["student"]}><PathHome /></Guard>} />
        <Route path="/match" element={<Guard roles={["student", "employer"]}><MatchHome /></Guard>} />
        <Route path="/advising" element={<Guard roles={["advisor"]}><Advising /></Guard>} />
        <Route path="/verify" element={<Guard roles={["advisor"]}><Verifications /></Guard>} />
        <Route path="/admin/users" element={<Guard roles={["admin"]}><Users /></Guard>} />
        <Route path="/admin/org" element={<Guard roles={["admin"]}><Org /></Guard>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
