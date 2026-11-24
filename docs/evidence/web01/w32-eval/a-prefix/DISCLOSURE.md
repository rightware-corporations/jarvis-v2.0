# Independence disclosure (W3.2 evaluation)
- The first W3.2 run (pre-fix code, "W3.2-a") completed S3 (offline revalidation R1–R5) and then started S2.
- Before it was stopped, two S2 results were printed and SEEN: G1 ADEQUATE (GROUNDED), G2 NOT ADEQUATE (ABSTAIN).
- The fixes committed in `c94c887` came from analysing R3/R4 of S3 (stored real bytes): retrieval ranking by attribute
  key, own overlap and subject/bridge entity; parts mostly made of question words; notes limited; evidence_id/quote format.
  They were NOT derived from G2: no G2 detail (plan, candidates or answer) was inspected.
- The final run ("b-final") runs S2 exactly once with the final code. S2 results are NOT used for further tuning.
