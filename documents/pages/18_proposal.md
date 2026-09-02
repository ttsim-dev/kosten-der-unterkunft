# How to fix this in GETTSIM?

Three options:

1. **Be developer-friendly** — users provide the **Bruttokaltmiete ceiling** as an
   input. Con: Many people need to make uninformed decisions. Input depends on household
   size.

1. **Be paternalistic** - GETTSIM provides an empirical default **or** applies the
   Wohngeld proxy rule. Con: Which default? Empirical average weighted by number of
   Bedarfsgemeinschaften (likely to move)? WoGG rule (which we know is, on average, not
   accurate)?

1. **Be user-friendly** - Provide a mapping from Kreis/Gemeinde to the caps. Con: Not
   maintainable with the resources we have.

Most likely: Optional companion pacakge with the mapping I collected, combined with the
paternalistic approach and a user-warning if default is being used.
