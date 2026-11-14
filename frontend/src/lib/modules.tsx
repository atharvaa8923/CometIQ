import { BookOpen, BriefcaseBusiness, LayoutDashboard, Library, Route, ScanSearch, Settings, Users } from "lucide-react";
import type { ReactNode } from "react";
import type { Role } from "./auth";

export interface NavItem { to: string; label: string; icon: ReactNode; roles: Role[]; tagline?: string; accent?: string }

export const MODULES: NavItem[] = [
  { to: "/gap", label: "CometGap", tagline: "Curriculum–Industry Gap Analysis", icon: <ScanSearch className="h-4 w-4" />, roles: ["faculty", "admin"], accent: "bg-comet-600" },
  { to: "/forge", label: "CometForge", tagline: "AI Course & Syllabus Generation", icon: <BookOpen className="h-4 w-4" />, roles: ["faculty", "admin"], accent: "bg-flame-500" },
  { to: "/path", label: "CometPath", tagline: "AI Degree & Career Planner", icon: <Route className="h-4 w-4" />, roles: ["student", "admin"], accent: "bg-comet-500" },
  { to: "/match", label: "CometMatch", tagline: "Student–Employer Talent Matching", icon: <BriefcaseBusiness className="h-4 w-4" />, roles: ["student", "employer", "admin"], accent: "bg-navy-500" },
];

export const NAV: NavItem[] = [
  { to: "/app", label: "Dashboard", icon: <LayoutDashboard className="h-4 w-4" />, roles: ["admin", "faculty", "student", "employer"] },
  ...MODULES,
  { to: "/catalog", label: "Knowledge Graph", icon: <Library className="h-4 w-4" />, roles: ["admin", "faculty", "student"] },
  { to: "/admin/users", label: "Users", icon: <Users className="h-4 w-4" />, roles: ["admin"] },
  { to: "/admin/org", label: "Organization", icon: <Settings className="h-4 w-4" />, roles: ["admin"] },
];

export const ROLE_LABEL: Record<Role, string> = { admin: "Administrator", faculty: "Faculty", student: "Student", employer: "Employer" };
