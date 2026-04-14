import { ReactNode } from "react";

type PanelProps = {
  title: string;
  eyebrow?: string;
  actions?: ReactNode;
  children: ReactNode;
};

export function Panel({ title, eyebrow, actions, children }: PanelProps) {
  return (
    <section className="rounded-[28px] border-2 border-border bg-surface p-5 shadow-[6px_6px_0px_0px] shadow-border">
      <div className="mb-5 flex flex-col gap-3 border-b-2 border-primary pb-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          {eyebrow ? <p className="font-mono text-xs uppercase tracking-[0.35em] text-muted">{eyebrow}</p> : null}
          <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}
