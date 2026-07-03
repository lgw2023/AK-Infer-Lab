import { expect, test } from "@playwright/test";

test("NEO search highlights the calibrated GPU, PCIe, CPU and DDR route", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("搜索论文、硬件或层级").fill("NEO");

  await expect(page.getByTestId("active-work-title")).toContainText("NEO");
  const hardware = page.getByTestId("highlighted-hardware");
  await expect(hardware).toContainText("GPU/HBM");
  await expect(hardware).toContainText("PCIe/DMA");
  await expect(hardware).toContainText("CPU cores");
  await expect(hardware).toContainText("CPU DDR");
  await expect(hardware).toContainText("NUMA boundary");
  await expect(page.getByTestId("primary-path-detail")).toContainText("load-aware scheduler");
  await expect(page.getByTestId("primary-path-detail")).not.toContainText("NUMA");
  await expect(page.getByTestId("topology-summary")).toContainText("NUMA 不是原文核心机制");
  await expect(page.getByTestId("board-map")).toBeVisible();
});

test("server board topology cards do not overlap", async ({ page }) => {
  await page.goto("/");

  const boxes = await page.locator(".react-flow__node.board-node").evaluateAll((nodes) =>
    nodes.map((node) => {
      const rect = node.getBoundingClientRect();
      return {
        id: node.getAttribute("data-id") ?? "",
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
      };
    }),
  );

  const overlaps: string[] = [];
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      const first = boxes[i];
      const second = boxes[j];
      const xOverlap = Math.min(first.right, second.right) - Math.max(first.left, second.left);
      const yOverlap = Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top);
      if (xOverlap > 1 && yOverlap > 1) {
        overlaps.push(`${first.id}/${second.id}`);
      }
    }
  }

  expect(overlaps).toEqual([]);
});

test("server board overlays do not overlap hardware cards", async ({ page }) => {
  await page.goto("/");

  await expect
    .poll(async () => {
      return page.evaluate(() => {
        const cardRects = Array.from(document.querySelectorAll(".react-flow__node.board-node")).map((node) => {
          const rect = node.getBoundingClientRect();
          return {
            id: node.getAttribute("data-id") ?? "",
            left: rect.left,
            top: rect.top,
            right: rect.right,
            bottom: rect.bottom,
          };
        });
        const labelRects = Array.from(document.querySelectorAll(".react-flow__edge-text, .board-edge-label, .react-flow__controls, .react-flow__minimap")).map((label) => {
          const rect = label.getBoundingClientRect();
          return {
            id: label.textContent?.trim() ?? "",
            left: rect.left,
            top: rect.top,
            right: rect.right,
            bottom: rect.bottom,
          };
        });

        const collisions: string[] = [];
        for (const label of labelRects) {
          for (const card of cardRects) {
            const xOverlap = Math.min(label.right, card.right) - Math.max(label.left, card.left);
            const yOverlap = Math.min(label.bottom, card.bottom) - Math.max(label.top, card.top);
            if (xOverlap > 1 && yOverlap > 1) {
              collisions.push(`${label.id}/${card.id}`);
            }
          }
        }
        return collisions;
      });
    })
    .toEqual([]);
});

test("server board keeps auxiliary labels smaller than hardware card labels", async ({ page }) => {
  await page.goto("/");

  const fontSizes = await page.evaluate(() => {
    const readPx = (selector: string) => {
      const element = document.querySelector(selector);
      if (!element) return 0;
      return Number.parseFloat(window.getComputedStyle(element).fontSize);
    };

    return {
      eyebrow: readPx(".board-panel > .panel-title-row .eyebrow"),
      title: readPx(".board-panel > .panel-title-row h2"),
      legend: readPx(".legend-dot"),
      edgeLabel: readPx(".edge-label-chip"),
      nodeTitle: readPx(".board-node-inner strong"),
    };
  });

  expect(fontSizes.eyebrow).toBeLessThanOrEqual(14);
  expect(fontSizes.title).toBeLessThanOrEqual(24);
  expect(fontSizes.legend).toBeLessThanOrEqual(14);
  expect(fontSizes.edgeLabel).toBeLessThanOrEqual(14);
  expect(fontSizes.nodeTitle).toBeGreaterThanOrEqual(26);
});

test("Tutti search highlights SSD and GPU direct object I/O without CPU data path wording", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("搜索论文、硬件或层级").fill("Tutti");

  await expect(page.getByTestId("active-work-title")).toContainText("Tutti");
  const hardware = page.getByTestId("highlighted-hardware");
  await expect(hardware).toContainText("NVMe/SSD");
  await expect(hardware).toContainText("GPU direct/object I/O");
  await expect(hardware).toContainText("GPU io_uring");
  await expect(hardware).toContainText("HBM");
  await expect(page.getByTestId("topology-summary")).toContainText("CPU 退出每次 I/O critical path");
  await expect(page.getByTestId("primary-path-detail")).toContainText("P2P");
});

test("FluxMoE search shows the corrected evidence and separate MoE mechanism", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("搜索论文、硬件或层级").fill("FluxMoE");

  await expect(page.getByTestId("active-work-title")).toContainText("FluxMoE");
  await expect(page.getByTestId("topology-summary")).toContainText("expert weights");
  await expect(page.getByLabel("详情").getByText("references/papers/FluxMoE__arxiv-2604.02715v2.pdf")).toBeVisible();
  await expect(page.getByTestId("primary-path-detail")).toContainText("PagedTensor");
});

test("Paper-calibrated view renders only the selected work markdown section", async ({ page }) => {
  await page.goto("/");

  const notes = page.getByTestId("paper-notes-markdown");
  await expect(notes).toBeVisible();
  await expect(notes).toContainText("NEO 原文精读小节");
  await expect(notes).toContainText("1. NEO");
  await expect(notes).toContainText("NEO 不是普通的 KV cache swap");
  await expect(notes).not.toContainText("Tutti 把 SSD-backed KV cache");
  await expect(notes).not.toContainText("BurstGPT");
  await expect(notes.getByRole("table").first()).toBeVisible();
});

test("Paper-calibrated view switches markdown section with the active work", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("搜索论文、硬件或层级").fill("Tutti");

  const notes = page.getByTestId("paper-notes-markdown");
  await expect(notes).toContainText("Tutti 原文精读小节");
  await expect(notes).toContainText("2. Tutti");
  await expect(notes).toContainText("Tutti 把 SSD-backed KV cache");
  await expect(notes).not.toContainText("NEO 不是普通的 KV cache swap");
});

test("Paper-calibrated view does not borrow global notes for works without a section", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("搜索论文、硬件或层级").fill("Dynamo");

  const notes = page.getByTestId("paper-notes-markdown");
  await expect(notes).toContainText("NVIDIA Dynamo KVBM / LMCache / FlexKV 原文精读小节");
  await expect(notes).toContainText("这份精读笔记里还没有该工作的独立小节");
  await expect(notes).not.toContainText("本轮精读状态");
  await expect(notes).not.toContainText("1. NEO");
});

test("main views render without losing the selected work context", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("搜索论文、硬件或层级").fill("Mooncake");
  await expect(page.getByTestId("active-work-title")).toContainText("Mooncake");

  await page.getByRole("button", { name: "L0-L11 层级矩阵" }).click();
  await expect(page.getByRole("heading", { name: "L0-L11 硬件层级地图" })).toBeVisible();

  await page.getByRole("button", { name: "状态对象流" }).click();
  await expect(page.getByRole("heading", { name: "KV / Expert / Prefix 状态对象流" })).toBeVisible();

  await page.getByRole("button", { name: "A+K 迁移与仿真" }).click();
  await expect(page.getByTestId("ak-active-work")).toContainText("Mooncake");
});

test("GLM-5.2 view renders a single-page infographic flow comparison", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "GLM-5.2 推理流" }).click();

  await expect(page.getByTestId("glm-infographic")).toBeVisible();
  await expect(page.getByRole("heading", { name: "GLM-5.2 推理计算流与 CPU/GPU/NPU 异构协同对比" })).toBeVisible();
  await expect(page.getByTestId("glm-model-pipeline")).toContainText("Prompt / Tokens");
  await expect(page.getByTestId("glm-model-pipeline")).toContainText("Transformer Blocks (78 Layers)");
  await expect(page.getByTestId("glm-model-pipeline")).toContainText("MLP / MoE");
  await expect(page.getByTestId("glm-model-pipeline")).toContainText("Sampling / Decode");
  await expect(page.getByTestId("glm-standard-column")).toContainText("标准推理框架");
  await expect(page.getByTestId("glm-neo-column")).toContainText("NEO 类");
  await expect(page.getByTestId("glm-ktransformers-column")).toContainText("KTransformers 类");
  await expect(page.getByTestId("glm-hardware-tier")).toContainText("GPU/NPU Compute");
  await expect(page.getByTestId("glm-hardware-tier")).toContainText("HBM / NPU Memory");
  await expect(page.getByTestId("glm-hardware-tier")).toContainText("CPU DDR");
  await expect(page.getByTestId("glm-hardware-tier")).toContainText("SSD / NVMe");
  await expect(page.getByTestId("glm-comparison-table")).toContainText("主优化对象");
  await expect(page.getByTestId("glm-legend")).toContainText("实线箭头：主数据流");
  await expect(page.getByTestId("glm-legend")).toContainText("虚线箭头：控制流 / 调度 / 预取");
});
