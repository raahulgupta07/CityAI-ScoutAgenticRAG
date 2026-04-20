const esbuild = require("esbuild");
const watch = process.argv.includes("--watch");

const opts = {
  entryPoints: ["src/widget.ts"],
  bundle: true,
  minify: !watch,
  outfile: "../backend/static/widget.js",
  format: "iife",
  target: ["es2020"],
  sourcemap: watch,
};

if (watch) {
  esbuild.context(opts).then((ctx) => {
    ctx.watch();
    console.log("Watching...");
  });
} else {
  esbuild.build(opts).then(() => console.log("Built → backend/static/widget.js"));
}
