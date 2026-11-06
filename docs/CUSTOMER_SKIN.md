# Customer Skin

The V3 shell always identifies **HP ZGX Fury, prepared for CUSTOMER**. Customer Skin is an on-screen presentation wrapper, not a customer's own AI product.

## Presenter steps

1. Open Mission Control on any station. Presenter controls and settings are available immediately: no PIN, presenter code, account, role assignment or unlock step is required. The Presenter station role remains an optional browser layout choice.
2. Choose the palette-icon **Customize for customer** button or **Who is in the room today?** card. Enter the customer name (80 characters maximum), optionally its official website, then press Enter.
3. Watch real research steps, elapsed time and local model routing. DeepSeek is selected only if its existing slot is free; otherwise the gateway chooses Qwen. Cancel stops the lookup. A ranking failure is disclosed and leaves source-order selection to the presenter.
4. Resolve ambiguity using up to four entity cards with descriptions and official domains. Inspect up to six logo candidates on light and dark tiles. Choose **Use this logo**, **None of these — upload**, or **Try a different name**.
5. Inspect swatches and current/proposed top bar, launcher and gauge. Text contrast meets 4.5:1 and UI contrast 3:1. Adjust primary/accent colors and choose a fictional industry sample pack. A monochrome mark keeps the default V3 accent until a color is explicitly selected.
6. **Apply across stations** uses existing telemetry SSE. Explicit Apply fades colors for 450 ms; reduced motion, initial load and background sync swap instantly. **Skins** offers reset and the eight most recently confirmed cached selections.

The hero uses the actual launcher tile count. Healthy, queued and failed colors retain their meaning. Red brands receive separated dark surfaces plus status icons/text. Low-contrast logos receive a light plate. Logos render only through `img`, preserving aspect ratio without intentional recoloring or cropping.

## Keep the demo available

If customization misbehaves, choose **Default appearance** in the left navigation, or open `/demos?skin=off`. This recovery link belongs to the core shell and works without the customization script or service. The bypass follows navigation and retained workspaces in that browser, without cancelling jobs or changing other stations. **Enable customization** returns to the normal shell. **Skins → Reset to default** clears the shared active skin; `./launch.sh skin clear` also removes cached skins. Neither requires a PIN.

Appearance storage, imports and telemetry are isolated behind `skin_runtime.py`. Missing optional dependencies, damaged state/configuration and missing logo files cannot stop the core collector. Invalid skins use default colors. A damaged public request counter displays unknown and prevents further public fetching instead of inventing a zero count; manual upload remains available. Requests time out; Close dismisses immediately, and late research responses cannot reopen the dialog. The skin stylesheet changes the top bar layout only after its wrapper is ready, and initialization failure restores the native bar.

For simpler recovery, whole-document View Transitions were removed in favor of the bounded color-only CSS fade. This supersedes the original animation implementation: skin changes never create a full-page transition overlay over demo controls. Fault-injection checks cover missing scripts/styles, initialization errors, service failures, malformed state, timeouts, Cancel races and bypass navigation in Chromium and Firefox. These are tested failure boundaries, not a guarantee against every future software or hardware fault.

## Sources and local processing

Tools use Wikidata `wbsearchentities`, P154 (logo), P856 (official website), P452 (industry), and Wikimedia Commons `Special:FilePath`. Official homepages supply Organization JSON-LD logos, header/nav logo SVGs/images, Apple touch icons, largest site icons, and social previews last. The model ranks metadata and can reject photos/banners. A supplied official website starts there. Manual upload remains available.

Only deterministic tools fetch public HTTPS. The local model never receives HTML or follows page instructions. The descriptive User Agent names this demo and public repository, without a personal email. Every dispatched public request, including redirects/failures, increments **Public web lookups**, visible in the panel and `/secure`. This is separate from **External AI API calls**. No cloud AI, logo API, account, API key or new GPU model is used.

Connections pin validated public DNS answers, blocking private, loopback, link-local, metadata and transition ranges. Lookup limits: 12 requests, three redirects per file, five seconds per request, 2 MB per file and 8 MB downloaded. Source tools accept HTML/JSON; logo files accept SVG/PNG/WebP/JPEG/ICO. defusedxml and strict SVG geometry/paint allowlists remove scripts, foreign objects, handlers, external references, stylesheets and remote fonts. A bounded 512 px raster supports extraction. Raster palettes use deterministic six-cluster OKLab; dark surfaces and accessible accents use OKLCH.

## Privacy and trademark rules

Use a customer logo **only in a demo for that customer**. Confirm identity and any required permission. Public availability grants no general trademark license. Marks remain their owners' property; HP identification always stays visible. Never put a customer logo on login/payment flows or generated applications.

Names, logos, palettes, source URLs and retrieval times stay in ignored `state/skin/`: `active.json` and opaque `cache/` directories. Both Git and the explicit release inclusion policy exclude them. Tests execute the production packager against an isolated tree with a private skin sentinel. Usage records contain counts, model identity, routing and timings, never customer identity. Documentation uses only the invented Northwind Beverages artwork; other test fixtures are fictional too. Never commit real lookup names, logos, palettes or screenshots.

Factory workers, prompts, sandbox and generated app previews are frozen. Customer logos never enter PPTX, MP4, images or exports. Atlas, Presentations and Image Studio use shared shell CSS without pipeline changes. `presentations_booth_palette` in `config/skin.json` defaults to `false`; enabling it adds palette-only CSS to the **on-screen booth deck preview**, without rewriting deck records or downloaded files.

Event reset through `ops/event-session.py reset` clears the active skin. Eight hours without genuine station interaction also clears it; polling does not extend retention. Configure `idle_hours` in `config/skin.json`. Confirmed cached skins remain available to the presenter until cleared. Status prints the active skin.

## Offline mode and event prep

When public research is unavailable, one line explains the problem and opens manual mode. Upload a PNG/SVG, extract colors locally, preview and apply. **Use a logo offline** skips research. Confirmed cached selections also work without internet.

```bash
./launch.sh skin prep "Fictional Company One" "Fictional Company Two"
./launch.sh skin list
./launch.sh skin clear
```

Prep uses the same tools/gateway, prompts for ambiguity, lists local candidate files for inspection, and requires interactive logo confirmation. It caches without applying. Clear removes active/cached branding while preserving the truthful public request counter. Curated packs in `config/skin_packs/` contain generic fictional scenarios and never claim facts about a customer. Selecting a launcher tile copies its generic sample into the existing control without submitting it. Factory inputs stay frozen.

## Verification

See `docs/verification/customer_skin.json`. Unit tests use fictional fixtures and recorded responses without network. Committed screenshots are 1366×768 under `docs/screenshots/v3/skin/`, using Northwind Beverages only. Real lookup records contain timings and pass/fail only.

This feature remains a draft because Factory latency acceptance failed. The new baseline was 320.013 s, setting a 352.014 s ceiling. The first skinned build failed the existing generated-app mobile layout check; two further builds passed functionality in 367.169 s and 358.285 s, exceeding that ceiling. All attempts are retained; the baseline and frozen Factory internals were not changed. The real public lookups passed in 6.458 s, 2.892 s and 5.088 s.
