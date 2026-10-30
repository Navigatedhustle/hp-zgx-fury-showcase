import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileUp, Library, Star } from "lucide-react";
import { Link } from "react-router-dom";
import { libApi, libKeys, useLibProjects } from "../../lib/library";
import { Thumb, slideTitle } from "./SlideCard";

/**
 * The library on the home page: what is in it, a few recent favourites, and the two ways in.
 * Hidden if the library API isn't answering, so Home never breaks on it.
 */
export function LibraryStrip() {
  const projects = useLibProjects();
  const favs = useQuery({
    queryKey: libKeys.favs,
    queryFn: () => libApi.search({ fav: true, sort: "added", limit: 6 }),
    retry: false,
  });
  if (projects.isError || !projects.data) return null;
  const p = projects.data;
  const decks = p.reduce((n, x) => n + x.decks, 0);
  const slides = p.reduce((n, x) => n + x.slides, 0);
  const favourites = p.reduce((n, x) => n + x.favourites, 0);
  const recent = favs.data?.items ?? [];
  return (
    <section className="mt-12" aria-labelledby="library-strip">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="library-strip" className="text-lg font-bold tracking-tight">Slide library</h2>
        {decks > 0 && (
          <span className="text-sm text-muted">
            {slides} slides · {decks} {decks === 1 ? "deck" : "decks"} · {p.length} {p.length === 1 ? "project" : "projects"} · {favourites} favourites
          </span>
        )}
      </div>
      <div className="rounded-2xl border border-line bg-surface p-4">
        {decks === 0 ? (
          <p className="text-[14px] text-muted">
            Keep every PowerPoint you have made in one place and find any slide again by what it says. Favourites are
            summarised and tagged for you.
          </p>
        ) : recent.length > 0 ? (
          <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6" aria-label="Recent favourites">
            {recent.map(s => (
              <li key={s.id}>
                <Link to={`/library?fav=true&open=${s.id}`} title={slideTitle(s)} className="block overflow-hidden rounded-md ring-1 ring-line-2 hover:ring-accent">
                  <Thumb src={s.thumb} alt={slideTitle(s)} />
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="flex items-center gap-1.5 text-[14px] text-muted"><Star className="size-4 text-warn" />Star the slides you reuse — they show up here.</p>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Link to="/library" className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-accent px-3 text-[13px] font-semibold text-accent-ink shadow-sm hover:brightness-110">
            <Library className="size-4" />Open library<ArrowRight className="size-3.5" />
          </Link>
          <Link to="/library?upload=1" className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line bg-surface px-3 text-[13px] font-semibold text-ink hover:border-faint">
            <FileUp className="size-4" />Add PPTX to library
          </Link>
        </div>
      </div>
    </section>
  );
}
