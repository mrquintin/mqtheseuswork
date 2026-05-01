import { inflateSync } from "node:zlib";
import { expect, test } from "@playwright/test";

const founderEmail = process.env.E2E_FOUNDER_EMAIL ?? process.env.SEED_FOUNDER_A_EMAIL;
const founderPassword =
  process.env.E2E_FOUNDER_PASSWORD ?? process.env.SEED_FOUNDER_A_PASSWORD;
const founderOrg = process.env.E2E_FOUNDER_ORG ?? "theseus-local";

type DecodedPng = {
  width: number;
  height: number;
  rgba: Uint8Array;
};

function paeth(a: number, b: number, c: number) {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  if (pa <= pb && pa <= pc) return a;
  if (pb <= pc) return b;
  return c;
}

function decodePng(buffer: Buffer): DecodedPng {
  const signature = "89504e470d0a1a0a";
  expect(buffer.subarray(0, 8).toString("hex")).toBe(signature);

  let offset = 8;
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  const idat: Buffer[] = [];

  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.subarray(offset + 4, offset + 8).toString("ascii");
    const data = buffer.subarray(offset + 8, offset + 8 + length);
    offset += 12 + length;

    if (type === "IHDR") {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      bitDepth = data[8]!;
      colorType = data[9]!;
    } else if (type === "IDAT") {
      idat.push(data);
    } else if (type === "IEND") {
      break;
    }
  }

  expect(bitDepth).toBe(8);
  expect([2, 6]).toContain(colorType);

  const bytesPerPixel = colorType === 6 ? 4 : 3;
  const rowStride = width * bytesPerPixel;
  const filtered = inflateSync(Buffer.concat(idat));
  const reconstructed = Buffer.alloc(height * rowStride);
  const rgba = new Uint8Array(width * height * 4);
  let src = 0;

  for (let y = 0; y < height; y += 1) {
    const filter = filtered[src++]!;
    const rowStart = y * rowStride;
    const priorRowStart = rowStart - rowStride;

    for (let x = 0; x < rowStride; x += 1) {
      const raw = filtered[src++]!;
      const left = x >= bytesPerPixel ? reconstructed[rowStart + x - bytesPerPixel]! : 0;
      const up = y > 0 ? reconstructed[priorRowStart + x]! : 0;
      const upLeft =
        y > 0 && x >= bytesPerPixel
          ? reconstructed[priorRowStart + x - bytesPerPixel]!
          : 0;
      let predictor = 0;

      if (filter === 1) predictor = left;
      else if (filter === 2) predictor = up;
      else if (filter === 3) predictor = Math.floor((left + up) / 2);
      else if (filter === 4) predictor = paeth(left, up, upLeft);
      else expect(filter).toBe(0);

      reconstructed[rowStart + x] = (raw + predictor) & 0xff;
    }
  }

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const source = y * rowStride + x * bytesPerPixel;
      const target = (y * width + x) * 4;
      rgba[target] = reconstructed[source]!;
      rgba[target + 1] = reconstructed[source + 1]!;
      rgba[target + 2] = reconstructed[source + 2]!;
      rgba[target + 3] = colorType === 6 ? reconstructed[source + 3]! : 255;
    }
  }

  return { width, height, rgba };
}

function pureWhiteSamplePoints(buffer: Buffer) {
  const image = decodePng(buffer);
  const points = [
    ["top-left", 1, 1],
    ["top-center", Math.floor(image.width / 2), 1],
    ["center", Math.floor(image.width / 2), Math.floor(image.height / 2)],
    ["bottom-center", Math.floor(image.width / 2), image.height - 2],
  ] as const;

  return points.flatMap(([label, x, y]) => {
    const idx = (y * image.width + x) * 4;
    const r = image.rgba[idx]!;
    const g = image.rgba[idx + 1]!;
    const b = image.rgba[idx + 2]!;
    const a = image.rgba[idx + 3]!;
    return a > 0 && r >= 248 && g >= 248 && b >= 248 ? [`${label}=${r},${g},${b}`] : [];
  });
}

test("login transition soft-navigates to dashboard without a white frame", async ({
  page,
}) => {
  test.skip(!founderEmail || !founderPassword, "seeded founder credentials are not set");

  const whiteFrames: string[] = [];
  let sampledFrames = 0;

  async function sampleFrame(label: string) {
    const bodyBackground = await page
      .evaluate(() => getComputedStyle(document.body).backgroundColor)
      .catch(() => "");
    if (
      bodyBackground === "rgb(255, 255, 255)" ||
      bodyBackground === "rgba(255, 255, 255, 1)"
    ) {
      whiteFrames.push(`${label}: body=${bodyBackground}`);
    }

    const screenshot = await page
      .screenshot({ animations: "allow", caret: "hide" })
      .catch(() => null);
    if (!screenshot) return;

    sampledFrames += 1;
    const whitePoints = pureWhiteSamplePoints(screenshot);
    if (whitePoints.length > 0) {
      whiteFrames.push(`${label}: ${whitePoints.join("; ")}`);
    }
  }

  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel(/organization/i).fill(founderOrg);
  await page.getByLabel(/email/i).fill(founderEmail!);
  await page.getByLabel(/passphrase/i).fill(founderPassword!);

  await sampleFrame("before-submit");

  const transition = Promise.all([
    page.waitForURL(/\/dashboard(?:\?|$)/, { timeout: 15_000 }),
    page.getByText(/Welcome back/i).waitFor({ state: "visible", timeout: 1_500 }),
  ]);
  await page.getByRole("button", { name: /enter the codex/i }).click();

  const start = Date.now();
  for (let index = 0; index < 18; index += 1) {
    await page.waitForTimeout(75);
    await sampleFrame(`frame-${index}`);
    const path = new URL(page.url()).pathname;
    if (path === "/dashboard" && Date.now() - start > 350) break;
  }

  await transition;
  await sampleFrame("dashboard-settled");

  expect(sampledFrames).toBeGreaterThan(0);
  expect(whiteFrames).toEqual([]);
});
