# Control power (24 V DC supply) — G1 Scope

Sizes the 24 V DC supply from these loads:
- digital inputs;
- interface relay coils;
- outputs without a relay;
- the PLC / I/O modules / HMI current, which the user gives.

It applies the template's factor (1.25), then picks the smallest supply from the own database
(Omron S8VK; 1P+N or 3P input).

Not yet: PLC, I/O modules, network and UPS selection (they wait for the ET 200SP and CPU 1513
manuals), and the supply's input MCB (the database has no input current).
