import type { ReactNode } from "react";
import { ArrowRight, BarChart3, BookOpen, BriefcaseBusiness, Building2, CheckCircle2, Factory, GraduationCap, Handshake, Route, ScanSearch, Target, Users } from "lucide-react";
import { Link } from "react-router-dom";
import { Logo } from "../components/Logo";
import { MODULES } from "../lib/modules";

const FEATURES: Record<string, string[]> = {
  "/gap": ["Compare industry skills vs. course content", "Identify gaps & emerging technologies", "Actionable insights for faculty"],
  "/forge": ["Generate course structure & modules", "Create learning outcomes, assignments & projects", "Align with accreditation & program goals"],
  "/path": ["Recommend courses & skills", "Plan semester-by-semester pathways", "Link learning to career goals"],
  "/match": ["AI-powered skill matching", "Transparent fit analysis", "Connect students with real opportunities"],
};
const ICONS: Record<string, ReactNode> = {
  "/gap": <ScanSearch className="h-8 w-8" />, "/forge": <BookOpen className="h-8 w-8" />,
  "/path": <Route className="h-8 w-8" />, "/match": <Users className="h-8 w-8" />,
};

export default function Landing() {
  return (
    <div className="min-h-screen bg-white">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <Logo />
        <nav className="flex items-center gap-3">
          <span className="hidden text-xs font-bold tracking-[0.2em] text-comet-800 md:block">LEARN / INNOVATE / IMPACT</span>
          <Link to="/login" className="btn-ghost">Sign in</Link>
          <Link to="/register" className="btn-accent">Get started</Link>
        </nav>
      </header>

      <section className="bg-gradient-to-br from-comet-900 via-comet-800 to-comet-700 text-white">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-16 md:grid-cols-2 md:py-24">
          <div>
            <Logo light size="lg" />
            <h1 className="mt-6 text-3xl font-bold leading-tight md:text-4xl">AI Intelligence for Education, Skills &amp; Talent</h1>
            <p className="mt-3 text-lg font-semibold italic text-flame-300">From Industry Demand to Student Success.</p>
            <p className="mt-4 max-w-lg text-comet-100">CometIQ connects industry needs, university curriculum, student goals and employer opportunities through four intelligent modules — all powered by a shared knowledge graph.</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/register" className="btn-accent px-6 py-3 text-base">Start free <ArrowRight className="h-4 w-4" /></Link>
              <Link to="/login" className="btn border border-white/30 px-6 py-3 text-base text-white hover:bg-white/10">Try the demo</Link>
            </div>
          </div>
          <div className="flex flex-col justify-center gap-2 text-2xl font-semibold md:items-end md:text-3xl">
            <span>Right Skills.</span><span>Right Courses.</span><span>Right Students.</span>
            <span className="text-flame-400">Brighter Futures.</span>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-16">
        <div className="grid items-center gap-10 md:grid-cols-2">
          <div>
            <h2 className="text-2xl font-bold text-comet-900 md:text-3xl">The Complete AI-Powered Ecosystem for Higher Education and Workforce Alignment</h2>
          </div>
          <div>
            <div className="flex items-center justify-between gap-2">
              {[
                { i: <Factory />, t: "Industry", s: "Job Demand & Trends", c: "bg-comet-800" },
                { i: <BookOpen />, t: "Curriculum", s: "Relevant & Future-Ready", c: "bg-flame-500" },
                { i: <GraduationCap />, t: "Students", s: "Personalized Pathways", c: "bg-comet-500" },
                { i: <BriefcaseBusiness />, t: "Employers", s: "Skilled Talent", c: "bg-navy-500" },
              ].map((x, k, a) => (
                <div key={x.t} className="flex items-center gap-2">
                  <div className="text-center">
                    <div className={`mx-auto flex h-14 w-14 items-center justify-center rounded-full text-white ${x.c}`}>{x.i}</div>
                    <div className="mt-2 text-sm font-bold text-comet-900">{x.t}</div>
                    <div className="text-[11px] text-slate-500">{x.s}</div>
                  </div>
                  {k < a.length - 1 && <ArrowRight className="h-4 w-4 shrink-0 text-slate-500" />}
                </div>
              ))}
            </div>
            <p className="mt-4 text-center text-sm font-semibold text-comet-700">A continuous feedback loop for a stronger future.</p>
          </div>
        </div>
      </section>

      <section className="bg-slate-50 py-16">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-2xl font-bold text-comet-900">Four Powerful Modules. <br />One Intelligent Platform.</h2>
          <div className="mt-8 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {MODULES.map((m) => (
              <div key={m.to} className="card p-6">
                <div className={`flex h-16 w-16 items-center justify-center rounded-full text-white ${m.accent}`}>{ICONS[m.to]}</div>
                <h3 className="mt-4 text-xl font-bold text-comet-900">{m.label}</h3>
                <div className="text-sm font-semibold text-flame-600">{m.tagline}</div>
                <ul className="mt-4 space-y-2 text-sm text-slate-600">
                  {FEATURES[m.to].map((f) => <li key={f} className="flex gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-comet-600" />{f}</li>)}
                </ul>
              </div>
            ))}
          </div>
          <div className="card mt-8 grid gap-6 p-6 md:grid-cols-5">
            <div className="md:col-span-1">
              <div className="font-bold text-comet-900">Built on a Shared Knowledge Graph</div>
              <div className="mt-1 text-xs text-slate-500">Jobs + Skills + Courses + Programs + Students + Projects + Employers + Outcomes</div>
            </div>
            {[[<Target key="a" />, "More Relevant Curricula"], [<GraduationCap key="b" />, "Personalized Student Journeys"], [<Handshake key="c" />, "Stronger Employer Partnerships"], [<BarChart3 key="d" />, "Better Career Outcomes"]].map(([i, t]) => (
              <div key={t as string} className="flex flex-col items-center text-center text-sm font-semibold text-comet-800"><div className="mb-2 text-comet-600">{i}</div>{t}</div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-comet-900 text-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-6 px-6 py-12">
          <div>
            <h2 className="text-2xl font-bold">Empowering the next generation<br />of <span className="text-flame-400">innovators, leaders and problem solvers.</span></h2>
            <p className="mt-3 max-w-xl text-sm text-comet-100">CometIQ is more than a set of tools — it's a strategic platform that helps universities and their partners stay ahead in a rapidly changing world of work.</p>
          </div>
          <Link to="/register" className="btn-accent px-6 py-3"><Building2 className="h-4 w-4" />Set up your institution</Link>
        </div>
      </section>
      <footer className="bg-flame-600 py-3 text-center text-xs font-bold tracking-[0.3em] text-white">INNOVATION / TALENT / IMPACT</footer>
      <div className="flex justify-center gap-6 bg-white py-3 text-xs text-slate-600"><Link to="/privacy" className="hover:underline">Privacy</Link><Link to="/terms" className="hover:underline">Terms</Link><Link to="/accessibility" className="hover:underline">Accessibility</Link></div>
    </div>
  );
}
