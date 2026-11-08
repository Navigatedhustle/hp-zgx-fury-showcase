# Fury v3.1.0 quickstart

Use the tested Ubuntu 24.04 ARM64 GB300 with its existing working driver and CUDA toolkit. Physical Grace memory is 494.15 GiB; the approximately 743.65 GiB Linux aggregate includes HBM. Reserve 350 GiB initially free disk; model files are about 227.566 GiB. See [prerequisites](docs/PREREQUISITES.md).

1. Clone tag `v3.1.0` with `git clone --branch v3.1.0 https://github.com/Navigatedhustle/hp-zgx-fury-showcase.git` and enter the checkout. For a checked release ZIP, measured setup times and complete partner instructions, use the [fresh Fury guide](docs/FRESH_FURY_GUIDE_v3.1.0.md).
2. Run `./launch.sh`. Keep setup progress visible; cold compilation may take tens of minutes.
3. Open **http://localhost:8080**. Eight cards open retained local workspaces.
4. Try Atlas, a three-slide presentation, an image or the included Vision/Translate samples. Video uses a fixed five-second preset.
5. For real concurrency, press **Launch Fury Rush** once. It submits six real workflows and shows their queued/submitted/complete/failed states.
6. For Action Trailer, read and tap consent before camera access. Choose a PG genre, capture once, play the final cut, then press **Done** to delete photo and video. Fullscreen sound requires a tap. Localhost downloads stay on the station.
7. Inspect `/models`, `/performance`, `/economics` and `/secure` for model identity, measured resources, dated scenarios and source evidence.
8. Use `./launch.sh status`, `./launch.sh diagnostics` and `./launch.sh stop`. Guarded recovery: `./launch.sh recover agent` after workloads finish.

Translate reflows text and offers advisory terminology review; it does not preserve source layout. Video/trailer model adapters and any two-shot fallback are disclosed. Guided Factory is recorded playback. Use fictional/public demonstration material outside the consented Action Trailer camera flow.

[Presenter](docs/PRESENTER.md) · [Fresh guide](docs/FRESH_FURY_GUIDE_v3.1.0.md) · [PDF](docs/FRESH_FURY_GUIDE_v3.1.0.pdf) · [Security policy](SECURITY.md). Private remote access uses the recipient's existing configuration; this upgrade changes no network or Tailscale settings.


To reuse a complete model directory you already own, run the following in a fresh checkout
with no `models/` entry. This explicit setup option creates the local model link and rehashes
every file against the pinned revision/SHA256 manifests without downloading or changing the
shared weights. Missing or mismatched files fail setup; no model substitution occurs.

```bash
FURY_MODELS_DIR=/absolute/path/to/verified/models ./launch.sh setup
./launch.sh
```

The original shared directory must remain available for later launches. Setup refuses to
replace a different existing `models/` directory. Never run two GPU stacks at once.

Use localhost or your approved private HTTPS hostname. Presenter controls deliberately have no PIN; the workstation account and SSH/private-network policies are the access boundary. Never expose the demo directly to the public internet or bypass parser/generated-code isolation.
