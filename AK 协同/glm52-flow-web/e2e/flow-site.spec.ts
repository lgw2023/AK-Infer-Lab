import { expect, test } from "@playwright/test";

test("renders the poster-style GLM flow map", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /GLM-5.2 推理计算流与 CPU\/GPU\/NPU 异构协同对比/ })).toBeVisible();
  await expect(page.getByText("标准推理框架 vs 文献中新方案")).toBeVisible();
  await expect(page.getByText("Transformer Blocks（78 Layers）")).toBeVisible();
  await expect(page.getByRole("heading", { name: "标准推理框架（GPU/NPU 主导）" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "NEO 类：CPU 系统算力 Decode Attention 与 KV" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "KTransformers 类：MoE Experts 分层与 CPU/GPU 协同" })).toBeVisible();
  await expect(page.getByText("统一硬件层级（由近到远）")).toBeVisible();
  await expect(page.getByText("图例说明")).toBeVisible();

  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 4
  );
  expect(hasHorizontalOverflow).toBe(false);

  const sheetBox = await page.locator(".infographic-sheet").boundingBox();
  expect(sheetBox).not.toBeNull();
  expect(Math.abs(sheetBox!.width / sheetBox!.height - 16 / 9)).toBeLessThan(0.01);
  expect(sheetBox!.height).toBeLessThanOrEqual(900);

  const topFlowDoesNotOverlapPanels = await page.evaluate(() => {
    const topFlow = document.querySelector(".top-flow");
    const mainPanels = document.querySelector(".main-panels");
    if (!topFlow || !mainPanels) return false;
    const deepestTopFlowBottom = Math.max(
      ...Array.from(topFlow.querySelectorAll("*")).map((element) => element.getBoundingClientRect().bottom)
    );
    return deepestTopFlowBottom <= mainPanels.getBoundingClientRect().top + 1;
  });
  expect(topFlowDoesNotOverlapPanels).toBe(true);

  const overflowingPanels = await page.evaluate(() => {
    return Array.from(document.querySelectorAll(".scenario-panel, .hardware-strip, .compact-table"))
      .map((element) => {
        const rect = element.getBoundingClientRect();
        const childRects = Array.from(element.querySelectorAll("*")).map((child) => child.getBoundingClientRect());
        const deepestChildBottom = childRects.length
          ? Math.max(...childRects.map((childRect) => childRect.bottom))
          : rect.bottom;
        return {
          className: element.className,
          overflowY: deepestChildBottom - rect.bottom
        };
      })
      .filter((entry) => entry.overflowY > 1);
  });
  expect(overflowingPanels).toEqual([]);

  await page.screenshot({ path: "test-results/glm52-flow-poster-desktop.png", fullPage: true });
});

test("stacks the poster cleanly on mobile width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /GLM-5.2 推理计算流/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "标准推理框架（GPU/NPU 主导）" })).toBeVisible();
  await expect(page.getByText("统一硬件层级（由近到远）")).toBeVisible();

  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 4
  );
  expect(hasHorizontalOverflow).toBe(false);

  await page.screenshot({ path: "test-results/glm52-flow-poster-mobile.png", fullPage: true });
});
