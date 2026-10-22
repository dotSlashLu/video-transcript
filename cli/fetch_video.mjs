#!/usr/bin/env node
// fetch_video.mjs — 用 CDP(用户已登录的 Chrome) 打开网页，取出主视频直链 + 元信息
// 用法: node fetch_video.mjs <url> [--wait 10000]
// 输出: {"pageUrl","title","video","duration","chapters":[{text,time}],"height","streams":[...]}
//
// 通用策略（按优先级）:
//   1) 站点自定义解析器（小红书: __INITIAL_STATE__ 里有全部分辨率 + 章节）
//   2) 通用: 取 <video>.currentSrc/src（最高分辨率）
//   3) 兜底: 页面 HTML 里的 .mp4 链接
const PROXY = "http://localhost:3456";

const argv = process.argv.slice(2);
const url = argv.find(a => !a.startsWith("--"));
const wi = argv.indexOf("--wait");
const waitMs = wi >= 0 ? parseInt(argv[wi + 1] || "10000") : 10000;
if (!url) { console.error("usage: node fetch_video.mjs <url>"); process.exit(2); }
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function ev(target, expr) {
  const r = await fetch(`${PROXY}/eval?target=${target}`, { method: "POST", body: expr });
  const t = await r.text();
  try { return JSON.parse(t).value; } catch { return null; }
}

// 小红书专用提取器
const XHS = `(() => {
  try {
    const s = window.__INITIAL_STATE__;
    if (!s || !s.note) return null;
    let note = null;
    if (s.note.noteDetailMap) {
      const keys = Object.keys(s.note.noteDetailMap);
      for (const k of keys) { const n = s.note.noteDetailMap[k]?.note; if (n && n.video) { note = n; break; } }
      if (!note && keys.length) note = s.note.noteDetailMap[keys[0]]?.note;
    }
    if (!note) note = s.note.noteDetail?.note || s.note;
    if (!note || !note.video) return null;
    const v = note.video;
    const streams = (v.media && v.media.stream) || {};
    const cands = [];
    for (const codec of Object.keys(streams)) {
      for (const x of (streams[codec] || [])) {
        if (x && x.masterUrl) cands.push({
          codec, w: x.width || 0, h: x.height || 0, br: x.videoBitrate || 0,
          size: x.size || 0, q: x.qualityType || "", url: x.masterUrl
        });
      }
    }
    return JSON.stringify({
      title: note.title || document.title,
      duration: (v.capa && v.capa.duration) || null,
      chapters: (v.consumer && v.consumer.chapters) || [],
      desc: note.desc || "",
      streams: cands
    });
  } catch (e) { return "ERR:" + e.message; }
})()`;

const GENERIC = `(() => {
  const vs = [...document.querySelectorAll('video')];
  const cands = vs.map(v => ({src: v.currentSrc || v.src, dur: isFinite(v.duration)?v.duration:null,
                              w: v.videoWidth, h: v.videoHeight, readyState: v.readyState}))
                  .filter(v => v.src && !v.src.startsWith('blob:'));
  return JSON.stringify({
    pageUrl: location.href,
    title: (document.querySelector('meta[property="og:title"]')?.content) || document.title,
    videos: cands
  });
})()`;

const res = await fetch(`${PROXY}/new?url=${encodeURIComponent(url)}`).then(r => r.json()).catch(() => ({}));
const target = res.targetId;
if (!target) { console.error("无法创建 tab:", JSON.stringify(res)); process.exit(1); }

let result = null;
const deadline = Date.now() + waitMs;
while (Date.now() < deadline) {
  await sleep(800);
  const isXhs = /xiaohongshu\.com/.test(url) || /xhslink\.cn/.test(url);
  if (isXhs) {
    const raw = await ev(target, XHS);
    if (raw && !String(raw).startsWith("ERR:")) {
      const info = JSON.parse(raw);
      if (info.streams && info.streams.length) {
        info.streams.sort((a, b) => (b.h * 10000 + b.br) - (a.h * 10000 + a.br));
        const best = info.streams[0];
        const page = await ev(target, "location.href");
        result = {
          pageUrl: page || url, title: info.title, desc: info.desc,
          video: best.url, duration: info.duration, chapters: info.chapters,
          width: best.w, height: best.h, codec: best.codec,
          streams: info.streams.map(s => ({ codec: s.codec, w: s.w, h: s.h, br: s.br, size: s.size }))
        };
        break;
      }
    }
  }
  const raw = await ev(target, GENERIC);
  if (raw) {
    try {
      const info = JSON.parse(raw);
      if (info.videos && info.videos.length) {
        info.videos.sort((a, b) => (b.w * b.h) - (a.w * a.h));
        const v = info.videos[0];
        if (v.w > 0 || isXhs === false) {
          result = { pageUrl: info.pageUrl, title: info.title, video: v.src, duration: v.dur,
                     width: v.w, height: v.h, chapters: [] };
          if (v.w > 0) break;    // 已有分辨率信息，可提前结束
        }
      }
    } catch {}
  }
}

if (!result) {
  const raw = await ev(target, `(() => {
    const m = document.documentElement.innerHTML.match(/https?:\\/\\/[^"'\\s]+?\\.mp4[^"'\\s]*/g) || [];
    return JSON.stringify({pageUrl: location.href, title: document.title, mp4: [...new Set(m)].slice(0,5)});
  })()`);
  console.error("未定位到 video 元素，页面内 mp4:", raw);
}

await fetch(`${PROXY}/close?target=${target}`).catch(() => {});
if (!result) process.exit(1);
console.log(JSON.stringify(result));
