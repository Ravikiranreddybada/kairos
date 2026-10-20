---
name: Kairos
description: A planning copilot set as a carbon-copy requisition pad. Answer on the top sheet, evidence on the canary, audit on the pink.
colors:
  carbon-ink: "#23306b"
  carbon-ink-faded: "#48538a"
  errata-red: "#b3261e"
  ledger-green: "#3c6650"
  ledger-rule: "#9cb8a6"
  ledger-rule-strong: "#6f9a82"
  canary-copy: "#f4e38a"
  canary-edge: "#efd969"
  canary-caption: "#5b4c0b"
  pink-copy: "#f1c9d2"
  pink-edge: "#e9b5c1"
  pink-caption: "#6a2a3b"
  top-sheet: "#f7f7f4"
  desk: "#e4e5e1"
  desk-shadowed: "#d9dbd6"
  type-black: "#1f2227"
  type-grey: "#4a4e57"
  carbon-ground: "#0c1022"
  carbon-ground-2: "#121733"
  carbon-sheet: "#171d3b"
  transferred-ink: "#c3cdff"
  transferred-ink-faded: "#98a3d9"
  carbon-canary: "#36311a"
  carbon-pink: "#3b2231"
  carbon-rule: "#2e4a3d"
  carbon-rule-ink: "#8fbfa5"
  carbon-type: "#e6e8ef"
  carbon-errata: "#ff8f84"
typography:
  display:
    fontFamily: "Archivo Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 800
    lineHeight: "28px"
    letterSpacing: "-0.02em"
    fontVariation: "'wdth' 125"
  stamp:
    fontFamily: "Archivo Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "19px"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "0.08em"
    fontVariation: "'wdth' 112"
  title:
    fontFamily: "Archivo Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "14.5px"
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontFamily: "Archivo Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  answer:
    fontFamily: "Archivo Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "15.5px"
    fontWeight: 400
    lineHeight: "28px"
  figure-in-prose:
    fontFamily: "Archivo Variable, ui-sans-serif, system-ui, sans-serif"
    fontWeight: 600
    fontFeature: "'tnum' 1"
  label:
    fontFamily: "Archivo Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 560
    lineHeight: "14px"
    letterSpacing: "0.02em"
    fontVariation: "'wdth' 78"
  data:
    fontFamily: "Fragment Mono, ui-monospace, SFMono-Regular, monospace"
    fontSize: "13.5px"
    fontWeight: 400
    letterSpacing: "-0.01em"
    fontFeature: "'tnum' 1"
  data-large:
    fontFamily: "Fragment Mono, ui-monospace, SFMono-Regular, monospace"
    fontSize: "22px"
    fontWeight: 400
    lineHeight: "28px"
    fontFeature: "'tnum' 1"
rounded:
  none: "0px"
spacing:
  hair: "2px"
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  xxl: "32px"
  rule-line: "28px"
  masthead: "56px"
  pad-column: "248px"
  copies-column: "440px"
components:
  button-primary:
    backgroundColor: "{colors.carbon-ink}"
    textColor: "{colors.top-sheet}"
    rounded: "{rounded.none}"
    padding: "0 14px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.carbon-ink-faded}"
    textColor: "{colors.top-sheet}"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.carbon-ink}"
    rounded: "{rounded.none}"
    padding: "0 14px"
    height: "36px"
  button-disabled:
    backgroundColor: "transparent"
    textColor: "{colors.type-grey}"
  form-cell:
    backgroundColor: "{colors.top-sheet}"
    textColor: "{colors.carbon-ink}"
    typography: "{typography.data}"
    rounded: "{rounded.none}"
    padding: "6px 10px 8px"
  copy-tab-evidence:
    backgroundColor: "{colors.canary-copy}"
    textColor: "{colors.type-black}"
    rounded: "{rounded.none}"
    padding: "0 16px"
    height: "36px"
  copy-tab-evidence-folded:
    backgroundColor: "{colors.canary-edge}"
    textColor: "{colors.type-grey}"
    height: "30px"
  copy-tab-audit:
    backgroundColor: "{colors.pink-copy}"
    textColor: "{colors.type-black}"
    rounded: "{rounded.none}"
    padding: "0 16px"
    height: "36px"
  copy-tab-audit-folded:
    backgroundColor: "{colors.pink-edge}"
    textColor: "{colors.type-grey}"
    height: "30px"
  stamp-verified:
    backgroundColor: "transparent"
    textColor: "{colors.carbon-ink}"
    typography: "{typography.stamp}"
    rounded: "{rounded.none}"
    padding: "6px 12px 7px"
  stamp-errata:
    backgroundColor: "transparent"
    textColor: "{colors.errata-red}"
    typography: "{typography.stamp}"
  stamp-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.carbon-ink-faded}"
  pad-item:
    backgroundColor: "{colors.desk-shadowed}"
    textColor: "{colors.type-black}"
    padding: "12px 16px"
  pad-item-open:
    backgroundColor: "{colors.top-sheet}"
    textColor: "{colors.type-black}"
---

# Design System: Kairos

## Overview

**Creative North Star: "The Carbon-Copy Requisition"**

Every question is a requisition torn from a multi-part form pad. The answer is typed onto the white top sheet in carbon-blue ink; the canary copy under it holds the evidence (the tool data and charts behind each figure); the pink copy holds the audit (tier, grounding, tokens, cost, trace id, champion run). The pad of past requisitions sits on the desk to the left. Nothing floats, nothing glows, nothing is rounded. Structure comes from preprinted ledger-green rules and captions, the way a form printer would set them, and everything the system itself wrote is in one ink.

Density is office-form dense: small condensed captions, tight 1px rules, tabular figures, a 28px ruled answer line. It refuses the category default for AI tools: no dark dashboard, no chat bubbles, no sidebar of cards, no blue-purple accent gradient. Dark mode is not an inverted light mode; it is the carbon sheet itself, a blue-black ground with pale transferred ink.

Motion is mechanical. Things land, they do not ease: routing-slip lines and the final stamp arrive in a 2-frame, 90ms step. A pending mark blinks in two steps. All of it switches off under reduced motion.

**Key Characteristics:**
- Three sheet colors (white, canary, pink) carry three jobs (answer, evidence, audit).
- One ink (carbon blue) for everything the system filled in; preprinted green for everything the form "came with".
- Square corners and 1px rules everywhere; depth only from stacked paper edges.
- Archivo for the form, Fragment Mono for filled values and identifiers.
- One stamp per answer states the verdict: VERIFIED, UNVERIFIED, REFUSED, DEGRADED, PARTIAL, NOT FILED.

## Colors

Paper, preprinted green, and one fill ink, with errata red held back for failure.

### Primary
- **Carbon Ink** (carbon-ink): every value the system wrote: answer text, field values, tool-latency bars, forecast line and band, the VERIFIED stamp, primary buttons, focus ring, caret. In dark mode it becomes **Transferred Ink** (transferred-ink).
- **Faded Carbon** (carbon-ink-faded): hover on the primary button, citation text, the quiet stamp (DEGRADED, PARTIAL, ROUTING).

### Secondary
- **Ledger Green** (ledger-green): preprinted captions and form labels; the "printer's" voice, never the system's. Dark: carbon-rule-ink.
- **Ledger Rule** (ledger-rule) and **Ledger Rule Strong** (ledger-rule-strong): 1px cell dividers and ruled answer lines (light rule); sheet borders, section breaks, column borders and stacked-copy edges (strong rule).

### Tertiary
- **Canary Copy** (canary-copy) with **Canary Edge** (canary-edge) and **Canary Caption** (canary-caption): the evidence sheet, its internal rules and folded tab, and its labels.
- **Pink Copy** (pink-copy) with **Pink Edge** (pink-edge) and **Pink Caption** (pink-caption): the audit sheet, its rules and folded tab, and its labels.
- **Errata Red** (errata-red): failure only. UNVERIFIED / REFUSED / NOT FILED stamps, failed tool calls, untraced figures (with a 10% errata wash and a wavy underline), "API unreachable". Dark: carbon-errata.

### Neutral
- **Top Sheet** (top-sheet): the open requisition, masthead, and the open item in the pad.
- **Desk** (desk) and **Desk Shadowed** (desk-shadowed): the page ground; the pad column and copies column sit on the shadowed desk.
- **Type Black** (type-black): preprinted headings, question and pad item text. **Type Grey** (type-grey): secondary text, timestamps, disabled controls, placeholders.
- **Carbon Ground / Carbon Sheet** (carbon-ground, carbon-ground-2, carbon-sheet, carbon-canary, carbon-pink, carbon-rule, carbon-type): the dark theme set. Each light role has a dark twin; the role map stays the same.

### Named Rules
**The One Ink Rule.** Anything the system filled in is carbon ink. Anything the form came with is ledger green or type black. Never fill a value in green or print a caption in ink.

**The Three Copies Rule.** White is the answer, canary is evidence, pink is audit. Do not use canary or pink as decoration or as a highlight on the top sheet.

**The Errata Reserve Rule.** Errata red means a failure the planner must see. It is never a brand accent, a hover color, or emphasis.

## Typography

**Display Font:** Archivo Variable (with ui-sans-serif, system-ui)
**Body Font:** Archivo Variable
**Label/Mono Font:** Fragment Mono (with ui-monospace, SFMono-Regular) for filled values

**Character:** Archivo's width axis does the work a form printer would: condensed (78%) for captions, normal for prose, expanded (112-125%) for the wordmark and stamp. Fragment Mono is the typewriter that filled the form in.

### Hierarchy
- **Display** (800, 22px/28px, width 125%, -0.02em): the "Requisition" form title and the Kairos wordmark (19px in the masthead).
- **Stamp** (800, 19px, width 112%, +0.08em, uppercase words): the verdict word inside the stamp only.
- **Title** (600, 13-14.5px): evidence block headings, tool log heading, routing-slip node names, button labels.
- **Body** (400, 15px/1.5): base text. Question field 16px; answer 15.5px on the 28px rule, max 72ch. Secondary text 12-13.5px.
- **Label** (560, 11px/14px, width 78%, +0.02em, sentence case): preprinted captions in the top-left of each field and above each section ("No.", "Date", "Question", "Routing slip", "Answer").
- **Data** (Fragment Mono 400, 11.5-13.5px, tabular, -0.01em): identifiers (stores, SKUs, run ids, trace ids), field values, table values, timestamps, latencies. Large data (20-22px/28px) for the headline figures of an evidence block.

### Named Rules
**The Typewriter Rule.** Fragment Mono is for filled values and identifiers only: field cells, table columns, IDs, latencies. Never set prose or headings in mono.

**The Figures-in-Prose Rule.** Numbers inside answer sentences stay in Archivo at weight 600 with tabular figures. Mono digits inside running text read as spaced-out digits. Store and SKU identifiers inside prose stay in Fragment Mono at 0.92em.

**The Printer's Caption Rule.** A caption labels a field on the form, in condensed sentence case. It is never an uppercase eyebrow over a heading and never decoration.

## Layout

A three-column desk on wide screens: the pad (248px) on the left on the shadowed desk, the open requisition in the centre on the plain desk, and the copy stack (440px) on the right on the shadowed desk, each column scrolling on its own under a 56px masthead. At 1024-1279px the pad stays left and the copies drop under the form. Under 1024px the pad folds into a "Pad" disclosure above the form with a separate New button, and everything stacks in one column with a 16px gutter (24px from 640px, 32px from 1024px).

The form header is a ruled grid of cells (title cell wider, then No., Date, Subject, Model tier); it falls to two columns on phones. Inside sheets the rhythm is 16px horizontal padding, 8-12px vertical between section breaks, and 28px ruled lines for question and answer text. Routing-slip rows use a fixed 28px / 64px / fluid grid (line number, node name, text). Evidence fields run in a 2-up grid, 3-up from 640px.

### Named Rules
**The Ledger Grid Rule.** Structure is drawn with visible 1px rules, not with whitespace cards. Fields share borders; sections are separated by a strong rule across the full sheet width.

## Elevation & Depth

The system is flat. No box-shadows exist anywhere. Depth is conveyed only by paper: the open requisition shows a 6px canary edge and a 12px pink edge offset down and right beneath it (the stacked copies of the pad), and the folded copy tab sits 6px lower and in a darker edge tint than the open one. Columns are separated by tone (desk vs shadowed desk) and a strong rule, never by lift.

### Named Rules
**The Paper-Only Depth Rule.** The only depth device is a hard-edged, square paper offset behind the open requisition. No blur, no soft shadow, no hover lift.

## Shapes

Square corners everywhere (0px). Borders are 1px ledger rules; the stamp alone uses a 2px border with a 1px outline 2px outside it and sits rotated -3deg. Bars (tool latency, safety stock, risk) are flat 5-6px ink strips with no track behind them; their length is the value. Chart markers are squares, not circles.

## Components

### Buttons
Typewritten and square: they read as boxes printed on the form.
- **Shape:** square (0px), 36px tall, 14px side padding, 1px border, 600 weight at 14px, icon (Phosphor, 15-16px) before or after the label.
- **Primary:** solid carbon ink with top-sheet text ("New requisition", "Submit"). In dark mode it becomes an ink-band fill (16% ink) with transferred-ink text and border: never a pale filled slab.
- **Hover / Focus:** hover shifts to faded carbon (150ms ease-out on color only); active presses down 1px; focus is a 2px carbon-ink outline offset 2px.
- **Quiet:** transparent with a strong-rule border and carbon-ink text ("Follow-up requisition", "Start a new pad"); hover adds a 12% ink wash and an ink border.
- **Disabled:** transparent, type-grey text, strong-rule border, not-allowed cursor.

### Form Cells
- **Style:** a caption printed top-left, the filled value under it in Fragment Mono carbon ink, padding 6px 10px 8px, a 1px rule on the right (none on the last cell). Values truncate; they do not wrap.

### Inputs / Fields
- **Style:** the question textarea has no box. It is ruled paper: transparent background, 28px rule lines, carbon-ink text and caret, 16px, resizable vertically. Placeholder in type grey.
- **Focus:** the global 2px carbon-ink outline. Enter submits; Shift+Enter adds a line; key hints are 11px mono boxes with a 1px current-color border.

### Navigation
- **The pad:** a numbered list of filed requisitions on the shadowed desk. Each row: mono "No. 0005" in ink and a mono clock time, the question in two lines, the subject identifiers, and a status word (ink for Verified, errata for failures, grey and blinking while routing). The open row turns top-sheet white; others take an ink wash on hover. A primary "New requisition" button heads the column; the session id and "Start a new pad" sit at its foot.
- **Copy tabs:** two square tabs, "Evidence copy" (canary) and "Audit copy" (pink). The open tab is 36px and in the sheet color; the folded tab is 30px, in the darker edge tint, with grey text. Arrow keys switch tabs.
- **Masthead:** 56px, top-sheet white, wordmark, "Planning copilot", the champion run id and gate count in mono, and a square 36px theme toggle.

### The Stamp (signature)
One per filed answer, lower right of the answer section. A transparent box in the verdict's color: 2px border plus 1px outline at 2px, rotated -3deg; the verdict word (Stamp type), a condensed 11px note ("3 of 3 figures traced to tools"), and the date in mono. Ink for VERIFIED, errata for UNVERIFIED / REFUSED / NOT FILED, faded ink for DEGRADED / PARTIAL. It lands with a 2-step 90ms scale from 1.08, no easing.

### The Routing Slip (signature)
A numbered, ruled list inside the requisition. Each graph node (Guard, Route, Cache, Model, Tools, Verify, File) stamps one line as its stream event arrives (2-step 90ms land). Tool lines list each call in mono with a 5px ink bar whose length is the call's real latency relative to the slowest call, and the latency at the right. While routing, a grey blinking "Working" line holds the next number.

### Evidence and Audit Copies
- **Evidence:** per tool call, a block with a title, its inputs as grey caption + mono ink value pairs, then fields (large mono headline figures), flat bar tables with right-aligned mono columns, and the forecast fan (ink line, 16% ink band for the 80% interval, canary-edge gridlines, square hover marker, a hidden data table for screen readers). It ends with "Re-read from <endpoint>" in 11px mono.
- **Audit:** a definition list on pink: pink-caption labels in a 132px column, mono ink values, pink-edge rules, then a tool log with latency bars.
- **Loading:** flat canary-edge blocks at 60% opacity, no shimmer.

## Do's and Don'ts

### Do:
- **Do** put every system-written value in carbon ink (#23306b light, #c3cdff dark) and every preprinted caption in ledger green.
- **Do** keep answer, evidence and audit on their own sheets: top sheet, canary (#f4e38a), pink (#f1c9d2).
- **Do** draw structure with 1px ledger rules and shared borders; separate sections with the strong rule (#6f9a82).
- **Do** set identifiers and field or table values in Fragment Mono with tabular figures; set figures inside answer prose in Archivo 600 tabular.
- **Do** end every filed answer with exactly one stamp whose word and color state the verdict.
- **Do** size bars by the real value (latency, safety stock, risk) with no track behind them.
- **Do** make motion land in 2 steps at 90ms with no easing, and disable it under reduced motion.

### Don't:
- **Don't** round any corner, or add soft shadows, blur, glow or hover lift.
- **Don't** use chat bubbles, card grids, a dark dashboard default, or blue-purple gradients (PRODUCT.md: the UI must not look AI-generated).
- **Don't** use canary or pink as highlight colors on the top sheet, or errata red for anything but a failure.
- **Don't** set prose or headings in Fragment Mono, or figures inside answer sentences in mono.
- **Don't** turn captions into uppercase eyebrows or labels over headings; a caption names a field.
- **Don't** fill the primary button with pale ink in dark mode; there it is an ink-band fill with an ink border.
- **Don't** show more than one stamp per requisition, or a stamp before the result is in.
