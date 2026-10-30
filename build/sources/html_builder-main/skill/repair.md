# Task: fix this slide

Your previous spec for slide {{POSITION}} (variant {{VARIANT}}) was rendered and reviewed. Fix every issue below.

## What has already been tried
{{HISTORY}}

## Issues to fix (most severe first)
{{ISSUES}}

## Plan for this slide
{{PLAN}}

## Source content
{{CONTENT}}

## Assets you may use
{{ASSETS}}

## Your previous spec
{{SPEC}}

## Instructions
- Return the COMPLETE corrected spec in the same four tagged sections (<meta>, <html>, <css>, <script>). No prose.
- Fix the listed problems at their root: if content does not fit, cut words or change the layout — never shrink text below 13px.
- Overflow and clipping are answered by removing content or changing the grid, not by reducing padding or font size.
- Check every step, not only the last one: a step that reveals a card must leave room for it from the start.
- Keep what already works. Keep the variant's character ({{VARIANT_NAME}}).
- JS errors: make `go(root, step)` idempotent and null-safe; query only inside `root`.
