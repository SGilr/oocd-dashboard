/** A minimal static server for dist/, used by the screenshot and audit scripts. */
import { createServer } from "node:http";
import { existsSync, readFileSync, statSync } from "node:fs";
import { extname, join } from "node:path";

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".xml": "application/xml; charset=utf-8",
  ".csv": "text/csv; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".txt": "text/plain; charset=utf-8",
};

export async function serveDist(port = 4321, root = "dist") {
  const server = createServer((request, response) => {
    let path = join(root, decodeURIComponent((request.url ?? "/").split("?")[0]));
    if (existsSync(path) && statSync(path).isDirectory()) path = join(path, "index.html");
    if (!existsSync(path)) {
      response.writeHead(404);
      return response.end("not found");
    }
    response.writeHead(200, {
      "Content-Type": TYPES[extname(path)] ?? "application/octet-stream",
    });
    response.end(readFileSync(path));
  });
  await new Promise((resolve) => server.listen(port, resolve));
  return { url: `http://127.0.0.1:${port}`, close: () => server.close() };
}
