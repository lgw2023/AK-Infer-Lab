import express from "express";
import { readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer as createViteServer } from "vite";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "..");
const isProduction = process.env.NODE_ENV === "production";
const port = Number(process.env.PORT || 5174);

const app = express();

app.get("/api/flow", async (_req, res, next) => {
  try {
    const payload = await readFile(join(__dirname, "flow-data.json"), "utf8");
    res.type("application/json").send(payload);
  } catch (error) {
    next(error);
  }
});

if (isProduction) {
  app.use(express.static(join(root, "dist")));
  app.get("*", (_req, res) => {
    res.sendFile(join(root, "dist", "index.html"));
  });
} else {
  const vite = await createViteServer({
    root,
    server: { middlewareMode: true },
    appType: "spa"
  });
  app.use(vite.middlewares);
}

app.listen(port, "127.0.0.1", () => {
  console.log(`GLM-5.2 flow site listening on http://127.0.0.1:${port}`);
});
