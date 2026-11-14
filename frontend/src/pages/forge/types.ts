export interface Outcome { id: string; text: string; bloom: string; skills: string[]; is_new: boolean }
export interface Module { week: number; title: string; topics: string[]; skills: string[]; activities: string[]; outcomes: string[]; is_new: boolean }
export interface Assessment { name: string; type: string; weight: number; description: string; outcomes: string[]; skills: string[] }
export interface Content {
  course_code: string; course_title: string; description: string; framework: string;
  learning_outcomes: Outcome[]; modules: Module[]; assessments: Assessment[];
  project: { title: string; description: string; deliverables: string[]; skills: string[] };
  accreditation: { standard: string; outcomes: string[]; evidence: string }[];
  program_goals: { goal: string; outcomes: string[] }[];
  tools: string[]; gaps_addressed: string[]; change_log: string[];
}
export interface Draft {
  id: string; title: string; version: number; status: "draft" | "approved"; engine: string; syllabus_id: string | null; analysis_id: string | null;
  created_at: string; new_modules: number; scores: { before: number | null; after: number | null; target: string | null };
  content: Content; versions: { id: string; version: number; status: string; created_at: string }[];
}
