# Nano stage checklist

This is the GB10 profile. All stage services bind to loopback. The Nano drives the display directly; the SSH laptop stays backstage. Runtime outputs, branding, recordings and local settings stay under ignored `state/`.

## The day before

* Connect power and HDMI to the show display. Select the display's native resolution locally. The layout supports 1280×720, 1920×1080, 1920×1200 and 3840×2160 without scaling the page.
* Stop the owned stage stack before checking out any new commit, so the next start loads its actual backend code.
* Use the tested `nano_exec` commit and the pinned, checksum verified local models. Do not update dependencies or models before rehearsal.
* Run `./launch.sh stage record` on the Nano at native 1920×1080 to create five real H.264 backups. It warms exact segment inputs twice, records real work and decodes and seeks each backup. Recording bootstrap is preparation only. The command returns to normal stage mode afterward.
* Run `./launch.sh stage` and inspect every Ready check. For a protected event, enable **Require verified backups**. Fast live start runs the eight core checks without requiring recordings; the backup count and protection setting are visible. A runtime source or model profile change requires new recordings.
* Use `/stage/keys` with the actual clicker. Verify Next, Back, blank and unblank. The key test displays both key press and release.
* Rehearse the five beats and the three emergency moves on the local display. Audio starts off. Decide audio and HDMI routing with the AV team; do not assume the previous volume is suitable.
* The stage and Free Mode share the unchanged supplied official HP Electric Blue keyline PNG. The decorative robot hero is bundled at `showcase_app/assets/nano-agent.png`; an optional override under `state/brand/` stays private. The original vector companion is the fallback. Neither is reported as live model work.
* Keep all event settings in `state/stage/stage.local.json`. Audio and projector boost default off. Live camera and both optional segments remain disabled in this P0 build. Do not put event or employee information into source files.

## Sixty minutes before

* Sign into the Nano's local desktop. Confirm power, HDMI and native resolution.
* Run `./launch.sh stage`. Wait for the two exact input warm passes and every Ready check to turn green.
* Run `./launch.sh stage status` from the backstage terminal. Confirm every local process is owned and ready.
* Test the clicker at `http://127.0.0.1:18808/stage/keys`, then return to `/stage`.
* Make the audio decision with the AV team. Audio off is the rehearsed default. If enabled, select HDMI and allow the short preparation checks to finish.
* Decide Projector boost on the actual screen. Use the default on an LED wall; toggle boost if the room projector washes out the panels.
* Confirm all five backups are current. Never use a recording-bootstrap Ready screen for the show.

## Ten minutes before

* Run `./launch.sh stage reset`. Confirm Ready is all green and session totals have reset.
* Leave Ready up. All four model lanes receive a real tiny keep alive every 60 seconds. These requests are excluded from session totals and throughput.
* Leave power connected. Keep the SSH laptop backstage. No network or tunnel is required for the show.
* Confirm the audio and projector decisions once more. Do not change display resolution after the final check.

## Walk on

* Press Next once to begin S0. Each later Next starts its live work automatically.
* Back revisits the previous beat without rerunning it. A Next while work is running remembers one advance; extra presses do not stack.
* If the room needs a pause, B or period blanks and unblanks the screen.
* If a segment needs backup, press V. Every backup visibly says “Recorded run”. Next continues the show.
* To restart a segment, hold R for two seconds. The working indicator remains visible during recovery.

## After

* Run `./launch.sh stage stop`. This stops only verified owned processes and restores the saved per-user display settings.
* Keep private run logs in `state/stage/runs/` for review. They are not release files. Delete only outputs you created and intend to remove.
* If display restoration is needed independently, run `sh state/stage/restore-display.sh` in the same logged-in user desktop session. The file contains the exact original values recorded before this show session.
* The saved commands have this form, with the actual original values in the private restore script:

```sh
gsettings set org.gnome.desktop.session idle-delay ORIGINAL_VALUE
gsettings set org.gnome.desktop.screensaver lock-enabled ORIGINAL_VALUE
gsettings set org.gnome.desktop.screensaver idle-activation-enabled ORIGINAL_VALUE
gsettings set org.gnome.desktop.notifications show-banners ORIGINAL_VALUE
gsettings set org.gnome.desktop.notifications show-in-lock-screen ORIGINAL_VALUE
gsettings set com.ubuntu.update-notifier no-show-notifications ORIGINAL_VALUE
```

No SSH, networking, firewall, Tailscale, driver, kernel or boot service setting is changed by these stage commands.

## Repeat the physical offline check locally

1. At the desk, leave the local desktop and HDMI display running with Ready all green.
2. Unplug Ethernet and turn Wi Fi off using the local desktop controls yourself. The build agent does not change networking.
3. Check that the Network tile says Offline only if there is no default route. Local only means a default route still exists.
4. Run all five beats with the clicker. Confirm the real cloud calls counter stays zero, live artifacts finish and no Recorded run label appears.
5. Run `./launch.sh stage reset` locally and confirm Ready is green again. Reconnect networking locally after your check if desired.

## Artwork policy

Cover and gallery images are generated live as wordless abstract artwork. The local vision lane checks every candidate before it can appear. A rejected candidate is discarded and regenerated once; a second rejection uses the visibly labelled segment backup. Keep the current backup set with its matching build. The intentionally written whiteboard and chart are fictional vision inputs.

## Timed verification

Run the actual native controls and controlled failure checks before the long proof:

```sh
PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright" .venv/bin/python ops/acceptance/gb10-controls.py
PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright" .venv/bin/python ops/acceptance/gb10-stage.py chaos
PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright" .venv/bin/python ops/acceptance/gb10-stage.py final
```

The final command leaves Ready up for 45 minutes, verifies session totals stay unchanged, then runs ten actual five minute shows. The first starts directly from that idle state; resets separate the next nine. All ten capture host sockets and check that the owned stage processes use loopback and local IPC only, with the offline environment enforced. Existing SSH and unrelated host processes remain outside that application claim. Private evidence stays in `state/stage/proof/`. A failed check stops the proof; it never becomes a passing run by exclusion.

## Fast live start

With the models resident, switch from Free Mode to Presenter Mode. Preparation runs bounded language/vision and speech checks, followed by one real presenter-size image render. Every step shows actual progress and elapsed time. It does not rehearse the whole show. A page-service restart can reuse preparation only when its source signature, audio setting and all five owned process identities still match. Changing audio or returning from Free Mode runs preparation again.

Use the visible **Start presentation** button or the existing clicker. Full two-pass preparation remains available through **Full rehearsal** or `./launch.sh stage rehearse`, and is mandatory for backup recording. Fast startup is functional readiness, not full event qualification. If a live workflow fails without a verified current clip, the error remains visible and no stale video is played.
