# HP ZGX Fury demo experience — V2

Open the home page at http://localhost:8080 for Demos, Why HP ZGX Fury, Shared AI and the presenter guide. Use [PRESENTER.md](docs/PRESENTER.md) for talk tracks and recovery.

# Quickstart

Use the tested Ubuntu 24.04 ARM64 GB300 host with its existing working driver, CUDA toolkit and [prerequisites](docs/PREREQUISITES.md). Reserve 350 GiB free disk for first setup; models alone download about 194 GiB.

1. Clone tag `v2.3.0` or extract the matching versioned release ZIP. See the README for exact commands.
2. Open a terminal in its root. For a ZIP, `chmod +x launch.sh showcase` if necessary.
3. Run `./launch.sh`. Read progress and errors in the terminal. The first run creates local environments, downloads/verifies assets, builds the editor and waits for all services.
4. Open **http://localhost:8080**. Subsequent launches use the same `./launch.sh` command.
5. For a predictable walkthrough, choose Factory Guided demonstration (recorded). To show genuine four-way inference, start an automatic short Factory Live build, then submit an Atlas query, booth deck and image concurrently. See the README table for prompts and URLs.
6. Use `./launch.sh status`, `./launch.sh diagnostics`, and `./launch.sh stop`. Recovery: `./launch.sh recover agent` after jobs finish.

Optional desktop shortcut: `./launch.sh desktop`; a copied desktop file may require **Allow Launching**. Remote browsers need [your own access setup](docs/REMOTE-ACCESS.md). No account or token from the publisher is needed.

[Colorado deployment PDF](docs/Colorado-Deployment-v2.3.0.pdf) includes site-owned Tailscale setup, recipient sharing, presenter steps and recovery.

Conference screens: open `/stations` on port 8080. Assign Economics (`/operator`), Why HP (`/why-hp`), or Interactive (`/demos`) independently in each browser. See docs/CONFERENCE.md.
