import type { PropsWithChildren, ReactNode } from "react";

export function SectionCard({
  eyebrow,
  title,
  aside,
  children,
}: PropsWithChildren<{ eyebrow: string; title: string; aside?: ReactNode }>) {
  return (
    <section className="section-card">
      <div className="section-head">
        <div>
          <p className="section-eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
        </div>
        {aside ? <div className="section-aside">{aside}</div> : null}
      </div>
      {children}
    </section>
  );
}

