"""RIGHTWARE Tool Gateway (JRV-P3A product runtime component).

Runs inside the isolated gateway image (configs/gateway/Dockerfile) for host-enabled supervised missions:
``gateway`` (AgentPolicy + ReceiptLedger behind MCP), ``mcp_http`` (transport, client allowlist, evidence),
``model_tap`` (tool filter at the model boundary), ``report_contract`` (te-p2b.report.v1) and ``verify``
(RIGHTWARE verifier). ``synthetic/`` holds the synthetic catalogue trial material used ONLY by the synthetic
mission capability. Moved from labs/ without semantic change: see PARITY.json. Off unless the host enables it.
"""
