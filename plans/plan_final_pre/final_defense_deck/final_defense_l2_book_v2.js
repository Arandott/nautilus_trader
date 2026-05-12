const pptxgen = require("pptxgenjs");
const {
  warnIfSlideHasOverlaps,
  warnIfSlideElementsOutOfBounds,
} = require("./pptxgenjs_helpers/layout");

const pptx = new pptxgen();
pptx.defineLayout({ name: "WIDE", width: 13.333, height: 7.5 });
pptx.layout = "WIDE";
pptx.author = "陈宝文";
pptx.company = "中央财经大学";
pptx.subject = "L2 本地订单簿特化结构优化最终答辩";
pptx.title = "面向低延迟场景的 L2 本地订单簿优化";
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: "Noto Sans CJK SC",
  bodyFontFace: "Noto Sans CJK SC",
  lang: "zh-CN",
};

const W = 13.333;
const H = 7.5;
const FONT = "Noto Sans CJK SC";
const S = pptx.ShapeType;

const C = {
  cover: "0E2638",
  cover2: "15364B",
  bg: "E8EEF3",
  paper: "F8FAFC",
  panel: "DDE8EF",
  navy: "0F3048",
  ink: "172D3A",
  muted: "536B7A",
  line: "B9CBD7",
  teal: "279C95",
  tealSoft: "DDF1EE",
  blue: "477CA2",
  orange: "E3863A",
  orangeSoft: "FBE8D5",
  gray: "8A9AAA",
  white: "FFFFFF",
};

const SLIDES = [];

function add(slide) {
  SLIDES.push(slide);
  return slide;
}

function bg(slide, color = C.bg) {
  slide.background = { color };
  slide.addShape(S.rect, {
    x: 0,
    y: 0,
    w: W,
    h: H,
    fill: { color },
    line: { color, transparency: 100 },
  });
}

function text(slide, str, x, y, w, h, opts = {}) {
  slide.addText(str, {
    x,
    y,
    w,
    h,
    fontFace: FONT,
    fontSize: opts.size ?? 12,
    bold: opts.bold ?? false,
    color: opts.color ?? C.ink,
    align: opts.align ?? "left",
    valign: opts.valign ?? "top",
    margin: opts.margin ?? 0,
    breakLine: false,
    fit: "shrink",
    paraSpaceAfterPt: opts.space ?? 2,
  });
}

function panel(slide, x, y, w, h, fill = C.paper, line = C.line) {
  slide.addShape(S.rect, {
    x,
    y,
    w,
    h,
    fill: { color: fill },
    line: { color: line, width: 0.7 },
  });
}

function header(slide, n, title, insight) {
  bg(slide);
  text(slide, `0${n}`.slice(-2), 0.72, 0.38, 0.58, 0.24, {
    size: 8,
    bold: true,
    color: C.teal,
    align: "left",
  });
  slide.addShape(S.line, {
    x: 1.42,
    y: 0.51,
    w: 0.66,
    h: 0,
    line: { color: C.teal, width: 1.1 },
  });
  text(slide, title, 0.72, 0.78, 11.9, 0.44, {
    size: 23,
    bold: true,
    color: C.navy,
  });
  if (insight) {
    text(slide, insight, 0.74, 1.34, 11.8, 0.36, {
      size: 12.5,
      bold: true,
      color: C.ink,
    });
  }
  slide.addShape(S.line, {
    x: 0.72,
    y: 7.04,
    w: 11.9,
    h: 0,
    line: { color: C.line, width: 0.6 },
  });
  text(slide, "L2 Specialized Order Book", 0.74, 7.15, 3.4, 0.16, {
    size: 6.8,
    bold: true,
    color: C.muted,
  });
  text(slide, String(n).padStart(2, "0"), 12.06, 7.11, 0.56, 0.22, {
    size: 8,
    bold: true,
    color: C.muted,
    align: "right",
  });
}

function bigMetric(slide, x, y, w, label, value, note, color = C.teal) {
  const compact = w < 1.62 || value.length >= 8;
  const valueSize = compact ? 14.2 : 18.6;
  panel(slide, x, y, w, 1.32, C.paper);
  slide.addShape(S.rect, {
    x,
    y,
    w: 0.08,
    h: 1.32,
    fill: { color },
    line: { color, transparency: 100 },
  });
  text(slide, label, x + 0.24, y + 0.16, w - 0.38, 0.18, {
    size: compact ? 7.2 : 8.2,
    bold: true,
    color: C.muted,
  });
  text(slide, value, x + 0.24, y + 0.42, w - 0.38, 0.42, {
    size: valueSize,
    bold: true,
    color,
  });
  text(slide, note, x + 0.24, y + 0.95, w - 0.38, 0.22, {
    size: compact ? 7.2 : 8.2,
    color: C.ink,
  });
}

function flowBox(slide, x, y, w, h, title, note, color = C.blue) {
  panel(slide, x, y, w, h, C.paper);
  slide.addShape(S.rect, {
    x,
    y,
    w,
    h: 0.1,
    fill: { color },
    line: { color, transparency: 100 },
  });
  text(slide, title, x + 0.2, y + 0.24, w - 0.4, 0.26, {
    size: 11,
    bold: true,
    color: C.navy,
  });
  text(slide, note, x + 0.2, y + 0.62, w - 0.4, h - 0.7, {
    size: 8.8,
    color: C.ink,
  });
}

function arrow(slide, x1, y1, x2, y2, color = C.line) {
  slide.addShape(S.line, {
    x: x1,
    y: y1,
    w: x2 - x1,
    h: y2 - y1,
    line: { color, width: 1.2, endArrowType: "triangle" },
  });
}

function bullets(slide, items, x, y, w, opts = {}) {
  items.forEach((item, i) => {
    const yy = y + i * (opts.gap ?? 0.52);
    slide.addShape(S.rect, {
      x,
      y: yy + 0.08,
      w: 0.08,
      h: 0.08,
      fill: { color: opts.color ?? C.teal },
      line: { color: opts.color ?? C.teal, transparency: 100 },
    });
    text(slide, item, x + 0.22, yy, w - 0.22, 0.28, {
      size: opts.size ?? 10,
      bold: opts.bold ?? false,
      color: opts.textColor ?? C.ink,
    });
  });
}

function hBar(slide, x, y, w, label, value, max, color, valueText) {
  text(slide, label, x, y, 1.36, 0.18, { size: 7.5, bold: true, color: C.ink });
  slide.addShape(S.rect, {
    x: x + 1.52,
    y: y + 0.02,
    w,
    h: 0.16,
    fill: { color: C.panel },
    line: { color: C.panel, transparency: 100 },
  });
  slide.addShape(S.rect, {
    x: x + 1.52,
    y: y + 0.02,
    w: Math.max(0.04, (value / max) * w),
    h: 0.16,
    fill: { color },
    line: { color, transparency: 100 },
  });
  text(slide, valueText, x + 1.78 + w, y - 0.01, 1.05, 0.2, {
    size: 7.4,
    bold: true,
    color,
  });
}

function verticalBars(slide, x, y, w, h, series, max, unit = "") {
  const slot = w / series.length;
  series.forEach((s, i) => {
    const bh = (s.value / max) * (h - 0.54);
    const bx = x + i * slot + slot * 0.22;
    const bw = slot * 0.46;
    slide.addShape(S.rect, {
      x: bx,
      y: y + h - 0.38 - bh,
      w: bw,
      h: bh,
      fill: { color: s.color },
      line: { color: s.color, transparency: 100 },
    });
    const labelY = Math.max(y + 0.04, y + h - 0.74 - bh);
    const labelW = slot * 0.62;
    const labelX = x + i * slot + (slot - labelW) / 2;
    text(slide, s.valueText ?? `${s.value}${unit}`, labelX, labelY, labelW, 0.18, {
      size: 5.8,
      bold: true,
      color: s.color,
      align: "center",
    });
    text(slide, s.label, x + i * slot, y + h - 0.18, slot * 0.9, 0.16, {
      size: 6.8,
      color: C.muted,
      align: "center",
    });
  });
  slide.addShape(S.line, {
    x,
    y: y + h - 0.34,
    w,
    h: 0,
    line: { color: C.line, width: 0.6 },
  });
}

function splitTitle(slide, x, y, label, title, color) {
  text(slide, label, x, y, 1.1, 0.18, { size: 7.4, bold: true, color });
  text(slide, title, x, y + 0.3, 3.4, 0.24, {
    size: 14,
    bold: true,
    color: C.navy,
  });
}

function miniFlow(slide, x, y, w, h, title, color) {
  slide.addText(title, {
    x,
    y,
    w,
    h,
    fontFace: FONT,
    fontSize: 8.2,
    bold: true,
    color: C.navy,
    align: "center",
    valign: "mid",
    margin: 0,
    fill: { color: C.paper },
    line: { color: C.line, width: 0.7 },
    fit: "shrink",
  });
  slide.addShape(S.line, {
    x,
    y: y + 0.02,
    w,
    h: 0,
    line: { color, width: 1.4 },
  });
}

// 1. Cover
{
  const slide = add(pptx.addSlide());
  bg(slide, C.cover);
  slide.addShape(S.rect, {
    x: 0,
    y: 0,
    w: W,
    h: H,
    fill: { color: C.cover },
    line: { color: C.cover, transparency: 100 },
  });
  for (let i = 0; i < 15; i++) {
    const yy = 0.92 + i * 0.34;
    const len = 2.1 + (i % 5) * 0.42;
    slide.addShape(S.rect, {
      x: 8.9 + (i % 3) * 0.24,
      y: yy,
      w: len,
      h: 0.035,
      fill: { color: i % 4 === 0 ? C.teal : "8DA4B4", transparency: i % 4 === 0 ? 18 : 62 },
      line: { color: C.cover, transparency: 100 },
    });
  }
  slide.addShape(S.line, {
    x: 0.92,
    y: 1.02,
    w: 0,
    h: 1.34,
    line: { color: C.teal, width: 3 },
  });
  text(slide, "面向低延迟场景的\nL2 本地订单簿优化", 1.18, 0.96, 7.4, 1.34, {
    size: 34,
    bold: true,
    color: C.white,
  });
  text(slide, "L2 Specialized Local Order Book for Low-Latency Workloads", 1.2, 2.72, 6.9, 0.26, {
    size: 12,
    bold: true,
    color: "8BD4CF",
  });
  slide.addShape(S.line, {
    x: 1.2,
    y: 5.48,
    w: 5.4,
    h: 0,
    line: { color: "31566C", width: 0.8 },
  });
  text(slide, "陈宝文  |  中央财经大学", 1.2, 5.72, 4.4, 0.22, {
    size: 11,
    color: "DCE7ED",
  });
  text(slide, "2026 年 5 月", 1.2, 6.12, 2.0, 0.2, {
    size: 10,
    color: "9DB1BE",
  });
  text(slide, "FINAL DEFENSE", 10.1, 6.2, 1.8, 0.18, {
    size: 7.5,
    bold: true,
    color: "9DB1BE",
    align: "right",
  });
}

// 2. Research problem
{
  const slide = add(pptx.addSlide());
  header(slide, 2, "研究问题：L2 本地订单簿为什么值得专门优化", "真正反复消耗时间的是本地状态维护、top-k 查询和大规模 replay，而不只是解析单条消息。");
  flowBox(slide, 1.0, 2.25, 2.35, 1.1, "高频 L2 Delta", "原始行情持续冲击价格档位", C.blue);
  flowBox(slide, 4.08, 2.25, 2.35, 1.1, "Local Book", "本地维护 bid / ask 状态", C.teal);
  flowBox(slide, 7.16, 2.25, 2.35, 1.1, "Query / Feature", "best、top-k、深度因子反复读取", C.blue);
  flowBox(slide, 10.24, 2.25, 2.0, 1.1, "Replay", "回测与离线验证", C.teal);
  arrow(slide, 3.42, 2.8, 3.96, 2.8);
  arrow(slide, 6.5, 2.8, 7.04, 2.8);
  arrow(slide, 9.58, 2.8, 10.12, 2.8);
  panel(slide, 1.0, 4.32, 5.0, 1.18, C.paper);
  splitTitle(slide, 1.32, 4.58, "MOTIVATION", "L2 语义更窄", C.teal);
  text(slide, "L2_MBP 只需要 price -> size 的聚合档位；通用订单簿路径仍保留 order-level 抽象。", 1.32, 5.12, 4.28, 0.26, {
    size: 9.6,
    color: C.ink,
  });
  panel(slide, 7.32, 4.32, 4.35, 1.18, C.panel);
  splitTitle(slide, 7.64, 4.58, "QUESTION", "能否消掉不必要的常数项", C.blue);
  text(slide, "目标不是推翻 baseline，而是在相同输入与接口下验证 L2 专用结构的工程边界。", 7.64, 5.12, 3.6, 0.26, {
    size: 9.6,
    color: C.ink,
  });
}

// 3. Baseline overhead
{
  const slide = add(pptx.addSlide());
  header(slide, 3, "Baseline Overhead：通用订单簿的成本来源", "baseline 的价值是统一 L1/L2/L3 语义；L2 场景的优化空间来自可消除的订单级常数项。");
  panel(slide, 0.96, 2.08, 6.25, 3.72, C.paper);
  text(slide, "native OrderBook(BookType::L2_MBP)", 1.28, 2.38, 5.4, 0.3, {
    size: 15,
    bold: true,
    color: C.navy,
  });
  const stack = [
    ["BookLadder", "每侧一棵有序价格树", C.blue],
    ["BTreeMap<BookPrice, BookLevel>", "定位 price level：O(log L)", C.blue],
    ["HashMap<OrderId, BookPrice>", "维护合成 order_id cache", C.orange],
    ["IndexMap<OrderId, BookOrder>", "L2 仍进入 order-level 容器", C.orange],
  ];
  stack.forEach((s, i) => {
    const y = 3.0 + i * 0.55;
    slide.addShape(S.rect, {
      x: 1.3,
      y,
      w: 4.96,
      h: 0.36,
      fill: { color: i < 2 ? C.panel : C.orangeSoft },
      line: { color: i < 2 ? C.line : "F1C9A5", width: 0.5 },
    });
    text(slide, s[0], 1.52, y + 0.08, 2.06, 0.16, {
      size: 8.2,
      bold: true,
      color: s[2],
    });
    text(slide, s[1], 3.95, y + 0.08, 2.05, 0.16, {
      size: 7.8,
      color: C.ink,
      align: "right",
    });
  });
  panel(slide, 7.72, 2.08, 4.6, 3.72, C.panel);
  splitTitle(slide, 8.05, 2.42, "OVERHEAD", "L2 实际不需要什么", C.orange);
  bullets(slide, [
    "不需要 order id cache 的一致性维护",
    "不需要 BookLevel.orders 容器",
    "不需要为 price level 构造合成订单语义",
    "空间上不应为 order-level 对象付费",
  ], 8.05, 3.22, 3.72, { color: C.orange, gap: 0.54, size: 9.2 });
  text(slide, "结论：这里优化的不是 Big-O，而是 hot path 上反复出现的对象层级、hash 查找和容器维护。", 1.18, 6.22, 10.9, 0.28, {
    size: 11.2,
    bold: true,
    color: C.navy,
    align: "center",
  });
}

// 4. Optimization map
{
  const slide = add(pptx.addSlide());
  header(slide, 4, "优化方法：三种结构对应三类成本假设", "Tree、Vec、Grid 分别验证语义收窄、连续内存、tick 离散化是否能转化为真实收益。");
  const cards = [
    ["Tree", "去掉订单级抽象", "保留有序树，value 直接存 Quantity", "更新常数下降；内存收缩", "top-k 仍是树遍历", C.teal],
    ["Vec", "提升连续读取局部性", "排序 Vec + raw payload", "top-k 查询非常快；RSS 最低", "insert/delete 中间位移", C.blue],
    ["Grid", "利用价格 tick 离散性", "page + 64 slot + bitmap", "dense/deep 场景有潜力", "sparse replay 空间放大", C.orange],
  ];
  cards.forEach((c, i) => {
    const x = 0.92 + i * 4.16;
    panel(slide, x, 2.08, 3.55, 3.72, C.paper);
    text(slide, c[0], x + 0.32, 2.38, 1.3, 0.38, {
      size: 21,
      bold: true,
      color: c[5],
    });
    text(slide, c[1], x + 0.34, 2.94, 2.8, 0.24, {
      size: 10.2,
      bold: true,
      color: C.navy,
    });
    slide.addShape(S.line, {
      x: x + 0.34,
      y: 3.36,
      w: 2.78,
      h: 0,
      line: { color: C.line, width: 0.7 },
    });
    text(slide, "结构", x + 0.34, 3.62, 0.48, 0.16, { size: 7.2, bold: true, color: C.muted });
    text(slide, c[2], x + 0.94, 3.58, 2.16, 0.28, { size: 8.4, color: C.ink });
    text(slide, "预期", x + 0.34, 4.18, 0.48, 0.16, { size: 7.2, bold: true, color: C.muted });
    text(slide, c[3], x + 0.94, 4.14, 2.16, 0.28, { size: 8.4, color: C.ink });
    text(slide, "代价", x + 0.34, 4.74, 0.48, 0.16, { size: 7.2, bold: true, color: C.muted });
    text(slide, c[4], x + 0.94, 4.7, 2.16, 0.28, { size: 8.4, color: C.ink });
  });
  text(slide, "统一评估：相同 raw L2 delta、相同 L2BookOps 接口、相同 correctness / replay / RSS 输出口径。", 1.1, 6.28, 11.1, 0.26, {
    size: 10.6,
    bold: true,
    color: C.navy,
    align: "center",
  });
}

// 5. System design
{
  const slide = add(pptx.addSlide());
  header(slide, 5, "系统总体设计：让结果可比，而不是让实现各说各话", "source of truth 始终是原始 L2 delta；结构只替换内部表示，不改变外部语义。");
  const y = 2.34;
  flowBox(slide, 0.88, y, 1.78, 1.02, "raw delta", "原始 L2 数据", C.blue);
  flowBox(slide, 3.16, y, 1.78, 1.02, "parser / replay", "时间顺序回放", C.teal);
  flowBox(slide, 5.44, y, 1.78, 1.02, "L2BookOps", "统一操作接口", C.blue);
  text(slide, "实现候选", 7.98, 2.02, 1.4, 0.18, { size: 8.2, bold: true, color: C.muted, align: "center" });
  miniFlow(slide, 7.98, 2.34, 1.38, 0.34, "baseline", C.gray);
  miniFlow(slide, 7.98, 2.82, 1.38, 0.34, "tree", C.teal);
  miniFlow(slide, 7.98, 3.3, 1.38, 0.34, "vec", C.blue);
  miniFlow(slide, 7.98, 3.78, 1.38, 0.34, "grid", C.orange);
  flowBox(slide, 10.18, y, 2.02, 1.02, "summary", "correctness / perf / RSS", C.teal);
  arrow(slide, 2.72, y + 0.51, 3.06, y + 0.51);
  arrow(slide, 5.0, y + 0.51, 5.34, y + 0.51);
  arrow(slide, 7.28, y + 0.51, 7.62, y + 0.51);
  arrow(slide, 9.68, y + 0.51, 10.08, y + 0.51);
  panel(slide, 1.22, 5.08, 3.12, 0.96, C.paper);
  text(slide, "统一输入", 1.5, 5.34, 2.4, 0.22, { size: 11.2, bold: true, color: C.navy });
  text(slide, "所有结构消费同一份 raw delta", 1.5, 5.7, 2.4, 0.18, { size: 8.0, color: C.ink });
  panel(slide, 5.08, 5.08, 3.12, 0.96, C.paper);
  text(slide, "统一接口", 5.36, 5.34, 2.4, 0.22, { size: 11.2, bold: true, color: C.navy });
  text(slide, "只替换内部表示，不改变外部语义", 5.36, 5.7, 2.4, 0.18, { size: 8.0, color: C.ink });
  panel(slide, 8.94, 5.08, 3.12, 0.96, C.tealSoft);
  text(slide, "统一解释", 9.22, 5.34, 2.4, 0.22, { size: 11.2, bold: true, color: C.navy });
  text(slide, "结果回到成本假设本身", 9.22, 5.7, 2.4, 0.18, { size: 8.0, color: C.ink });
}

// 6. Tree
{
  const slide = add(pptx.addSlide());
  header(slide, 6, "L2TreeBook：语义收窄带来稳定收益", "Tree 保留有序树的鲁棒性，把 L2 不需要的订单语义从 hot path 中拿掉。");
  panel(slide, 0.92, 2.0, 4.7, 3.64, C.paper);
  splitTitle(slide, 1.24, 2.32, "DESIGN", "从 BookLevel 到 Quantity", C.teal);
  flowBox(slide, 1.28, 3.12, 3.96, 0.62, "BTreeMap<BookPrice, BookLevel>", "price level + orders 容器", C.orange);
  flowBox(slide, 1.28, 4.14, 3.96, 0.62, "BTreeMap<BookPrice, Quantity>", "price level 直接存聚合数量", C.teal);
  arrow(slide, 3.26, 3.8, 3.26, 4.08);
  text(slide, "理论收益：仍是 O(log L)，但对象层级、cache 操作和合成 order 维护消失，常数项下降。", 1.24, 5.12, 3.92, 0.3, {
    size: 8.8,
    color: C.ink,
  });
  bigMetric(slide, 5.96, 2.0, 1.96, "replay only", "239,500/s", "+28.4% vs baseline", C.teal);
  bigMetric(slide, 8.16, 2.0, 1.96, "peak RSS", "32.5 MB", "约 -37.6%", C.teal);
  bigMetric(slide, 10.36, 2.0, 1.82, "定位", "主候选", "默认实时维护结构", C.teal);
  panel(slide, 6.1, 3.82, 6.14, 1.82, C.paper);
  text(slide, "10M replay 吞吐对比", 6.42, 4.1, 2.8, 0.24, { size: 11.5, bold: true, color: C.navy });
  hBar(slide, 6.42, 4.64, 2.78, "baseline", 186535, 239500, C.gray, "186,535/s");
  hBar(slide, 6.42, 5.12, 2.78, "L2TreeBook", 239500, 239500, C.teal, "239,500/s");
}

// 7. Vec
{
  const slide = add(pptx.addSlide());
  header(slide, 7, "L2VecBook：查询局部性强，但维护路径有代价", "连续内存让 top-k 查询非常快；真实 replay 中的中间 insert/delete 会吃掉维护收益。");
  panel(slide, 0.92, 2.0, 5.25, 3.8, C.paper);
  splitTitle(slide, 1.24, 2.32, "QUERY", "top-k 查询延迟显著下降", C.blue);
  hBar(slide, 1.24, 3.16, 1.72, "baseline q100", 3379, 6249, C.gray, "3,379 ns");
  hBar(slide, 1.24, 3.66, 1.72, "vec q100", 757, 6249, C.teal, "757 ns");
  hBar(slide, 1.24, 4.34, 1.72, "baseline q1000", 5354, 6249, C.gray, "5,354 ns");
  hBar(slide, 1.24, 4.84, 1.72, "vec q1000", 1299, 6249, C.teal, "1,299 ns");
  text(slide, "原因：排序 Vec 的前缀扫描更接近 CPU cache 友好的连续读取。", 1.24, 5.42, 4.38, 0.24, {
    size: 8.8,
    color: C.ink,
  });
  panel(slide, 6.82, 2.0, 5.2, 3.8, C.panel);
  splitTitle(slide, 7.14, 2.32, "MAINTENANCE", "真实 replay 暴露 shift 成本", C.orange);
  hBar(slide, 7.14, 3.22, 2.0, "baseline", 186535, 239500, C.gray, "186,535/s");
  hBar(slide, 7.14, 3.8, 2.0, "tree", 239500, 239500, C.teal, "239,500/s");
  hBar(slide, 7.14, 4.38, 2.0, "vec", 175553, 239500, C.orange, "175,553/s");
  text(slide, "工程定位：不作为默认实时维护 book；适合 top-k feature、因子计算和离线 analytics。", 7.14, 5.1, 4.26, 0.34, {
    size: 9.2,
    bold: true,
    color: C.navy,
  });
}

// 8. Grid
{
  const slide = add(pptx.addSlide());
  header(slide, 8, "L2GridBook：tick-grid 是条件型优化", "Grid 的优势依赖 dense/deep 盘口；真实 sparse replay 下，page 空间和浅查询常数会反噬。");
  panel(slide, 0.92, 2.0, 5.2, 3.72, C.paper);
  splitTitle(slide, 1.24, 2.32, "WHEN IT WORKS", "理论优势成立的条件", C.teal);
  bullets(slide, [
    "价格分布 dense：active slots / allocated slots 高",
    "查询深度 deep：top-N 经常跨连续价位",
    "更新集中在已有 page：减少 page 分配",
  ], 1.24, 3.14, 4.2, { color: C.teal, gap: 0.6, size: 9.2 });
  panel(slide, 6.82, 2.0, 5.2, 3.72, C.orangeSoft);
  splitTitle(slide, 7.14, 2.32, "WHAT HAPPENED", "真实 sparse replay 的代价", C.orange);
  bigMetric(slide, 7.08, 3.0, 1.52, "replay", "190k/s", "略高 baseline", C.orange);
  bigMetric(slide, 8.88, 3.0, 1.52, "q100", "4,554 ns", "慢于 baseline", C.orange);
  bigMetric(slide, 10.68, 3.0, 1.28, "RSS", "206 MB", "空间放大", C.orange);
  text(slide, "工程定位：dense/deep 场景候选；当前 BTCUSDT sparse replay 不适合作为通用默认路径。", 7.14, 4.92, 4.28, 0.4, {
    size: 9.2,
    bold: true,
    color: C.navy,
  });
}

// 9. Experiment
{
  const slide = add(pptx.addSlide());
  header(slide, 9, "实验设计：统一口径验证结构假设", "实验闭环由 microbench、真实 replay、查询负载和内存指标共同组成。");
  bigMetric(slide, 0.92, 2.0, 2.56, "数据", "10M", "Binance Futures BTCUSDT L2 delta", C.blue);
  bigMetric(slide, 3.82, 2.0, 2.56, "重复", "3 次", "降低单次运行波动", C.teal);
  bigMetric(slide, 6.72, 2.0, 2.56, "负载", "3 类", "replay_only / q100 / q1000", C.blue);
  bigMetric(slide, 9.62, 2.0, 2.56, "指标", "4 组", "correctness / throughput / latency / RSS", C.teal);
  panel(slide, 1.08, 4.52, 11.05, 0.98, C.paper);
  miniFlow(slide, 1.42, 4.74, 2.02, 0.54, "microbench", C.blue);
  miniFlow(slide, 4.08, 4.74, 2.02, 0.54, "replay", C.teal);
  miniFlow(slide, 6.74, 4.74, 2.02, 0.54, "query mix", C.blue);
  miniFlow(slide, 9.4, 4.74, 2.02, 0.54, "summary", C.teal);
  arrow(slide, 3.5, 5.0, 4.0, 5.0);
  arrow(slide, 6.16, 5.0, 6.66, 5.0);
  arrow(slide, 8.82, 5.0, 9.32, 5.0);
  text(slide, "审稿口径：每个结构都要回答“想消掉哪部分 overhead、预期收益是什么、实测是否支持”。", 1.18, 6.1, 10.95, 0.26, {
    size: 10.6,
    bold: true,
    color: C.navy,
    align: "center",
  });
}

// 10. Core results
{
  const slide = add(pptx.addSlide());
  header(slide, 10, "核心结果：没有一种结构全场景最优", "Tree 综合最稳；Vec 查询最强；Grid 是条件型结构；baseline 是安全参照。");
  panel(slide, 0.72, 2.0, 3.78, 3.38, C.paper);
  text(slide, "吞吐 updates/s", 1.0, 2.28, 2.8, 0.22, { size: 11.5, bold: true, color: C.navy });
  verticalBars(slide, 1.02, 2.78, 3.0, 1.82, [
    { label: "base", value: 186535, valueText: "186k", color: C.gray },
    { label: "tree", value: 239500, valueText: "239k", color: C.teal },
    { label: "vec", value: 175553, valueText: "176k", color: C.blue },
    { label: "grid", value: 190025, valueText: "190k", color: C.orange },
  ], 260000);
  text(slide, "Tree 在真实维护路径上最稳。", 1.0, 4.9, 2.86, 0.24, { size: 8.1, color: C.ink });
  panel(slide, 4.78, 2.0, 3.78, 3.38, C.paper);
  text(slide, "查询延迟 q1000", 5.06, 2.28, 2.8, 0.22, { size: 11.5, bold: true, color: C.navy });
  verticalBars(slide, 5.08, 2.78, 3.0, 1.82, [
    { label: "base", value: 5354, valueText: "5354", color: C.gray },
    { label: "tree", value: 2605, valueText: "2605", color: C.teal },
    { label: "vec", value: 1299, valueText: "1299", color: C.blue },
    { label: "grid", value: 6249, valueText: "6249", color: C.orange },
  ], 7000);
  text(slide, "Vec 的连续扫描优势最明显。", 5.06, 4.9, 2.86, 0.24, { size: 8.1, color: C.ink });
  panel(slide, 8.84, 2.0, 3.78, 3.38, C.paper);
  text(slide, "Peak RSS MB", 9.12, 2.28, 2.8, 0.22, { size: 11.5, bold: true, color: C.navy });
  verticalBars(slide, 9.14, 2.78, 3.0, 1.82, [
    { label: "base", value: 52.1, valueText: "52", color: C.gray },
    { label: "tree", value: 32.5, valueText: "33", color: C.teal },
    { label: "vec", value: 30.6, valueText: "31", color: C.blue },
    { label: "grid", value: 206, valueText: "206", color: C.orange },
  ], 220);
  text(slide, "Grid 的 page 预留导致空间放大。", 9.12, 4.9, 2.86, 0.24, { size: 8.1, color: C.ink });
  panel(slide, 1.1, 5.82, 11.1, 0.62, C.panel);
  text(slide, "工程结论：Tree 做实时维护主路径，Vec 做查询/因子辅助，Grid 保留为 dense/deep 场景研究候选。", 1.34, 6.02, 10.62, 0.2, {
    size: 9.5,
    bold: true,
    color: C.navy,
    align: "center",
  });
}

// 11. E2E
{
  const slide = add(pptx.addSlide());
  header(slide, 11, "工程落地验证：接入真实系统路径，但保持 opt-in", "研究结构已开始进入 DataEngine/cache/backtest 链路；当前定位是离线验证，不宣称 production-ready。");
  panel(slide, 0.92, 2.14, 11.55, 1.42, C.paper);
  flowBox(slide, 1.24, 2.46, 1.9, 0.64, "OrderBook", "Rust / Python API", C.blue);
  flowBox(slide, 3.86, 2.46, 1.9, 0.64, "DataEngine", "数据流接入", C.teal);
  flowBox(slide, 6.48, 2.46, 1.9, 0.64, "cache", "本地状态维护", C.blue);
  flowBox(slide, 9.1, 2.46, 1.9, 0.64, "backtest", "离线撮合验证", C.teal);
  arrow(slide, 3.22, 2.78, 3.78, 2.78);
  arrow(slide, 5.84, 2.78, 6.4, 2.78);
  arrow(slide, 8.46, 2.78, 9.02, 2.78);
  panel(slide, 1.12, 4.42, 3.0, 1.02, C.tealSoft);
  text(slide, "Rust e2e", 1.42, 4.72, 2.2, 0.22, { size: 12, bold: true, color: C.navy });
  text(slide, "DataEngine/cache 路径验证", 1.42, 5.12, 2.2, 0.18, { size: 8.4, color: C.ink });
  panel(slide, 5.16, 4.42, 3.0, 1.02, C.tealSoft);
  text(slide, "Python e2e", 5.46, 4.72, 2.2, 0.22, { size: 12, bold: true, color: C.navy });
  text(slide, "Python DataEngine 用户侧路径", 5.46, 5.12, 2.2, 0.18, { size: 8.4, color: C.ink });
  panel(slide, 9.2, 4.42, 3.0, 1.02, C.orangeSoft);
  text(slide, "边界声明", 9.5, 4.72, 2.2, 0.22, { size: 12, bold: true, color: C.orange });
  text(slide, "不展示实盘收益，不宣称默认上线", 9.5, 5.12, 2.2, 0.18, { size: 8.4, color: C.ink });
}

// 12. Summary
{
  const slide = add(pptx.addSlide());
  header(slide, 12, "总结与展望：从单点跑分到结构边界", "贡献不是证明某个容器永远最快，而是建立统一比较框架并识别 L2 专用结构的适用边界。");
  bigMetric(slide, 0.92, 2.04, 3.46, "Tree", "默认工程候选", "吞吐与内存都稳定改善", C.teal);
  bigMetric(slide, 4.94, 2.04, 3.46, "Vec", "查询/因子结构", "top-k 查询和内存最有优势", C.blue);
  bigMetric(slide, 8.96, 2.04, 3.46, "Grid", "条件型探索", "dense/deep 场景继续研究", C.orange);
  panel(slide, 1.08, 4.66, 5.1, 1.12, C.paper);
  splitTitle(slide, 1.4, 4.92, "ANSWER", "本文回答了什么", C.teal);
  text(slide, "baseline 的 overhead、每种结构的预期收益、真实 replay 是否支持这些判断。", 1.4, 5.58, 4.42, 0.16, {
    size: 8.8,
    color: C.ink,
  });
  panel(slide, 7.16, 4.66, 5.1, 1.12, C.panel);
  splitTitle(slide, 7.48, 4.92, "NEXT", "后续工作", C.blue);
  text(slide, "扩大数据集、继续生产化 Tree、优化 Vec/Grid 条件场景、完善 live 前验证。", 7.48, 5.58, 4.42, 0.16, {
    size: 8.8,
    color: C.ink,
  });
}

if (process.env.SLIDES_LAYOUT_WARN === "1") {
  SLIDES.forEach((slide) => {
    warnIfSlideHasOverlaps(slide, pptx, {
      ignoreLines: true,
      ignoreDecorativeShapes: true,
    });
    warnIfSlideElementsOutOfBounds(slide, pptx);
  });
} else {
  SLIDES.forEach((slide) => warnIfSlideElementsOutOfBounds(slide, pptx));
}

pptx.writeFile({ fileName: "final_defense_l2_book_v2.pptx" });
