# Nano quickstart

For the **HP ZGX Nano / NVIDIA GB10**, start with [the fresh-install guide](docs/NANO_QUICKSTART.md) or [download its PDF](https://github.com/Navigatedhustle/hp-zgx-fury-showcase/releases/download/v3.2.0-nano.3/HP-ZGX-Nano-Quickstart.pdf).

```bash
git clone --branch v3.2.0-nano.3 --depth 1 \
  https://github.com/Navigatedhustle/hp-zgx-fury-showcase.git hp-zgx-nano
cd hp-zgx-nano
./install.sh
./launch.sh free
```

Use Ubuntu 24.04 ARM64, 128 GB unified memory, an existing working NVIDIA driver/CUDA toolkit and 200 GiB free disk. Initial setup downloads about 95.9 GiB of models plus dependencies. Open http://127.0.0.1:18808/free on the Nano; switch to Presenter Mode from the sidebar. [Full guide](docs/NANO_GUIDE.md) · [Share kit and release](https://github.com/Navigatedhustle/hp-zgx-fury-showcase/releases/tag/v3.2.0-nano.3).

---

# Fury V3 quickstart

Use the tested Ubuntu 24.04 ARM64 GB300 with its existing working driver and CUDA toolkit. Physical Grace memory is 494.15 GiB; the approximately 743.65 GiB Linux aggregate includes HBM. Reserve 350 GiB initially free disk; model files are about 227.566 GiB. See [prerequisites](docs/PREREQUISITES.md).

1. Clone branch `v3` and enter the checkout. V3 is an unmerged review branch, not a published tag or release.
2. Run `./launch.sh`. Keep setup progress visible; cold compilation may take tens of minutes.
3. Open **http://localhost:8080**. Eight cards open retained local workspaces.
4. Try Atlas, a three-slide presentation, an image or the included Vision/Translate samples. Video uses a fixed five-second preset.
5. For real concurrency, press **Launch Fury Rush** once. It submits six real workflows and shows their queued/submitted/complete/failed states.
6. For Action Trailer, read and tap consent before camera access. Choose a PG genre, capture once, play the final cut, then press **Done** to delete photo and video. Fullscreen sound requires a tap. Localhost downloads stay on the station.
7. Inspect `/models`, `/performance`, `/economics` and `/secure` for model identity, measured resources, dated scenarios and source evidence.
8. Use `./launch.sh status`, `./launch.sh diagnostics` and `./launch.sh stop`. Guarded recovery: `./launch.sh recover agent` after workloads finish.

Translate reflows text and offers advisory terminology review; it does not preserve source layout. Video/trailer model adapters and any two-shot fallback are disclosed. Guided Factory is recorded playback. Use fictional/public demonstration material outside the consented Action Trailer camera flow.

[Presenter](docs/PRESENTER.md) · [V3 launch guide](docs/V3_LAUNCH_GUIDE.md) · [PDF](docs/V3_Launch_Guide_v3.0.0.pdf). Private remote access uses the recipient's existing configuration; this upgrade changes no network or Tailscale settings.
