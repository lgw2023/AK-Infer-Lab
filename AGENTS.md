# Repository Guidelines

## Project Structure & Module Organization

This repository root is a lightweight documentation hub. The main planning materials now live in `工作记录与进度笔记本/`, with historical inputs under `工作记录与进度笔记本/00_原始材料/`. `AK 协同` is a symlink to working project materials: research notes, references, diagrams, slide assets, and web prototypes.

Key linked subprojects:

- `AK 协同/glm52-flow-web/`: GLM-5.2 inference flow app; source in `src/`, data in `server/`, browser tests in `e2e/`.
- `AK 协同/hardware-map-web/`: hardware topology app; source in `src/`, tests in `src/*.test.ts` and `e2e/`.
- `AK 协同/references/`, `AK 协同/diagrams/`, `AK 协同/技术点 PPT/`: evidence, visuals, and presentation artifacts.

## Build, Test, and Development Commands

Run app commands from the relevant subproject directory.

```bash
cd "AK 协同/glm52-flow-web"
pnpm install
pnpm dev        # local server on 127.0.0.1:5174
pnpm test       # Vitest data/unit checks
pnpm build      # TypeScript build plus Vite bundle
pnpm test:e2e   # Playwright browser checks
pnpm check      # test plus build
```

```bash
cd "AK 协同/hardware-map-web"
pnpm install
pnpm dev        # Vite server on 127.0.0.1:5173
pnpm test
pnpm build
pnpm test:e2e
pnpm check
```

Use `rg "keyword" .` from the root for fast research and document lookup.

## Coding Style & Naming Conventions

Use TypeScript, React function components, 2-space indentation, semicolons, and existing local formatting. Keep components in PascalCase, data/types as descriptive camelCase exports, Vitest files as `*.test.ts`, and Playwright files as `*.spec.ts`. For Markdown research files, keep descriptive titles and source-backed claims.

## Testing Guidelines

Add or update Vitest coverage when changing structured data, route maps, or schema-like exports. Add Playwright coverage for layout, search/filter behavior, screenshots, or responsive behavior. Before handoff, run `pnpm check`; run `pnpm test:e2e` when UI layout or interaction changed.

## Commit & Pull Request Guidelines

This root is not currently a Git repository; the linked project history uses concise Conventional Commit style such as `docs:` and `chore:`. Continue that pattern: `docs: update AK inference plan` or `fix: correct hardware map evidence`.

PRs should include a short scope summary, touched folders, verification commands run, and screenshots or exported PDFs for visual changes. For research-doc edits, cite the local reference file or external source that supports the claim.

## Agent-Specific Instructions

Keep edits surgical. Do not rewrite neighboring research notes, generated decks, lockfiles, or reference assets unless required. The linked `AK 协同` worktree may contain unrelated local changes; preserve them.

This local machine is an external development machine, not the Ascend server. Any work that depends on the real Ascend environment, NPU runtime, server paths, deployment, or server-side validation must be handed off for execution on the Ascend server.

Use `通信模块/docs/developer-to-server.md` as the communication document from this development machine to the server. Every time a server task is handed off, clear the old historical contents of that file first, then write only the current server task, including all context, commands, paths, constraints, expected outputs, and reporting requirements the server operator needs.

At the start and end of every task round, refresh the corresponding content under `工作记录与进度笔记本/`. Keep the notebook current with the task status, evidence, results, problems, and next actions.
