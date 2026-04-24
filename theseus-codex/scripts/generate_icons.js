#!/usr/bin/env node
/* eslint-disable no-console */
const fs = require("fs");
const path = require("path");

const ASSETS_DIR = path.resolve(__dirname, "..", "assets");
const SOURCE = path.join(ASSETS_DIR, "icon.png");
const ICNS_OUT = path.join(ASSETS_DIR, "icon.icns");
const ICO_OUT = path.join(ASSETS_DIR, "icon.ico");

function main() {
  if (!fs.existsSync(SOURCE)) {
    console.error(`[icons] Source icon not found: ${SOURCE}`);
    process.exit(1);
  }

  let png2icons;
  try {
    png2icons = require("png2icons");
  } catch (err) {
    console.error("[icons] png2icons is not installed. Run: npm install --save-dev png2icons");
    process.exit(1);
  }

  const input = fs.readFileSync(SOURCE);

  try {
    const icns = png2icons.createICNS(input, png2icons.BILINEAR, 0);
    if (icns) {
      fs.writeFileSync(ICNS_OUT, icns);
      console.log(`[icons] Wrote ${ICNS_OUT}`);
    } else {
      console.warn("[icons] Skipped icon.icns — png2icons returned null on this platform");
    }
  } catch (err) {
    console.warn(`[icons] Skipped icon.icns: ${err.message}`);
  }

  try {
    const ico = png2icons.createICO(input, png2icons.BILINEAR, 0, false);
    if (ico) {
      fs.writeFileSync(ICO_OUT, ico);
      console.log(`[icons] Wrote ${ICO_OUT}`);
    } else {
      console.warn("[icons] Skipped icon.ico — png2icons returned null on this platform");
    }
  } catch (err) {
    console.warn(`[icons] Skipped icon.ico: ${err.message}`);
  }
}

main();
