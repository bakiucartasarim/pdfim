---
name: Precision Editorial
colors:
  surface: '#faf8ff'
  surface-dim: '#d2d9f4'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e2e7ff'
  surface-container-highest: '#dae2fd'
  on-surface: '#131b2e'
  on-surface-variant: '#464555'
  inverse-surface: '#283044'
  inverse-on-surface: '#eef0ff'
  outline: '#777587'
  outline-variant: '#c7c4d8'
  surface-tint: '#4d44e3'
  primary: '#3525cd'
  on-primary: '#ffffff'
  primary-container: '#4f46e5'
  on-primary-container: '#dad7ff'
  inverse-primary: '#c3c0ff'
  secondary: '#0058be'
  on-secondary: '#ffffff'
  secondary-container: '#2170e4'
  on-secondary-container: '#fefcff'
  tertiary: '#960014'
  on-tertiary: '#ffffff'
  tertiary-container: '#bc1d25'
  on-tertiary-container: '#ffd0cc'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e2dfff'
  primary-fixed-dim: '#c3c0ff'
  on-primary-fixed: '#0f0069'
  on-primary-fixed-variant: '#3323cc'
  secondary-fixed: '#d8e2ff'
  secondary-fixed-dim: '#adc6ff'
  on-secondary-fixed: '#001a42'
  on-secondary-fixed-variant: '#004395'
  tertiary-fixed: '#ffdad7'
  tertiary-fixed-dim: '#ffb3ad'
  on-tertiary-fixed: '#410004'
  on-tertiary-fixed-variant: '#930013'
  background: '#faf8ff'
  on-background: '#131b2e'
  surface-variant: '#dae2fd'
typography:
  display-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.015em
  headline-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.01em
  title-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: -0.005em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: -0.005em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0em
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.005em
  label-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.03em
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-compact: 0.5rem
  margin: 1.5rem
  margin-mobile: 0.75rem
  space-xxs: 0.125rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1.25rem
  space-xl: 2rem
---

## Brand & Style

This design system establishes a high-performance, studio-grade aesthetic for a document manipulation and PDF productivity platform. The visual style merges **Corporate / Modern** rigor with subtle **Glassmorphism** to reflect absolute precision, technical fluency, and workflow velocity.

### Target Audience & Personality
Built for knowledge workers, legal operators, enterprise teams, and technical specialists who interact with dense, high-stakes documents daily. The UI prioritizes cognitive clarity and ergonomic speed. The emotional response is calm, razor-sharp, and unyielding in reliability—evoking the confidence of an industrial-grade creative or analytical suite.

### Visual Principles
- **Clarity Over Ornament:** Chrome yields to content. Canvas backgrounds remain pristine and neutral, ensuring document pages stand out as the primary focus.
- **Instrument Density:** Controls, toolbars, and inspector panels use compact, tight vertical rhythms inspired by professional creative workstations.
- **Atmospheric Translucency:** Floating toolbars, zoom controls, and contextual popovers utilize soft backdrop blurs to preserve contextual awareness without obscuring canvas viewport data.

## Colors

The color architecture balances focused deep neutrals with electric functional accents to direct attention across high-density tool panels.

### Application Palette
- **Primary (`#4F46E5`):** Reserved for core call-to-actions, focused node outlines, active tab indicators, and primary edit states.
- **Secondary (`#3B82F6`):** Highlights selection marquees, annotation bounds, text highlighting, and secondary progress indicators.
- **Tertiary / PDF Accent (`#EF4444`):** Anchors file-type identity, destructive actions (e.g., delete page, purge signature), and critical alert badges.
- **Neutral Core (`#0F172A`):** Anchors deep typographic contrast in light mode and defines rich dark workspace chrome when operating in dark canvas modes.

### Surface Tiers
- **Canvas Base:** `#F1F5F9` (Light Mode Canvas) / `#090D16` (Dark Mode Canvas) provides deep contrast against the white document paper (`#FFFFFF`).
- **Surface Panels:** `#FFFFFF` (Light) / `#0F172A` (Dark) with 1px structural borders at `#E2E8F0` / `#1E293B`.
- **Translucent Overlays:** `rgba(255, 255, 255, 0.82)` and `rgba(15, 23, 42, 0.85)` paired with a 12px blur for floating action bars and context menus.

## Typography

The typography system relies on a dual-engine hierarchy: **Plus Jakarta Sans** provides geometric clarity and forward-leaning structural presence for section titles and modal headers, while **Inter** delivers neutral, highly-legible data density for tooltips, document trees, properties inspectors, and standard UI chrome.

### Hierarchy & Scale Rules
- **Display & Headlines:** Used strictly for administrative dashboards, conversion workflows, and modal headers. Never used inside the PDF canvas workspace or floating strips.
- **Labels & Micro-copy:** Labels (`label-sm`) default to uppercase with slight tracking (`0.03em`) for inspector panel headers (e.g., "PAGE ATTRIBUTES", "COLOR PROFILE", "ENCRYPTION").
- **Tabular Data:** Page coordinates, scale percentages, and measurement readouts must utilize font-feature-settings `"tnum"` (tabular figures) to avoid layout jitter during rapid scrubbing.

## Layout & Spacing

The workspace operates on an ultra-compact 4px baseline sub-grid, scaling to an 8px architectural grid for outer structures. The document viewport behaves as an infinite virtual canvas framed by fixed dock panels and floating utility surfaces.

### Layout Model
- **Primary Chrome Frame:**
  - **Top Ribbon / App Bar:** Fixed `48px` height. Holds document metadata, export targets, and workspace modes.
  - **Left Rail (Thumbnails & Layers):** Collapsible, default width `240px` (expandable to `360px`, min `48px` icon state).
  - **Right Inspector (Properties & OCR):** Collapsible, fixed width `280px`.
  - **Document Stage:** Auto-calculating flexible viewport centered on the physical page canvas.
- **Floating Island Toolbars:** Floating contextual actions (text editing, signature injection) hover 24px above active selections with zero canvas boundary clip.
- **Breakpoints:**
  - **Mobile (< 768px):** Rails collapse into swipeable bottom sheets; top toolbar condenses to essential undo/redo, share, and page switcher.
  - **Tablet (768px - 1024px):** Single active sidebar docked at a time; page thumbnail reel toggles from horizontal footer shelf.
  - **Desktop (> 1024px):** Dual-dock full productivity layout with multi-document split-screen capabilities.

## Elevation & Depth

Visual hierarchy uses crisp boundary containment combined with subtle, luminous ambient shadows. Translucent glass layers keep spatial relationships clear across overlapping interface elements.

### Elevation Levels
- **Level 0 (Stage/Base):** `background-color: #F1F5F9`. No shadow. Flat workspace background for page rendering.
- **Level 1 (Document Paper & Docked Panels):** Flat surface with `1px` continuous border `rgba(15, 23, 42, 0.08)` and subtle shadow: `0 1px 3px 0 rgba(15, 23, 42, 0.04), 0 1px 2px -1px rgba(15, 23, 42, 0.04)`.
- **Level 2 (Dropdowns, Menus & Tool Shelves):** Translucent backdrop: `backdrop-filter: blur(12px)`, background `rgba(255, 255, 255, 0.88)`. Shadow: `0 4px 6px -1px rgba(15, 23, 42, 0.07), 0 2px 4px -2px rgba(15, 23, 42, 0.05)`, border `1px solid rgba(255, 255, 255, 0.6)`.
- **Level 3 (Modals, Overlays & Dragged Pages):** Active drag states and dialog surfaces: `0 20px 25px -5px rgba(15, 23, 42, 0.1), 0 8px 10px -6px rgba(15, 23, 42, 0.06)`. Border: `1px solid rgba(15, 23, 42, 0.12)`.

## Shapes

The design system maintains a **Soft** shape metric (`roundedness: 1`). Controls are tailored for density, utilizing controlled, geometric perimeters that maximize interior data volume.

### Radius Assignments
- **Micro Shapes (`2px`):** Checkbox indicators, scrub bar thumbs, custom scrollbar tracks.
- **Standard Controls (`4px` / `0.25rem`):** Buttons, inputs, tab segments, dropdown items, toolbar icon toggles.
- **Panels & Cards (`8px` / `0.5rem`):** Flyout menus, contextual toolstrips, document thumbnail cards, toast notifications.
- **Modals & Dialogs (`12px` / `0.75rem`):** Export flows, document settings modals, digital certificate signing windows.
- **Full Radius (`9999px`):** Pill-shaped zoom controls, status tags, active page counter indicators.

## Components

### Buttons & Icon Controls
- **Primary Action Button:** Height `32px` (dense toolbar) or `38px` (prominent). Solid `#4F46E5` background, `#FFFFFF` text, `4px` radius. Hover: `#4338CA`. Active: scale `0.98`. Focus ring: 2px offset with `#3B82F6`.
- **Toolbar Action Icons:** Square `32x32px` buttons with `4px` radius. Neutral transparent background. On hover: `rgba(15, 23, 42, 0.05)`. Active/Selected: `#EEF2FF` text with `#4F46E5` foreground icon.
- **Destructive Action:** Ghost button with `#EF4444` hover tinting, transitioning to solid `#EF4444` fill on modal confirmation steps.

### Inputs & Scrub Fields
- **Inspector Inputs:** Height `28px`. Background `#F8FAFC`, border `1px solid #E2E8F0`. Focused state switches to `#FFFFFF` background with a crisp `1.5px` border in `#4F46E5`. Font `Inter`, `12px` body text. Numeric fields allow cursor scrub for width/height/rotation adjustments.

### Floating Canvas Toolstrip
- A detached, horizontally-oriented floating pill-strip that hovers over document pages.
- Styling: `backdrop-filter: blur(16px)`, background `rgba(255, 255, 255, 0.85)`, border `1px solid rgba(226, 232, 240, 0.8)`, shadow Level 2. Contains grouped actions separated by `1px` vertical divider lines (`#E2E8F0`).

### Checkboxes, Radios & Switches
- **Checkboxes:** `14x14px`, `2px` radius. Checked: `#4F46E5` fill with white checkmark.
- **Toggle Switches:** `28px` length, `16px` height. Pill shape. Background `#CBD5E1` (inactive), `#4F46E5` (active). Thumb is a pure white `12px` circle with 2px inset.

### Thumbnail Rail Cards
- Represent page items within the left document sidebar.
- Fixed aspect ratio preview with `1px solid #E2E8F0`. Page index tag centered below (`label-sm`).
- **Active Selection:** 2px border in `#4F46E5`, elevation Level 1 shadow, and a top-right `#4F46E5` badge indicating multi-selection order.
- **Reorder Cue:** A vibrant 2px `#3B82F6` line with circular endpoints appears between cards when dragging pages.

### Annotation & Selection Overlays
- **Bounding Box Handles:** 8-point resizing nodes (`8x8px` white squares with `1.5px solid #4F46E5`).
- **Active Area Highlight:** Transparent indigo tint (`rgba(79, 70, 229, 0.08)`) bound by a 1px dashed `#4F46E5` perimeter line.