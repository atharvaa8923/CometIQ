import { Link } from "react-router-dom";
import { Logo } from "../components/Logo";

function Shell({ title, version, children }: { title: string; version: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-white">
      <header className="border-b border-slate-200"><div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-4"><Link to="/"><Logo size="sm" /></Link>
        <nav className="flex gap-4 text-sm"><Link to="/privacy" className="text-comet-700 hover:underline">Privacy</Link><Link to="/terms" className="text-comet-700 hover:underline">Terms</Link><Link to="/accessibility" className="text-comet-700 hover:underline">Accessibility</Link></nav></div></header>
      <main className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="text-3xl font-bold text-comet-900">{title}</h1>
        <p className="mt-1 text-sm text-slate-500">Version {version}</p>
        <div className="prose-sm mt-6 space-y-4 text-[15px] leading-relaxed text-slate-700 [&_h2]:mt-8 [&_h2]:text-lg [&_h2]:font-bold [&_h2]:text-comet-900 [&_li]:ml-5 [&_li]:list-disc">{children}</div>
      </main>
    </div>
  );
}

export function Privacy() {
  return (
    <Shell title="Privacy Notice" version="2026-11">
      <p>CometIQ helps your institution align courses with industry needs, plan degrees and connect students with employers. This notice explains what we collect, why, who can see it, and the choices you have.</p>
      <h2>What we collect</h2>
      <ul>
        <li><b>Account:</b> name, email, role and institution; a hashed password (never the password itself).</li>
        <li><b>Students:</b> program, concentration, career goal, courses you record or plan, your resume (if you upload one), courses/certifications/projects you submit with any proof files, degree plans and advisor feedback, and job applications.</li>
        <li><b>Faculty:</b> syllabi you upload or import, gap analyses and syllabus drafts.</li>
        <li><b>Employers:</b> company name, job postings and candidate status changes.</li>
        <li><b>Activity:</b> an audit log of important actions (sign-ins, approvals, exports) for security.</li>
      </ul>
      <h2>Why we use it</h2>
      <ul>
        <li>To provide the four modules: curriculum gap analysis, syllabus generation, degree planning and talent matching.</li>
        <li>To send the notifications you choose (you can turn email off in Account settings).</li>
        <li>When your institution enables it, text you provide (syllabi, resumes, course descriptions) may be processed by an AI service (Anthropic's Claude) to extract skills and write suggestions. It is not used to train AI models under the provider's commercial terms.</li>
      </ul>
      <h2>Who can see your information</h2>
      <ul>
        <li><b>Advisors and administrators</b> at your institution can see student records needed to advise and verify submissions.</li>
        <li><b>Employers</b> see only students who turn on “Let partner employers find me,” and then only name, program, headline, skills and skill evidence — never full resume text, grades or plans. Turn this off at any time in CometMatch.</li>
        <li><b>Faculty</b> see course and market data; on the knowledge-graph map, students appear as counts, not names.</li>
        <li>We do not sell personal information.</li>
      </ul>
      <h2>Education records (FERPA)</h2>
      <p>Student information in CometIQ may be part of your education records. Your institution controls these records and sharing follows its FERPA policies and directory-information rules. Employer visibility is opt-in.</p>
      <h2>Your choices and rights</h2>
      <ul>
        <li><b>Download my data:</b> Account settings → Download my data gives you a copy of everything stored about you.</li>
        <li><b>Delete my account:</b> Account settings → Delete my account permanently removes your account and personal data. Activity-log entries are kept without your identity.</li>
        <li>Correct your information in the app, or ask your institution's administrator.</li>
      </ul>
      <h2>Security and retention</h2>
      <p>Data is encrypted in transit (HTTPS) and stored in a managed database with backups. Access is limited by role. Job postings from public sources are closed after 60 days. Your data is kept while your account is active and deleted when you delete your account or your institution asks us to.</p>
      <h2>Contact</h2>
      <p>Questions or requests: contact your institution's CometIQ administrator.</p>
    </Shell>
  );
}

export function Terms() {
  return (
    <Shell title="Terms of Use" version="2026-11">
      <p>By using CometIQ you agree to these terms and to your institution's acceptable-use policies.</p>
      <h2>Using CometIQ</h2>
      <ul>
        <li>Use your own account and keep your password private. Tell your administrator about suspected misuse.</li>
        <li>Submit only information that is accurate and that you are allowed to share. Do not upload certificates or documents that are not yours.</li>
        <li>Employers may use student information only to recruit for the roles they post, and must not copy or resell it.</li>
      </ul>
      <h2>Advice, not decisions</h2>
      <p>Degree plans, course recommendations, gap analyses, AI suggestions and match scores are guidance. Official degree requirements are set by the university catalog and your academic advisor; hiring decisions are made by employers.</p>
      <h2>Content</h2>
      <p>You keep ownership of what you upload. You let CometIQ store and process it to provide the service to you and your institution.</p>
      <h2>Changes</h2>
      <p>We may update these terms; you'll be asked to accept a new version before continuing.</p>
    </Shell>
  );
}

export function AccessibilityStatement() {
  return (
    <Shell title="Accessibility" version="2026-11">
      <p>CometIQ aims to meet the Web Content Accessibility Guidelines (WCAG) 2.1 Level AA, as expected of Texas public universities.</p>
      <ul>
        <li>Every page is tested with the axe accessibility engine for each user role.</li>
        <li>All features work with a keyboard; dialogs close with Escape; charts have text alternatives and status is never shown by color alone.</li>
        <li>Text meets contrast requirements and the layout adapts to zoom and small screens.</li>
      </ul>
      <p>If something is hard to use, contact your institution's CometIQ administrator and we will provide the information in another way and fix the issue.</p>
    </Shell>
  );
}
