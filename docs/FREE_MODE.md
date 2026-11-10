# Nano Free Mode

Free Mode is the interactive Nano adaptation of the Fury V3 experience center. It adds a launcher, seven retained workspaces, a shared job queue, Model Hub, six-workflow Nano Rush and local downloads alongside the sequential Executive Stage.

```bash
cd ~/hp-zgx-fury-showcase
./launch.sh free
./launch.sh free status
```

Open **http://127.0.0.1:18808/free**. A cold start uses the same verified controller and model-loading order as the stage. It starts no second model stack and needs no stage recordings or full-show warm-up. The Nano Collective skin uses the supplied official HP keyline logo, an original robot hero and seven capability-colored agent illustrations. Decorative artwork is separate from live generated outputs. Starting Free Mode while the presenter is already idle switches the running page service to Free Mode. If an older page process lacks the new routes, restart that owned page service with the updated source first.

Presenter Mode's Ready screen links to Free Mode. Reset an in-progress show before switching. The Free Mode sidebar returns to Presenter Mode after all jobs finish or cancel; short functional preparation checks both language lanes, vision, a real presenter-size cover render and speech. It avoids running the entire show twice. Optional **Require verified backups** still blocks on the current build's five recordings. A free-mode model health check is not stage qualification.

| Experience | Nano behavior | Difference from Fury V3 |
|---|---|---|
| Atlas | Multi-turn account questions, four cited fictional Northwind source files, live response and TXT/source export. Uses gpt-oss-120b. | Bounded account assistant; the full Fury business/university SQL analytics, ASR and dashboard are not carried over. General answers disclose the lack of source verification. |
| Presentations | Custom briefs, 3–8 slides, previews, per-slide text/point/notes editing and native editable PPTX plus JSON export. Uses Qwen. | Concise local deck workflow; no full Fury slide library, reference-deck ingestion or PowerPoint import. Model authors the content; the local renderer supplies the visual system. |
| Agent Factory | Custom brief → gpt-oss plan → Qwen implementation → browser smoke check → sandboxed interactive preview, HTML/source and plan downloads. | Self-contained browser applications only. No generated server, external packages, network, Python execution or full Fury development team. Smoke checks do not establish application correctness. |
| Image Studio | Custom prompt, five styles, two landscape sizes, seed and batches of 1/2/4. FLUX renders sequentially; Qwen checks every candidate for lettering before publication. PNG downloads. | Wordless images, bounded landscape presets; no Send to Video. A local vision check is fallible and is not a guarantee that every image is flawless. |
| Vision Lab | Whiteboard/chart samples or a public/fictional PNG, JPEG or WebP, editable analysis question, actual Qwen image inference, result export. | No real visitor photos, camera capture, scanned-document OCR pipeline or automated accuracy claim for arbitrary images. |
| Translate Desk | Editable text, UTF-8 TXT/DOCX/text-PDF import, 34 target choices, page-aware model translation, numeric/product-code checks, TXT/DOCX downloads. | 500 KB input, 9,000 extracted characters, up to four PDF pages. Clean text reflow; no source-layout preservation, scanned PDF OCR or PDF output. Language quality requires human review. |
| Voice Studio | Custom English text, Michael/Heart voices, WAV playback and export. Uses Kokoro on CPU. | Additional standalone workspace for the Nano's resident speech model; English only, 900 characters. |

Video Studio and Action Trailer are excluded: the pinned four-model Nano profile has no Wan/video pipeline. No video or visitor-camera workflow is silently replaced with another model.

## Working with the hub

Open any experience, change its inputs and run it. Navigating between workspaces preserves their form controls and output frames for the current page session. Model jobs continue when another workspace is open. Jobs & outputs restores the latest 50 retained jobs across service restarts. Inputs in forms and Atlas conversation memory are page-session state, not a persistent personal chat account. Outputs are installation-local and shared by users of the local station.

Nano Rush reads the current inputs of Atlas, Presentations, Agent Factory, Image Studio, Vision Lab and Translate Desk, shows them before submission, then submits all six atomically. It does not use fixed presenter scripts. The host admits at most 12 unfinished jobs, runs up to three non-voice workflows at once and one speech workflow, and retains the gateway's existing admission and routing limits. FLUX still has one active renderer and three queued image jobs. Queue-full and model errors are visible; no recorded output is substituted.

Cancel stops the owning task and drains its pending image job before releasing mode ownership. Finish or cancel work before changing modes. Completed/failed/cancelled outputs can be deleted from Jobs & outputs. At the retention limit, the oldest finished job and its files are removed. Interrupted jobs are marked explicitly after a restart; they are never reported complete.

Runtime files live in ignored `state/free-mode/`; images also use the existing private creative lane. Do not commit uploads, output images, audio, decks, job records, local screenshots or model weights. Distribution includes only the explicit source allowlist. Use public/fictional demonstration documents and images, consistent with the existing repository policy.

```bash
./launch.sh stage          # sequential presenter workflow
./launch.sh stage status
./launch.sh free           # interactive experience center
./launch.sh free status
./launch.sh stage stop     # verified shutdown of the shared Nano stack
```

Both modes remain loopback-only and offline for inference. Browser mutations use the existing local origin guard. Generated apps run in an opaque sandboxed iframe with a networkless CSP. Uploaded images are resized and metadata is stripped before inference. Document contents and model text are not written to application logs; user-visible job errors avoid dumping model requests. Measured language usage, actual model identities and routing reasons use the existing ledger; free-mode run identities keep these totals separate from presenter show totals.
