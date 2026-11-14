import { Copy } from "lucide-react";
import { Card, PageHeader, Spinner, Stat } from "../../components/ui";
import { useApi } from "../../lib/hooks";
import { useToast } from "../../lib/toast";

interface Org { name: string; slug: string; join_code: string; plan: string; members: Record<string, number> }
interface Log { id: number; action: string; user: string | null; detail: Record<string, unknown> | null; at: string }

export default function Org() {
  const toast = useToast();
  const { data } = useApi<Org>("/admin/org");
  const logs = useApi<Log[]>("/admin/audit");
  if (!data) return <Spinner />;
  return (
    <div className="space-y-6">
      <PageHeader title={data.name} subtitle={`Workspace /${data.slug} · ${data.plan.toUpperCase()} plan`} />
      <div className="grid gap-4 md:grid-cols-4">
        {Object.entries(data.members).map(([r, n]) => <Stat key={r} label={`${r}s`} value={n} />)}
      </div>
      <Card title="Invite people">
        <p className="mb-3 text-sm text-slate-600">Share this join code. People choose their role (student, faculty or employer) when they register.</p>
        <div className="flex items-center gap-3">
          <code className="rounded-lg bg-comet-50 px-4 py-2 text-lg font-bold tracking-widest text-comet-800">{data.join_code}</code>
          <button className="btn-ghost btn-sm" onClick={() => { navigator.clipboard.writeText(data.join_code); toast("Join code copied"); }}><Copy className="h-4 w-4" />Copy</button>
        </div>
      </Card>
      <Card title="Audit log" padded={false}>
        <div className="max-h-96 overflow-y-auto">
          <table className="table-base"><thead><tr><th>When</th><th>User</th><th>Action</th><th>Detail</th></tr></thead>
            <tbody>{logs.data?.map((l) => (
              <tr key={l.id}><td className="whitespace-nowrap text-slate-500">{new Date(l.at).toLocaleString()}</td><td>{l.user ?? "—"}</td>
                <td className="font-medium">{l.action}</td><td className="text-xs text-slate-500">{l.detail ? JSON.stringify(l.detail) : ""}</td></tr>))}
            </tbody></table>
        </div>
      </Card>
    </div>
  );
}
