"use client";

import { useMemo, useState } from "react";

const palettes = [
  { name: "羌红石青", colors: ["#f04f78", "#15d6c8", "#3346d3", "#f2c85b"] },
  { name: "雪山晨光", colors: ["#f7e6c4", "#dd784f", "#2a7280", "#192d49"] },
  { name: "墨绿织坊", colors: ["#e4c88a", "#8aa36b", "#315d50", "#172f2b"] },
];

const motifs = ["蝶恋花", "羊角守护", "山河菱花"];
const products = ["丝巾", "帆布包", "数字屏风"];

export function DesignWorkbench() {
  const [paletteIndex, setPaletteIndex] = useState(0);
  const [motifIndex, setMotifIndex] = useState(0);
  const [productIndex, setProductIndex] = useState(0);
  const palette = palettes[paletteIndex];
  const style = useMemo(() => ({
    "--design-primary": palette.colors[0],
    "--design-secondary": palette.colors[1],
    "--design-deep": palette.colors[2],
    "--design-accent": palette.colors[3],
    "--motif-rotation": `${motifIndex * 15}deg`,
  }) as React.CSSProperties, [palette, motifIndex]);

  return <section className="design-lab" aria-labelledby="design-lab-title">
    <header className="design-lab-heading"><div><p className="eyebrow">GENERATIVE DESIGN WORKBENCH</p><h2 id="design-lab-title">纹样再设计工坊</h2></div><p>参考动态纹样与产品生成流程，把色彩、母题和应用载体拆成可控步骤。当前为可交互视觉原型，不把生成画面标记为真实 AI 结果。</p></header>
    <div className="design-workbench">
      <div className="design-controls">
        <fieldset><legend>01 · 选择配色</legend><div className="option-list">{palettes.map((item, index) => <button type="button" className={index === paletteIndex ? "active" : ""} aria-pressed={index === paletteIndex} onClick={() => setPaletteIndex(index)} key={item.name}><span className="swatches">{item.colors.map((color) => <i key={color} style={{ backgroundColor: color }} />)}</span>{item.name}</button>)}</div></fieldset>
        <fieldset><legend>02 · 选择母题</legend><div className="option-list compact">{motifs.map((item, index) => <button type="button" className={index === motifIndex ? "active" : ""} aria-pressed={index === motifIndex} onClick={() => setMotifIndex(index)} key={item}>{item}</button>)}</div></fieldset>
        <fieldset><legend>03 · 选择载体</legend><div className="option-list compact">{products.map((item, index) => <button type="button" className={index === productIndex ? "active" : ""} aria-pressed={index === productIndex} onClick={() => setProductIndex(index)} key={item}>{item}</button>)}</div></fieldset>
      </div>
      <div className="design-stage" style={style}>
        <div className="motion-grid" aria-hidden="true" />
        <div className={`product-preview product-${productIndex}`}>
          <div className="generated-motif"><span /><span /><span /><b>绣</b></div>
        </div>
        <div className="design-caption"><span>实时组合预览</span><strong>{motifs[motifIndex]} · {palette.name}</strong><small>应用：{products[productIndex]}</small></div>
      </div>
    </div>
  </section>;
}
