# Drafting C: the rule a benchmark earned

For whoever writes a drafter's brief in this repository (S10 copies this file from psxdecomp's PS1 profile).

- **Fields by name.** Where a header has the struct, read and write its members as `p->field`: no byte-offset
  arithmetic, no offset macro, no struct pointer retyped so it can be indexed. If the struct or the field is missing,
  say which one; the type goes into the header first.

What it measured (psxdecomp's C corpus, 2026-10-11: 24 small functions, three models, 72 paired drafts per arm, one
compiler): with this text in the brief, drafts that match the bytes and contain no such access went from 39 to 54 of
72 (16 pairs gained, 1 lost), the byte-match rate did not fall (59 to 61 of 72) and the cost per draft rose 5%. On
nine held-out functions of one real game (mmx6, 2026-10-11, exploratory, 27 pairs) matching drafts with no offset
access went from 9 to 17 and the match rate held (19 to 18), but a draft cost 67% more: the drafter reads the type
header.

Tried in the same text and not adopted, because the baseline drafts gave them nothing to prevent (0 to 2 events in 72
drafts): no bare address, no register pin, no `goto`, no type defined in a draft, no file touched but the draft.
Showing a text check's findings (pin, `goto`, offset cast) at each probe instead of the text changed nothing
measurable (8 pairs gained, 5 lost): of the 22 drafts with an offset access in its own arm it saw 4, the rest being
spelled as pointer casts or retyped parameters. A rule here needs a number of this kind before it is added.
