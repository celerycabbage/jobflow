import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const manifest = JSON.parse(await readFile(new URL("./manifest.json", import.meta.url), "utf8"));

test("uses a module MV3 service worker and explicit permissions", () => {
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.background, { service_worker: "background.js", type: "module" });
  assert.deepEqual(manifest.permissions, ["activeTab", "scripting", "storage"]);
});

test("only grants persistent host access to local JobFlow services", () => {
  assert.deepEqual(manifest.host_permissions, [
    "http://localhost:5173/*",
    "http://localhost:8000/*",
  ]);
});
