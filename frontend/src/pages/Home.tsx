import { ArrowRight, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { Card, PageHeader } from "../components/ui";
import { useAuth } from "../lib/auth";
import { MODULES } from "../lib/modules";
import Impact from "./Impact";

const NEXT: Record<string, string> = {
  faculty: "Upload a syllabus in CometGap to see how it compares with live industry demand, then turn the gaps into an updated syllabus with CometForge.",
  student: "Set your career goal in CometPath to get a semester-by-semester plan, then upload your resume in CometMatch to see your best-fit jobs.",
  employer: "Post a job in CometMatch. CometIQ extracts the skills and ranks matching students with a transparent fit breakdown.",
  admin: "Invite faculty, students and employers with your join code, then follow adoption and outcomes on this dashboard.",
};

export default function Home() {
  const { user } = useAuth();
  if (!user) return null;
  const mods = MODULES.filter((m) => m.roles.includes(user.role));
  return (
    <div>
      <PageHeader title={`Welcome, ${user.full_name.split(" ")[0]}`} subtitle="From industry demand to student success." />
      <div className="mb-6 flex items-start gap-3 rounded-xl border border-flame-200 bg-flame-50 p-4 text-sm text-flame-900">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-flame-500" /><div><span className="font-semibold">Suggested next step: </span>{NEXT[user.role]}</div>
      </div>
      <div className="mb-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {mods.map((m) => (
          <Link key={m.to} to={m.to} className="card group p-5 transition hover:-translate-y-0.5 hover:shadow-md">
            <div className={`flex h-11 w-11 items-center justify-center rounded-full text-white ${m.accent}`}>{m.icon}</div>
            <div className="mt-3 text-lg font-bold text-comet-900">{m.label}</div>
            <div className="text-sm text-slate-500">{m.tagline}</div>
            <div className="mt-3 flex items-center gap-1 text-sm font-semibold text-flame-600">Open <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" /></div>
          </Link>
        ))}
      </div>
      <Card title="Platform impact"><Impact /></Card>
    </div>
  );
}
