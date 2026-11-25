"""JRV-R02: general research with provenance (search → select → read → compare → grounded answer).

The model PROPOSES (queries, which result to read, the answer). The HOST decides and verifies:
* ``provenance``: which URLs may be opened at all (only what this question's search/reads produced, or what the user
  typed), plus static destination rules; open reading also requires a transport that verifies destinations.
* ``search``: DuckDuckGo HTML results fetched through the SAME audited fetcher (per-hop host checks, limits).
* ``documents``: PDF → text on the host (fixed converter, fixed arguments, bounded).
* ``citations``: whether each cited statement is actually supported by a passage of the cited source.
* ``toolkit``: the three tools for ``AgentSession`` (``web_search``, ``web_read``, ``doc_read``) and the source registry.
External text is always DATA (framed, injection-flagged), never instructions.
"""
