import { Stat } from "../components/ui";
import { useApi } from "../lib/hooks";

interface Org { members: Record<string, number>; courses: number; programs: number; syllabi: number; analyses: number; drafts: number; jobs: number; applications: number }

/** Org-wide numbers; richer outcome metrics arrive in Step 6. */
export default function Impact() {
  const { data } = useApi<Org>("/dashboard/summary");
  if (!data) return <div className="text-sm text-slate-500">Impact metrics appear as your institution uses CometIQ.</div>;
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <Stat label="Courses in graph" value={data.courses} hint={`${data.programs} programs`} />
      <Stat label="Market job postings" value={data.jobs} tone="navy" />
      <Stat label="Syllabi analyzed" value={data.analyses} hint={`${data.syllabi} uploaded`} tone="flame" />
      <Stat label="Students" value={data.members.student ?? 0} hint={`${data.applications} applications`} tone="slate" />
    </div>
  );
}
