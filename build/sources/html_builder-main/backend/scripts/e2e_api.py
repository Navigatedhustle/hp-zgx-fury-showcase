"""End-to-end API test: upload -> plan -> generate -> choose/revise -> export. Run against a live server (mock or real)."""
import json
import sys
import time
from pathlib import Path

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
DECK = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).resolve().parents[2] / "evals" / "decks" / "hp_z_workstations_genai.pptx")
c = httpx.Client(base_url=BASE, timeout=600)


def wait(pid, pred, label, timeout=1800):
    t0 = time.time()
    while time.time() - t0 < timeout:
        p = c.get(f"/api/projects/{pid}").json()
        if p["status"] == "error":
            raise SystemExit(f"project error: {p['error']}")
        if pred(p):
            print(f"  {label} in {time.time() - t0:.1f}s")
            return p
        time.sleep(1.5)
    raise SystemExit(f"timeout waiting for {label}")


print("health", c.get("/api/health").json())
r = c.post("/api/projects", files={"file": (DECK.name, DECK.read_bytes(), "application/vnd.openxmlformats-officedocument.presentationml.presentation")})
r.raise_for_status()
pid = r.json()["id"]
print("project", pid)
p = wait(pid, lambda p: p["status"] == "ready", "planned")
print("  renderer:", p["renderer"], "| brief:", json.dumps(p["brief"])[:200])
for s in p["slides"]:
    print(f"   #{s['index']:>2} {s['plan'].get('pattern', ''):<10} {s['plan'].get('headline', '')}")

c.post(f"/api/projects/{pid}/generate", json={}).raise_for_status()
p = wait(pid, lambda p: p["status"] in ("reviewing", "complete") and p["counts"]["generating"] == 0, "generated")
for s in p["slides"]:
    vs = s["versions"]
    print(f"   #{s['index']:>2} {s['status']:<8}", " | ".join(
        f"{v['lineage']}{v['number']} {v['status']} score={v['score']} errs={sum(1 for f in v['qa']['findings'] if f['severity'] == 'error')}"
        for v in vs))
    for v in vs:
        for f in v["qa"]["findings"]:
            print(f"        {v['lineage']} [{f['severity']}] {f['code']}: {f['message'][:140]}")

s0 = p["slides"][2]
a = next(v for v in s0["versions"] if v["lineage"] == "A")
c.post(f"/api/slides/{s0['id']}/revise", json={"base_version_id": a["id"], "comment": "Make the title shorter and use a navy background."}).raise_for_status()
time.sleep(1)
p = wait(pid, lambda p: p["counts"]["generating"] == 0, "revised")
print("   versions on slide 3:", [(v["lineage"], v["number"], v["status"], v["comment"][:20]) for v in p["slides"][2]["versions"]])

for s in p["slides"]:
    ready = [v for v in s["versions"] if v["status"] == "ready"]
    if ready:
        c.post(f"/api/slides/{s['id']}/choose", json={"version_id": ready[-1]["id"]}).raise_for_status()
p = c.get(f"/api/projects/{pid}").json()
print("status after approvals:", p["status"], p["counts"])

prev = c.get(f"/api/versions/{p['slides'][0]['versions'][0]['id']}/preview")
print("preview", prev.status_code, len(prev.text))
st = c.get(f"/api/projects/{pid}/export/stats").json()
print("export stats", st)
h = c.get(f"/api/projects/{pid}/export.html")
out = Path(__file__).resolve().parents[2] / "data" / "e2e_deck.html"
out.write_bytes(h.content)
print("html", h.status_code, len(h.content), "->", out)
pdf = c.get(f"/api/projects/{pid}/export.pdf")
(out.with_suffix(".pdf")).write_bytes(pdf.content)
print("pdf", pdf.status_code, len(pdf.content))
print("PID", pid)
