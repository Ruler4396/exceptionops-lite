import type { RuleHit } from "../lib/types";

export function RuleChip({ hit }: { hit: RuleHit }) {
  return (
    <article className={`rule-chip severity-${hit.severity}`}>
      <div className="rule-chip-head">
        <strong>{hit.rule_code}</strong>
        <span>{hit.severity}</span>
      </div>
      <p>{hit.message}</p>
      <small>{hit.evidence_refs.join(" | ")}</small>
    </article>
  );
}

