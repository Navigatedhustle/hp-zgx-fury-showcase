# Launch HP ZGX Fury — v2.3.0

Use the tested Ubuntu 24.04 ARM64 GB300 workstation with its working NVIDIA driver and CUDA toolkit, at least 700 GiB system memory, 256703 MiB GPU memory and 350 GiB free disk. See [prerequisites](PREREQUISITES.md). Do not install another model stack alongside this one.

**Install.** Clone the public release:

```bash
git clone --branch v2.3.0 https://github.com/Navigatedhustle/hp-zgx-fury-showcase.git
cd hp-zgx-fury-showcase
./launch.sh
```

Or download the v2.3.0 ZIP from [Releases](https://github.com/Navigatedhustle/hp-zgx-fury-showcase/releases/tag/v2.3.0), extract it, open a terminal in that directory, run `chmod +x launch.sh showcase`, then `./launch.sh`. No publisher account or model API key is needed. Initial setup downloads about 194 GiB of models plus dependencies. Allow for network time and kernel compilation: an empty-cache launch measured about 39 minutes on this machine. Cached launches are shorter; wait for readiness in the terminal.

**Open a station.** On the Fury, use these browser addresses. On an already configured private HTTPS host, use the same dashboard paths; microphone access needs localhost or HTTPS.

| Station or demo | Local URL |
|---|---|
| Home | http://localhost:8080/ |
| Station assignment | http://localhost:8080/stations |
| Economics | http://localhost:8080/operator |
| Why HP | http://localhost:8080/why-hp |
| Interactive demos | http://localhost:8080/demos |
| Presenter guide | http://localhost:8080/presenter |
| Atlas | http://localhost:8200/ |
| Presentations | http://localhost:8765/booth |
| Agent Factory | http://localhost:8501/devteam |
| Image Studio | http://localhost:8800/ |

Factory **Live build** performs new inference. **Guided demonstration (recorded)** replays a previous successful run. Use fictional data. See [presenter notes](PRESENTER.md) for sample inputs and the four-workload demonstration.

**Operate and recover.** Run `./launch.sh status` to inspect readiness, `./launch.sh diagnostics` for local diagnostics, and `./launch.sh stop` for an identity-checked shutdown. Wait for active jobs to finish before stopping. For a failed idle component, use `./launch.sh recover agent` (or its component name), then retry your job. Run `./launch.sh setup` to resume interrupted setup. Inspect local logs; do not publish them. Never kill an unknown process or change drivers/network settings to make a demo start.

**Rollback.** Preserve runtime output and stop the current stack first. In a clean Git checkout, run `git fetch --tags origin`, `git switch --detach v2.2.0`, `./launch.sh setup`, then `./launch.sh`. To return to this release, stop again and switch to `v2.3.0`. For ZIP installs, keep the previous directory and launch it only after stopping the current one; do not copy process registries. Never run both stacks together.

**Remote viewing.** Follow [REMOTE-ACCESS.md](REMOTE-ACCESS.md) using your own approved access. Local launch does not configure remote access. The [Colorado deployment PDF](Colorado-Deployment-v2.3.0.pdf) has the longer deployment walkthrough.
