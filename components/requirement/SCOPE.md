# Requirement — G1 Scope

Step 1 of the ClusterVise flow: **describe the machine**. The user writes the requirement in plain
words, e.g. "I need a control panel for a 75kW special purpose conveyor system, IP54, outdoor
installation in Germany, budget under €8,000."

The component:
1. reads only facts it can read for certain (fixed patterns, R-REQ-01) and shows the exact words
   each fact came from;
2. never picks between two different values for the same fact (R-REQ-02);
3. asks a question for every input the selection needs that the text does not give (R-REQ-04).
   There are no silent defaults;
4. records facts that cannot be used yet and says why (R-REQ-06);
5. runs the selection (panel assembly 12, I/O list 23) only after the user confirms (R-REQ-07).

In scope: one panel with one or more motors ("75 kW conveyor VFD; 2 x 11 kW pumps DOL", R-REQ-09). The
confirmed facts run through every built component:
- feeders (1 motor FLC, 2 DOL, 4 VFD with Power Module, Control Unit, memory card and BOP-2, 6 motor cable);
- 23 I/O list;
- 16 relays and terminals;
- 19 internal wiring;
- 3 the incomer breaker (until 8 is built);
- 15 metering, when asked.

Blocked components are listed as not selected with the document each one waits for (R-REQ-13).

Out of scope (owner, 2026-10-12):
- **Enclosure:** IP rating and indoor/outdoor are recorded, not selected.
- **Budget:** recorded; no price source is held, so no total is given.

Authority: RULE (our reading rules, signed off by the owner). The component holds no engineering
data; every value comes from the components it runs.
