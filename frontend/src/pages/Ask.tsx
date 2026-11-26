import { MessageCircleQuestion, Send } from "lucide-react";
import { Fragment, useEffect, useRef, useState, type ReactElement } from "react";
import { Link } from "react-router-dom";
import { Card, PageHeader } from "../components/ui";
import { api } from "../lib/api";

interface Answer { question: string; answer: string; citations: { n: number; title: string; link: string; type: string }[]; intent: string; engine: string; steps: string[]; examples: string[] }
const EXAMPLES = ["Why did BUAN 6356 drop?", "Which accepted changes were never implemented?", "Where does the program teach SQL twice?",
  "Draft the AACSB summary for SQL.", "Which priority gaps have no decision yet?", "Which proposals are waiting for review?"];

/** Minimal, safe markdown: headings, bullet lists, **bold**, *italic* and [n] citation links. No HTML is injected. */
function Inline({ text, cites }: { text: string; cites: Map<number, string> }) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|\[\d+\])/g);
  return <>{parts.map((p, i) => {
    if (/^\*\*[^*]+\*\*$/.test(p)) return <b key={i}>{p.slice(2, -2)}</b>;
    if (/^\*[^*]+\*$/.test(p)) return <i key={i}>{p.slice(1, -1)}</i>;
    const m = p.match(/^\[(\d+)\]$/);
    if (m && cites.has(Number(m[1]))) return <Link key={i} to={cites.get(Number(m[1]))!} className="mx-0.5 rounded bg-comet-100 px-1 text-[11px] font-semibold text-comet-800 no-underline hover:bg-comet-200" aria-label={`Source ${m[1]}`}>{m[1]}</Link>;
    return <Fragment key={i}>{p}</Fragment>;
  })}</>;
}

function Markdown({ text, cites }: { text: string; cites: Map<number, string> }) {
  const blocks: ReactElement[] = [];
  let list: string[] = [];
  const flush = () => { if (list.length) { blocks.push(<ul key={blocks.length} className="my-2 list-disc space-y-1 pl-5">{list.map((l, i) => <li key={i}><Inline text={l} cites={cites} /></li>)}</ul>); list = []; } };
  text.split("\n").forEach((line) => {
    if (/^\s*[-*] /.test(line)) { list.push(line.replace(/^\s*[-*] /, "")); return; }
    flush();
    if (line.startsWith("## ")) blocks.push(<h3 key={blocks.length} className="mt-1 text-base font-bold text-comet-900"><Inline text={line.slice(3)} cites={cites} /></h3>);
    else if (line.trim()) blocks.push(<p key={blocks.length} className="my-1.5"><Inline text={line} cites={cites} /></p>);
  });
  flush();
  return <div className="text-sm leading-relaxed text-slate-800">{blocks}</div>;
}

export default function Ask() {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<(Answer | { question: string; pending: true } | { question: string; error: string })[]>([]);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [items]);
  const ask = async (question: string) => {
    if (question.trim().length < 3) return;
    setQ("");
    setItems((x) => [...x, { question, pending: true }]);
    try {
      const a = await api.post<Answer>("/ask", { question });
      setItems((x) => [...x.slice(0, -1), a]);
    } catch (e) { setItems((x) => [...x.slice(0, -1), { question, error: (e as Error).message }]); }
  };
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <PageHeader icon={<MessageCircleQuestion className="h-5 w-5" />} title="Ask CometIQ" subtitle="Answers come only from CometIQ's stored records, and every claim links to its source" />
      {!items.length && <Card>
        <p className="text-sm text-slate-600">Try a question:</p>
        <div className="mt-2 flex flex-wrap gap-2">{EXAMPLES.map((e) => <button key={e} className="btn-ghost btn-sm" onClick={() => ask(e)}>{e}</button>)}</div>
      </Card>}
      <div className="space-y-4" aria-live="polite">
        {items.map((it, i) => (
          <div key={i} className="space-y-2">
            <div className="ml-auto w-fit max-w-[80%] rounded-2xl rounded-br-sm bg-comet-700 px-4 py-2 text-sm text-white">{it.question}</div>
            {"pending" in it ? <div className="w-fit rounded-2xl bg-white px-4 py-2 text-sm text-slate-500 shadow-sm">Looking through the records…</div>
              : "error" in it ? <div role="alert" className="w-fit rounded-2xl bg-red-50 px-4 py-2 text-sm text-red-800">{it.error}</div>
              : <Card>
                  <Markdown text={it.answer} cites={new Map(it.citations.map((c) => [c.n, c.link]))} />
                  {it.citations.length > 0 && <div className="mt-3 border-t border-slate-100 pt-2">
                    <div className="label">Sources</div>
                    <ol className="space-y-0.5 text-xs">{it.citations.map((c) => <li key={c.n}><span className="mr-1 font-semibold text-comet-800">[{c.n}]</span><Link className="text-comet-700 hover:underline" to={c.link}>{c.title}</Link></li>)}</ol>
                  </div>}
                  <details className="mt-2 text-xs text-slate-500"><summary className="cursor-pointer">How this was answered ({it.engine === "claude" ? "Claude" : "built-in engine"})</summary>
                    <ol className="mt-1 list-decimal pl-5">{it.steps.map((s, k) => <li key={k}>{s}</li>)}</ol></details>
                </Card>}
          </div>))}
        <div ref={end} />
      </div>
      <form className="sticky bottom-4 flex gap-2 rounded-xl border border-slate-200 bg-white p-2 shadow-lg" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
        <label htmlFor="ask-q" className="sr-only">Your question</label>
        <input id="ask-q" className="input border-0 focus:ring-0" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about courses, gaps, decisions, proposals or skills…" maxLength={500} />
        <button className="btn-primary" disabled={q.trim().length < 3}><Send className="h-4 w-4" />Ask</button>
      </form>
    </div>
  );
}
