# OutreachPilot Full Redesign Plan

Status: Phases 0 to 6 committed on redesign/v2 (2026-11-16). Next: Phase 7, final review.

## Ground rules

1. All work happens on a new branch `redesign/v2`, cut from `main`. `main` is never touched.
2. Design only. No change to routes, Jinja context variables, form fields, API calls, auth, quotas, SEO metadata or any JS logic.
3. One design in two themes. Dark mode swaps only the background, surface, border and text tokens. The accent hue, layout, radius, spacing, shadows and motion stay the same. No neon, no glow, no gradient text, no new accent colors in dark.
4. Palette rules from past feedback still apply: no generic SaaS blue, no saturated orange or terracotta, no neon. Plain English copy, no dashes, no `//` chips, no jargon.
5. Every screen must work on phone (375), tablet (768) and desktop (1280+), in both themes.
6. Local-only AI files (the `ai_agent.py` working copy, the local-model block in `config.py`, `local_enrich.py`) are never staged on this branch either.

## Chosen direction (2026-11-15)

Direction C, "Field Guide", from the Phase 0 style tile:
- Type: Young Serif (headlines), Figtree (text), IBM Plex Mono (data). Self-hosted woff2.
- Accent: moss #56672A, the same value in light and dark. Sand paper backgrounds in light, warm near-black in dark.
- Shape: soft corners (cards 18px, inputs 12px), pill buttons and chips, a dotted map texture, city pins.

Applied with the ambition and richness of `var/temp/index.html` on every screen: a sticky nav with a scroll progress line and a sliding hover pill, a full-screen mobile menu, an animated product demo in the hero (map, results, email draft, a five-step progress row), rotating headline words, scroll reveals, count-up numbers, city and category marquees, an old-way versus new-way comparison, scroll-driven how-it-works, a bento feature grid, audience cards, a security section, pricing, FAQ, a final call to action and a full footer.

What changes from the reference:
- Moss instead of orange. No glow, no gradient text, no colored shadows in dark mode. Emphasis words use Young Serif in the accent color.
- Numbers come only from live server data (city and category counts, plan limits). Demo panels are labelled as sample. No made-up totals, names or quotes.
- Copy stays plain English with no dashes.
- New homepage elements only link to things that already exist (`/app`, `/directory`, sign in, city and category pages). No new features.

## What I found in the current code

- FastAPI + Jinja2, 12 templates, none use `extends`, `include` or macros. Every page repeats its own head, theme script, nav and footer.
- Every page loads the Tailwind Play CDN at runtime (`cdn.tailwindcss.com`) with its own inline `tailwind.config`. The look lives in utility classes inside the HTML (index 510 lines of classes, admin 558, landing 295).
- `app.js` (233KB) builds a lot of the UI as HTML strings (about 330 `class="..."` strings, 102 `innerHTML` writes), so the look is partly baked into JS.
- `lucide@latest` and `marked` load without a pinned version.
- No CSP header, no test suite, no build step.

## Key technical decision

Replace the Tailwind runtime with a small hand-written design system:

- `static/css/tokens.css` for colors, type, spacing, radius, shadow, motion (light + dark).
- `static/css/base.css` for reset, typography and layout primitives.
- `static/css/components/*.css` for buttons, inputs, custom dropdown, chips, cards, tables, tabs, modals, toasts, sidebar, nav, footer, empty states, skeletons.
- `static/css/pages/*.css` for landing, app, admin, directory and legal.

Why: the redesign has to rewrite every class string anyway. Semantic classes (`.op-card`, `.op-chip`) make the look consistent, make dark mode a pure token swap, remove the runtime CDN compile and first-paint flash, and give the block-wise structure you asked for.

State classes the JS toggles today (`hidden`, active/open/selected states, about 47 unique strings in `app.js`) are kept with the same names so no logic changes.

## Safety net for "no functionality change"

Before any redesign work, a scratch script in `var/` records a contract for every template and JS file:
- every `id`, `name`, `for`, `data-*`, form `action`/`method`, `href` to an app route
- every Jinja variable, `if`/`for` block and filter used
- every selector and class the JS reads or toggles
- every `<meta>`, canonical, JSON-LD and heading on directory and SEO pages

After each phase the script runs again and must report zero missing items. Then I click through each screen in the browser pane in both themes and at three widths, with no console errors.

## Phases

Each phase ends with your review. I commit to the branch only after you approve that phase.

### Phase 0: Branch, contract and design direction
- Create `redesign/v2`, build the contract inventory.
- Present 2 to 3 design directions as a style tile: palette (light and dark side by side), type pairing, buttons, inputs, dropdown, card, table, chip, a sample app row and a sample hero. You pick one.
- Fonts self-hosted as woff2, like today.
- `var/temp/index.html` is treated as the quality bar and a source of section ideas for the homepage, not a palette to copy, because its orange gradient breaks rule 4.

### Phase 1: Foundation
- Tokens, base and component CSS for the chosen direction.
- `templates/base.html` with blocks (`title`, `meta`, `head_extra`, `body_class`, `content`, `scripts`).
- `templates/partials/`: head, theme boot script, public nav, footer, app sidebar, admin sidebar, modal shell, toast container.
- `templates/macros/`: button, input, select/dropdown, chip, card, stat, empty state, pagination.
- Pin icon and markdown library versions (visual only).

### Phase 2: Public pages
- `landing.html` redesigned from scratch: hero, how it works (resume, directory, AI draft, send from your Gmail), directory preview, trust and privacy, tiers, FAQ, final call to action. Real copy only, no fake stats or logos.
- `privacy.html`, `terms.html`, `404.html`, `error.html`, `maintenance.html` on the new system.

### Phase 3: Directory and SEO pages
- `directory_hub.html`, `directory.html`, `directory_combo.html`, `company_profile.html`.
- Keep every meta tag, canonical, JSON-LD block, heading level and internal link exactly as is.

### Phase 4: App (`/app`)
- `index.html` plus the HTML strings inside `app.js`: Companies tab, filters and custom dropdown, company cards and detail, Candidate Profile, Outreach Hub, email draft and send flow, quota and tier states, every modal, toast, empty and loading state.
- Only class names and wrapper markup in JS strings change. No logic, no data flow, no event wiring.

### Phase 5: Admin (`/admin`)
- `admin.html` plus HTML strings in `admin.js`: users, bans, tiers, maintenance, GitHub Actions dispatch, sent pitches audit, kill switch. Mobile sidebar and table layouts.

### Phase 6: Code split
- `app.js` and `admin.js` split by feature into plain scripts loaded in order (no build step, same global scope, so behavior is identical). Example layout: `static/js/app/core.js` (state, fetch helpers), `ui.js` (dropdown, modal, toast), `companies.js`, `profile.js`, `outreach.js`, `boot.js`. Exact cut lines decided from the code at that point.
- Pure move: no renamed functions, no changed logic. `node --check` on every file and a full click-through after each split.

### Phase 6 result (2026-11-16)
- app.js and admin.js are each one DOMContentLoaded closure whose functions share local state, so a plain-script split can only move functions that touch no shared state. A parser check (acorn) proved 24 such functions in app.js and 7 in admin.js.
- Moved unchanged into static/js/app/ (utils, feedback, pagination, dropdown, activity, subscription, profile, theme) and static/js/admin/ (modals, controls, kill-switch, workflows), loaded before the controller. app.js 4962 to 4016 lines, admin.js 2044 to 1818.
- Splitting the stateful controllers further needs a shared state module, which rewrites logic. Left for a separate, explicitly approved change.

### Phase 7: Final QA and handoff
- Contract script: zero missing items across all pages.
- Every screen at 375, 768, 1280 and 1440 in light and dark. Keyboard focus states, reduced-motion support, color contrast AA.
- Copy grep for dashes, `//` chips and jargon.
- Cache-buster `?v=` bumps on every changed asset.
- Bring in any new commits from `main` (Antigravity work) and resolve conflicts.
- Push the branch only when you say so. Merging to `main` is your call.

## Risks

- `main` keeps moving while this branch is open. I'll merge `main` into the branch at the end of each phase so it does not drift.
- JS-generated markup is the biggest regression risk. The contract script and click-throughs cover it.
- Removing Tailwind means any class I miss shows unstyled. The contract script lists every class each page uses, before and after.

## Phase 7 result and review loop

- Phase 7 QA (commit d656741): contrast tokens fixed to WCAG AA, directory card overflow at 375px, /app toolbar and card grid at 768px, cache version bump. 11 pages checked at 375, 768 and 1440 in light and dark.
- Review pass 1: workspace counters show thousands separators (display only); stat card wording made plain; "/" focuses the search box on /app; app.js and admin.js now use the shared cache version so restyled code always reaches the browser.
- Functional ideas from the review are in REDESIGN_PROPOSALS.md and are not built.
- Review pass 2: /app search and filters sit on one line on wide screens with search taking the free space; pager numbers use separators (5,538); the company profile "At a glance" card now really stays in view while scrolling.
- Review pass 3: Ban / Unban buttons in /admin users get their red / green outline (classes the utility generator missed); company names on /app cards can use three lines on phones so they are not cut short. /admin, /app, landing and company profile checked at 375 with no horizontal scroll.
- Review pass 4 (dark theme): automated WCAG contrast scan of landing, directory, city hub, company profile, privacy, 404, all /app tabs and all /admin tabs. Fixed three failures: the highlighted demo row on the landing page, the industry tag on hub company cards (inline style moved to .co-tag), and the amber warn button in /admin (white text, also failed in light). Only decorative giant numerals and breadcrumb slashes remain below 4.5.
- Dark theme rework (user feedback: dark did not match the reference): dark tokens now follow var/temp/index.html: near-black layers #07080B / #101218 / #151821 / #1C202B, translucent white hairlines, reference shadows with the inset top highlight, glass nav, map colors, and the reference film grain on public pages. Moss accent kept (no orange, no neon). text-3 lifted to #868A95 for AA. Contrast scan: 0 failures on 9 pages plus the company modal.
- Interactive map canvas everywhere: moved from four page templates into base.html, so every page (landing, directory pages, company profiles, legal, error pages, /app, /admin) gets it. Clicks on solid panels, cards, tables, modals and overlays no longer launch a plane, so the workspace stays usable; empty background still reacts.
