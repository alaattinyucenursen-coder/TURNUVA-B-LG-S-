// web/ klasörünü uygulamanın içine (www/) kopyalar.
const fs = require("fs");
const path = require("path");

const src = path.join(__dirname, "..", "web");
const dst = path.join(__dirname, "www");
fs.rmSync(dst, { recursive: true, force: true });
fs.cpSync(src, dst, { recursive: true });
fs.cpSync(path.join(__dirname, "runners"), path.join(dst, "runners"), { recursive: true });
console.log("web -> www kopyalandı");
