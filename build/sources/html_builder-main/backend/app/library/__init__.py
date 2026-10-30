"""The slide library: a personal store of finished decks — upload, browse, favourite, tag, search, re-export.

Separate from the conversion pipeline on purpose. A library deck is never planned or generated; its files are
copies under `data/library/<deck id>/`, so deleting a project never takes library slides with it.

Modules (each owns one concern and one router):
  common.py   paths, the "library" event channel, the job key
  schema.py   the JSON shapes the API returns — the frontend's `lib/library.ts` mirrors them
  ingest.py   upload, render, parse, fingerprint, duplicates, versions, save-from-project, delete, backup
  search.py   the FTS5 index and the query language
  tagging.py  favourite → review-model summary, tags, entities; the tag vocabulary
  export.py   selected slides → one PPTX (original slides via PowerPoint, else one picture per slide)
"""
