"""Regenerate overlay.manifest.json hashes from the PINNED vendor files (run only when deliberately moving the overlay
to a new pin, after reviewing every replaced module and string patch). Usage: python rightware/gui/frontend/build_manifest.py"""
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FE = ROOT / "vendor/openjarvis/frontend"
R = "rightware/gui/frontend/src/overrides/"
REPLACEMENTS = [
    ("src/main.tsx", "main.tsx", "RIGHTWARE theme/i18n, HUD poller, CPU budget; no analytics init"),
    ("src/components/Chat/SystemPanel.tsx", "SystemPanel.tsx", "HUD side panel (core, missions, last result) instead of cost/leaderboard"),
    ("src/components/OptInModal.tsx", "OptInModal.tsx", "no analytics/giveaway dialog (R-8)"),
    ("src/lib/analytics-invitation.ts", "analytics-invitation.ts", "never offer analytics"),
    ("src/components/Chat/MicButton.tsx", "MicButton.tsx", "voice NOT integrated: explicit disabled indicator"),
    ("src/pages/AgentsPage.tsx", "AgentsPage.tsx", "/agents shows supervised Missions"),
    ("src/pages/DataSourcesPage.tsx", "DataSourcesPage.tsx", "/data-sources shows real capability status"),
    ("src/pages/DashboardPage.tsx", "DashboardPage.tsx", "/dashboard is the full HUD"),
    ("src/components/Sidebar/Sidebar.tsx", "Sidebar.tsx", "PT-MZ navigation, language switch, no backdrop blur"),
    ("src/lib/sse.ts", "sse.ts", "explicit conversation id header (R-5)"),
]
STRINGS = {
    "src/components/Chat/ChatArea.tsx": [
        ("'Good morning'", "__rwT('chat.greeting.morning')", 1), ("'Good afternoon'", "__rwT('chat.greeting.afternoon')", 1),
        ("'Good evening'", "__rwT('chat.greeting.evening')", 1),
        ("Ask anything. Your AI runs locally — private, fast, and always available.", "{__rwT('chat.subtitle')}", 1),
        ("Connect Data Sources", "{__rwT('chat.connectSources')}", 1),
        ("Set Up Messaging Channels", "{__rwT('chat.channels')}", 1)],
    "src/components/Chat/InputArea.tsx": [
        ("'Generating...'", "__rwT('chat.generating')", 3), ("'Researching...'", "__rwT('chat.researching')", 1),
        ("'No response was generated. Please try again.'", "__rwT('chat.noResponse')", 1),
        ("onClick={() => setDeepResearch(!deepResearch)}", "onClick={() => undefined}", 1),
        ("            Deep Research\n", "            {__rwT('chat.deepResearch')}\n", 1),
        ("'Deep Research: on'", "__rwT('chat.deepResearch')", 1), ("'Deep Research: off'", "__rwT('chat.deepResearch')", 1),
        ("'Message OpenJarvis...'", "__rwT('chat.placeholder')", 1),
        ("'Pick a model first (⌘K)...'", "__rwT('chat.pickModel')", 1),
        ("<kbd className=\"font-mono\">Enter</kbd> to send &middot;", "<kbd className=\"font-mono\">Enter</kbd> {__rwT('chat.toSend')} &middot;", 1),
        ("</kbd> for new line", "</kbd> {__rwT('chat.newLine')}", 1),
        ('title="Stop generating"', "title={__rwT('chat.stop')}", 1),
        ("title={selectedModel ? 'Send message' : 'Pick a model first (⌘K)'}", "title={__rwT('chat.send')}", 1)],
    "src/components/Sidebar/ConversationList.tsx": [
        ("'No matching chats'", "__rwT('sidebar.noMatch')", 1), ("'No conversations yet'", "__rwT('sidebar.empty')", 1)],
}
HTML = {"file": "index.html", "items": [("<title>OpenJarvis</title>", "<title>RIGHTWARE JARVIS</title>", 1)]}
# Upstream tests whose subject module is replaced by the overlay (they test code that is no longer shipped).
REPLACED_TESTS = ["src/components/OptInModal.test.tsx", "src/lib/analytics-invitation.test.ts",
                  "src/pages/DataSourcesPage.lifecycle.test.tsx"]

sha = lambda p: hashlib.sha256((FE / p).read_bytes()).hexdigest()
out = {"pin": "f21d902f4d3bd7f0f3f138f1a4613019a394b549",
       "replacements": [{"upstream": u, "sha256": sha(u), "replacement": "src/overrides/" + r, "reason": why}
                        for u, r, why in REPLACEMENTS],
       "strings": [{"file": f, "sha256": sha(f), "items": [{"find": a, "replace": b, "count": n} for a, b, n in items]}
                   for f, items in STRINGS.items()],
       "html": {"file": HTML["file"], "sha256": sha(HTML["file"]),
                "items": [{"find": a, "replace": b, "count": n} for a, b, n in HTML["items"]]},
       "replacedTests": REPLACED_TESTS}
(ROOT / "rightware/gui/frontend/overlay.manifest.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
print("ok", len(out["replacements"]), sum(len(s["items"]) for s in out["strings"]))
