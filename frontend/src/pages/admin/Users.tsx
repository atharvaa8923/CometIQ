import { UserPlus } from "lucide-react";
import { useState } from "react";
import { Badge, Card, ErrorBox, Field, Modal, PageHeader, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth, type Role } from "../../lib/auth";
import { useApi } from "../../lib/hooks";
import { ROLE_LABEL } from "../../lib/modules";
import { useToast } from "../../lib/toast";

interface Row { id: string; email: string; full_name: string; role: Role; company: string | null; is_active: boolean; created_at: string }
const ROLE_COLOR: Record<Role, string> = { admin: "purple", faculty: "green", student: "blue", employer: "orange" };

export default function Users() {
  const { user } = useAuth();
  const toast = useToast();
  const { data, loading, reload } = useApi<Row[]>("/admin/users");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ full_name: "", email: "", role: "faculty", password: "", company: "" });
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState<"" | Role>("");

  const patch = async (id: string, body: Record<string, unknown>) => {
    try { await api.patch(`/admin/users/${id}`, body); reload(); toast("User updated"); } catch (e) { toast((e as Error).message, "error"); }
  };
  const create = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try { await api.post("/admin/users", { ...f, company: f.company || null }); setOpen(false); reload(); toast("User created"); }
    catch (x) { setErr((x as Error).message); }
  };
  const rows = (data ?? []).filter((r) => !filter || r.role === filter);

  return (
    <div>
      <PageHeader title="Users" subtitle="Manage who can access your institution's CometIQ workspace"
        actions={<button className="btn-primary" onClick={() => setOpen(true)}><UserPlus className="h-4 w-4" />Add user</button>} />
      <Card padded={false} title={
        <select className="input w-44 py-1" value={filter} onChange={(e) => setFilter(e.target.value as Role | "")} aria-label="Filter by role">
          <option value="">All roles</option>{(Object.keys(ROLE_LABEL) as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
        </select>}>
        {loading ? <Spinner /> : (
          <table className="table-base"><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th /></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id}>
                <td className="font-medium">{r.full_name}{r.company && <div className="text-xs text-slate-500">{r.company}</div>}</td>
                <td className="text-slate-600">{r.email}</td>
                <td>
                  <select className="input w-32 py-1 text-xs" value={r.role} disabled={r.id === user?.id} onChange={(e) => patch(r.id, { role: e.target.value })} aria-label={`Role for ${r.full_name}`}>
                    {(Object.keys(ROLE_LABEL) as Role[]).map((x) => <option key={x} value={x}>{ROLE_LABEL[x]}</option>)}
                  </select>
                </td>
                <td><Badge color={r.is_active ? ROLE_COLOR[r.role] : "red"}>{r.is_active ? "Active" : "Disabled"}</Badge></td>
                <td className="text-right">{r.id !== user?.id && <button className="btn-ghost btn-sm" onClick={() => patch(r.id, { is_active: !r.is_active })}>{r.is_active ? "Disable" : "Enable"}</button>}</td>
              </tr>))}
            </tbody></table>
        )}
      </Card>
      <Modal open={open} onClose={() => setOpen(false)} title="Add user">
        <form onSubmit={create} className="space-y-3">
          <ErrorBox error={err} />
          <Field label="Full name"><input className="input" required value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field>
          <Field label="Email"><input className="input" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
          <Field label="Role"><select className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
            {(Object.keys(ROLE_LABEL) as Role[]).map((x) => <option key={x} value={x}>{ROLE_LABEL[x]}</option>)}</select></Field>
          {f.role === "employer" && <Field label="Company"><input className="input" value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} /></Field>}
          <Field label="Temporary password" hint="At least 8 characters"><input className="input" minLength={8} required value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
          <button className="btn-primary w-full">Create user</button>
        </form>
      </Modal>
    </div>
  );
}
