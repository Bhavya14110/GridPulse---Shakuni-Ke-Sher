import Link from "next/link";

export default function NotFound() {
  return (
    <div className="glass mt-8 flex flex-col items-start gap-3 p-8">
      <h1 className="text-xl font-semibold text-white">Nothing here</h1>
      <p className="text-sm text-slate-400">
        That page doesn&apos;t exist. The portfolio view has everything.
      </p>
      <Link
        href="/"
        className="rounded-lg border border-white/15 bg-white/5 px-3.5 py-2 text-sm text-slate-200 transition-colors hover:bg-white/10"
      >
        Back to portfolio
      </Link>
    </div>
  );
}
