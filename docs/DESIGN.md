# FresherPilot design system (DESIGN.md)

Target: a calm, dark-first, keyboard-friendly tool in the family of Linear / Vercel / Raycast, for someone who opens it many times a day to answer one question: **what is the system doing, and what needs me?**

## Principles (from the research)
1. **Answer first, detail on demand.** Every screen opens with one status sentence and one primary action; the rest is progressive disclosure.
2. **Dark first, light supported.** Tokens in `web/css/fp.css`; both themes use the same names.
3. **Quiet chrome.** Borders and surface steps define regions, shadows only for floating things (menus, toasts, run bar).
4. **Density 13-14px.** Base 14px (Inter / system UI), 12px secondary, tabular numbers for counts and times.
5. **Colour = meaning.** Accent = running/primary, green = done, amber = needs you, red = failed/stop. Never decorative.
6. **Motion explains state.** 150-250 ms for hover/press, 400-500 ms for entrances, spring only on small controls. Something running always looks alive (pulse, sweep, streaming steps). Honour `prefers-reduced-motion`.
7. **Keyboard.** `Ctrl K` palette everywhere; every list row reachable by arrows.
8. **The Stop button is always one click away** while anything applies (run bar, every page).

## Tokens
Surfaces `--bg < --surface < --surface-2 < --surface-3`; text `--text / --text-2 / --text-3`; lines `--line / --line-2`; accent `--accent` (violet) with `--accent-2` (cyan) gradient; status `--good --warn --bad --info` each with a `-soft` tint. Radius 8 / 12 / 18. Easing `--smooth` (cubic-bezier .22,1,.36,1), `--spring` (.34,1.56,.64,1).

## Screens (information architecture)
| Route | Question it answers | Primary action |
|---|---|---|
| Today | What needs me, what is running, what is new, what failed | Apply to new jobs / Stop |
| Jobs | Which jobs fit, what do I do with each | Auto-apply / open |
| Auto-apply | Where is the robot right now, at which step | Stop / Continue |
| Stats | Is the pipeline healthy, how many applications | none |
| Control room | Which board / AI / cloud part is working | none |
| Settings, Profile | Keys, preferences, my data | Save |

## Reference sources
- Dashboard patterns and density: AdminLTE "25 best dashboard design examples 2026", saasframe.io "Anatomy of high-performance SaaS dashboard design", 925studios "35 SaaS dashboard design examples".
- DESIGN.md format: github.com/google-labs-code/design.md; example brand files: github.com/VoltAgent/awesome-design-md.
- Job-tracker UIs (kanban pipeline Wishlist → Applied → Interview → Offer): hariharen9/jobtrac, Gsync/jobsync, fergus/job-tracker.

## Implemented layers
`fp.css` (tokens + components) → `motion.css` (glass shell, springs, live-state animation, confetti) → `fx.js` (stagger, count-up, ripple, success burst). Rebuilt views use only these classes.
