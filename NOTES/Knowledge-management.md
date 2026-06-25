# Knowledge-Management Research

Source: buildin.ai exports from `~/Downloads/` — 9 ZIPs analyzed 2026-06-25.

## What's been evaluated

### Notes / Markdown editors
- **QOwnNotes, Zettlr, MarkText, Abricotine, Vnote, Joplin, Typora** (from Markdown_Notes_Editors CSV)
- **Wikis tried & rejected**: Smeagol, Tiki.org, Tiddly, Wiki.js, XWiki
- **VSCode/Codium extensions — full eval (2026-04-21)**:
  - **Best**: Markdown Collapsible Sections (`jayblack388.md-collapsible-sections`), Markdown Inline Editor (`CodeSmith.markdown-inline-editor-vscode` — WYSIWYG text editor modifier), Dendron Markdown Shortcuts (`dendron.dendron-markdown-shortcuts` — context menu + shortcuts)
  - **Maybe**: `remcohaszing.markdown-decorations` (real human), `tanishq-chaudhary.its-markdown-studio` (real, has `/` milkdown), `lwxyfer.new-markdown-editor` (hides marks), `jishii1204.markdown-live-editor` (real, has `/`, fold at headings, but no multi-line actions)
  - **No**: `easonruan.markdown-editor-ultra` (constant autosave), `vikgamov.calliope-md` (todolist autocomplete), `imaken.fractal` (theming only, no buttons), `ShinyaIwasaki.markcanvas` (broken), `chrp.markdown-beautiful-editor` (broken TOC), `masaya.wysiwyg-markdown` + `LawrenceRicher.visual-markdown-editor` (both Vditor — SLOP), `adamerose.markdown-wysiwyg` (corrupts todos), `slashmd.slashmd` (deletes checkboxes), `concretio.markdown-for-humans` (no button for todos, no folds), `1AbhishekPandey.live-markdown` (does nothing), lots of sketchy SLOP extensions
  - **Missing**: multi-cursor edits — none found that support it
- **Current**: Notion (reluctantly)

### Task / Project managers
- **Currently using**: Buildin.ai (flagged "Missing task features")
- **Active contender**: Todoist (passes most criteria)
- **Also tried**: TickTick, Amazing Marvin, Asana, ntask, Taiga.io, MLO3, ClickUp, Chaos Control, Colanode, Docmost, AnyType, Affine, Trilium, AppFlowy, LeanTime, OpenProject, Plane, Focalboard, Orgnise, Vikunja, RedMine, Stacks 2
- **MLO3 flagged**: "very high potential investigate on desktop"

### Sync / E2EE
- Syncthing, Tahoe-LAFS, Seafile, NextCloud
- Encryption: encFS, gocryptfs, cryFS

## Hard requirements (from notes)

### Notes
- WYSIWYG, single pane (no split)
- Tables edit cleanly
- Plain text on filesystem (markdown)
- Attachments in `[filename]_assets/`, deleted with note
- Each note + assets = one transferable artifact
- Sync by external tool (Syncthing / NextCloud / Seafile)
- Hierarchical folders, not tag-based
- No vendor lock-in
- Multi-cursor + `/` command palette + fold at headings

### Tasks
- Mobile fast input w/ duplicate detection + project/task decision help
- Nesting ≥ 3 levels
- Customizable recurrence
- CalDAV / Cal.com integration (Actual or Make)
- Group by top category, see completed for day/week

## Cross-cutting constraints
- FOSS / self-host preferred
- Russian localization + works in Russia
- Plain text > proprietary DB
- ADHD-friendly fast capture
- NixOS + KDE + Android stack

## Gaps in research
1. **Obsidian** not in any list
2. **Logseq** not in any list
3. **Silverbullet** not mentioned
4. **TriliumNext** (fork w/ mobile) — Trilium was rejected; fork may address
5. **Task app FOSS self-host**: Vikunja / Plano / OpenProject / Taiga for 3-level nesting + RU-friendly
