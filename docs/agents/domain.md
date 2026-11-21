# Domain documentation

This repository uses a single context: `GLOSSARY.md` at the root and architectural decision records under `docs/adr/`.

## Before exploring or designing

- Read `GLOSSARY.md` for the domain language.
- Read any ADRs under `docs/adr/` that concern the work.
- If either is absent, proceed without creating a placeholder. The domain-modeling skill creates these documents when terms or decisions are resolved.

## Use the agreed language

Use glossary terms in requirements, issues, plans, code discussions, and test descriptions. When a term is missing or conflicts with the intended meaning, resolve it through domain-modeling.

Keep `GLOSSARY.md` a glossary. Product requirements belong in product documents, and implementation decisions belong in the relevant spec or ADR.

## Record decisions when warranted

Create an ADR only when a choice is costly to reverse, would be surprising without context, and reflects a real trade-off. Use the domain-modeling skill's ADR format.

Surface a conflict with an existing ADR explicitly before proposing a different direction. Name the affected ADR and explain the trade-off.

## Product documents

Product requirements may live under `docs/`. Use them as the source for a later implementation spec, linking the spec back to the product document.
