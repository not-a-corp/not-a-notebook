// design.md §2.3: the one decorative place in the interface, and a quiet one —
// three blurred patches of colour at the edges over a faint grid that fades
// out towards the centre. Still under prefers-reduced-motion (app.css stops
// every animation there).
export function HomeBackground() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="home-drift absolute -top-[260px] -left-[220px] size-[620px] rounded-full bg-accent opacity-12 blur-[120px]" />
      <div className="home-drift-slow absolute -right-[240px] -bottom-[300px] size-[680px] rounded-full bg-[var(--glow)] opacity-10 blur-[120px]" />
      <div className="home-drift absolute -top-[260px] right-20 size-[420px] rounded-full bg-accent opacity-8 blur-[120px] [animation-delay:-20s]" />
      <div className="home-grid absolute inset-0" />
    </div>
  );
}
