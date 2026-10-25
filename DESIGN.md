---
name: OutreachPilot Design System
version: 3.0.0
frameworks:
  - make-interfaces-feel-better
  - gpt-taste
  - emil-design-eng
  - industrial-brutalist-ui
  - hallmark
  - taste-skill
  - web-design-guidelines
  - awesome-design-md
  - playwright-cli
colors:
  surface: '#090A0D'
  surface-dim: '#050608'
  surface-bright: '#22252F'
  surface-container-lowest: '#07080B'
  surface-container-low: '#0D0E12'
  surface-container: '#121419'
  surface-container-high: '#181A21'
  surface-container-highest: '#20232C'
  on-surface: '#F8FAFC'
  on-surface-variant: '#94A3B8'
  inverse-surface: '#F8FAFC'
  inverse-on-surface: '#090A0D'
  outline: '#232630'
  outline-variant: '#1A1C23'
  surface-tint: '#F59E0B'
  primary: '#FBBF24'
  on-primary: '#090A0D'
  primary-container: '#F59E0B'
  on-primary-container: '#090A0D'
  inverse-primary: '#D97706'
  secondary: '#10B981'
  on-secondary: '#FFFFFF'
  secondary-container: '#059669'
  on-secondary-container: '#ECFDF5'
  tertiary: '#EA580C'
  on-tertiary: '#FFFFFF'
  tertiary-container: '#C2410C'
  on-tertiary-container: '#FFF7ED'
  error: '#EF4444'
  on-error: '#FFFFFF'
  error-container: '#7F1D1D'
  on-error-container: '#FEF2F2'
  background: '#090A0D'
  on-background: '#F8FAFC'
  surface-variant: '#1A1C24'
typography:
  display-xl:
    fontFamily: Inter, -apple-system, sans-serif
    fontSize: 56px
    fontWeight: '700'
    lineHeight: 64px
    letterSpacing: -0.04em
  display-lg:
    fontFamily: Inter, -apple-system, sans-serif
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.03em
  headline-xl:
    fontFamily: Inter, -apple-system, sans-serif
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.025em
  headline-lg:
    fontFamily: Inter, -apple-system, sans-serif
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter, -apple-system, sans-serif
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.015em
  headline-sm:
    fontFamily: Inter, -apple-system, sans-serif
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter, -apple-system, sans-serif
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 26px
    letterSpacing: -0.005em
  body-md:
    fontFamily: Inter, -apple-system, sans-serif
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
    letterSpacing: 0em
  body-sm:
    fontFamily: Inter, -apple-system, sans-serif
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0.005em
  label-caps:
    fontFamily: JetBrains Mono, monospace
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.08em
  data-metric:
    fontFamily: JetBrains Mono, monospace
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.02em
rounded:
  sm: 0.375rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.25rem
  gutter-lg: 2rem
  margin: 1.5rem
  margin-lg: 3rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
  space-2xl: 4rem
---

# OutreachPilot Design System Specification

Engineered according to **Taste Skill v2** (Anti-Slop Architecture), **Vercel Web Interface Guidelines**, **Awesome DESIGN.md Tokens**, and **Playwright Visual Verification**.

## 1. Aesthetic Identity & Anti-Slop Directive
- **Anti-Slop Principle**: Banish decorative purple/pink gradient blobs and identical generic icon cards. Build with deep graphite field contrast, subtle 1px border illumination, tactile elevation, and authentic domain-specific copy.
- **The Core Sentence**: *On this page, automated company intelligence and executive contact discovery becomes an instant, tactile personalization engine.*
- **The "One Live Thing"**: An interactive live Pitch & Scout Sandbox right on the landing page, letting visitors choose real company profiles, toggle personalization tone parameters, and see real-time synthesized email outreach with verified recruiter signals.

## 2. Color Foundation & Tonal Hierarchy
- **Base Canvas (`#0B0F17`)**: Ergonomic, deep obsidian-graphite plane that eliminates harsh eye strain.
- **Surface Elevation 1 (`#111726`)**: Primary card hulls, hero preview windows, and feature modules.
- **Surface Elevation 2 (`#1A2234`)**: Interactive targets, hover states, filter dropdowns, and modal dialogs.
- **Crisp Dividers (`#1E273A` & `#2D3A54`)**: Razor-thin 1px borders providing structure without visual noise.
- **Accent Indigo (`#6366F1`) & Glow (`rgba(99, 102, 241, 0.2)`)**: Primary execution buttons, selected navigation items, and active progress pulses.
- **Verified Emerald (`#10B981`)**: Authentic email signals, deliverability indicators, and high lead scores.
- **Amber Signal (`#F59E0B`)**: Rate limits, scheduled warmups, and attention cues.

## 3. Typography & Numerical Precision
- **Primary Interface**: `Inter`, `-apple-system`, `sans-serif` with tight negative letter-spacing on headlines (`-0.02em` to `-0.04em`).
- **Telemetry & Numbers**: `JetBrains Mono` with `font-variant-numeric: tabular-nums` for all lead metrics, timestamps, and confidence percentages. Zero layout shifting during state changes.

## 4. Web Interface Guidelines (Vercel Standards)
- **Zero CLS**: Fixed dimensional reserves for dynamic lead counts and status chips.
- **Contrast**: Text contrast strictly WCAG AA compliant (`#F1F5F9` on `#0B0F17` = 15.2:1 contrast ratio; `#94A3B8` on `#0B0F17` = 6.8:1).
- **Keyboard Navigation**: Focus rings (`outline: 2px solid #6366F1; outline-offset: 2px`) on all interactive buttons, inputs, and tabs.
- **State Feedback**: Default -> Hover (`translateY(-1px)`) -> Pressed (`scale(0.98)`) -> Disabled (`opacity: 0.5; cursor: not-allowed`).

## 5. Automated Verification
- Headless visual regression audits executed via Microsoft Playwright CLI (`npx @playwright/cli screenshot`).
