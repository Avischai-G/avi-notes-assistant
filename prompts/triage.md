---
description: Opens the case - proposes the candidate causes of death, including the ones the rules missed
---

# Triage

## Your job

Propose 2-3 candidate causes of death, most likely first.

The rule-based guess matches on the stop-reason string, so it is fooled
whenever the recorded reason describes the symptom rather than the cause. A run
that says it is "waiting for the user" may really have died because something
upstream forced it to ask. Treat the guess as one hypothesis among others.

If the recorded stop reason looks like the proximate symptom of something
earlier in the run, say so and propose the earlier cause as well.
