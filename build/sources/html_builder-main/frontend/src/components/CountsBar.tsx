/** A project's slide counts as one bar. */
export function CountsBar({ approved, review, generating, error, included }: { approved: number; review: number; generating: number; error: number; included: number }) {
  const seg = (n: number, cls: string) => n > 0 && <span className={cls} style={{ flex: n }} />;
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-line">
      {seg(approved, "bg-good")}
      {seg(review, "bg-warn")}
      {seg(generating, "bg-accent animate-pulse")}
      {seg(error, "bg-bad")}
      {seg(Math.max(0, included - approved - review - generating - error), "bg-line")}
    </div>
  );
}
