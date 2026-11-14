import { Hammer } from "lucide-react";
import { Empty, PageHeader } from "../components/ui";

export default function Soon({ title, step }: { title: string; step: number }) {
  return (<div><PageHeader title={title} /><Empty icon={<Hammer className="h-8 w-8" />} title={`${title} is being built (Step ${step})`}>This module is next on the build plan.</Empty></div>);
}
