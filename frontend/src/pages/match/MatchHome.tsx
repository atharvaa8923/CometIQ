import { useAuth } from "../../lib/auth";
import EmployerMatch from "./EmployerMatch";
import StudentMatch from "./StudentMatch";

export default function MatchHome() {
  const { user } = useAuth();
  return user?.role === "student" ? <StudentMatch /> : <EmployerMatch />;
}
