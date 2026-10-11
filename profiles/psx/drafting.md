# Drafting C: the rule a benchmark earned

For whoever writes a drafter's brief in this repository (S10 copies this file from psxdecomp's PS1 profile).

- **Fields by name.** Read and write struct members as `p->field`: no byte-offset arithmetic, no `M2C_FIELD`, no macro
  that hides one. If a header lacks the struct or the field, say which one in your last message.

That is the line as tested, the first of eight in one block of text (psxdecomp's C corpus, 2026-10-11: 24 small
functions, three models, 72 paired drafts per arm, one compiler). With the block in the brief, drafts that match the
bytes and read no field by offset went from 39 to 54 of 72 (16 pairs gained, 1 lost), the byte-match rate did not
fall (59 to 61) and the cost per draft rose 5%. In 14 of the 16 gained pairs the baseline draft read a field by
offset, which is why the gain is credited to this line. Read it with three limits: the line was not tested alone; 11
of the 16 pairs are one model; and "reads no field by offset" is judged by a scorer corrected during the run (with a
text lint's kinds as the only judge the pairs are 8 gained, 2 lost).

On nine held-out functions of one real game (mmx6, 2026-10-11, exploratory, 27 pairs, run after the other arms)
matching drafts with no offset access went from 9 to 17 and the match rate held (19 to 18), at a cost per draft at
least 67% higher, because the drafter reads the type header. That is above the +20% psxdecomp allows a text change to
cost, so weigh it per game.

Tried in the same block and not adopted: no bare address, no register pin, no `goto`, no type defined in a draft (0
to 2 events in 72 baseline drafts, so nothing to prevent); rules on names, `!FAKE` marks and touching other files
could not be measured in that setup. A text check's findings (pin, `goto`, offset cast) printed at each probe in
place of the text changed nothing measurable (8 pairs gained, 5 lost): 11 of its 72 drafts were ever shown a finding,
and of the 22 that read a field by offset it saw 4. A rule here needs a number of this kind before it is added.
