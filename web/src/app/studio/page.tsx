import type { Metadata } from "next";
import { StudioDemo } from "@/components/studio-demo";

export const metadata: Metadata = { title: "智绣实验室" };
export default function StudioPage() { return <main className="inner-page"><header className="page-hero"><p className="eyebrow">INTELLIGENT CREATIVE STUDIO</p><h1>智绣实验室</h1><p>这里是生产接口入口，不模拟 AI 结果。后端未接入时会明确提示服务不可用。</p></header><StudioDemo /><section className="workflow"><p className="eyebrow">WORKFLOW</p><h2>可信的智能分析链路</h2><ol><li><span>01</span><strong>提交与校验</strong><p>检查文件格式、大小与图像质量。</p></li><li><span>02</span><strong>特征分析</strong><p>提取主体、色彩和向量特征。</p></li><li><span>03</span><strong>候选匹配</strong><p>返回可解释的相似纹样候选。</p></li><li><span>04</span><strong>人工复核</strong><p>专家确认文化含义与授权边界。</p></li></ol></section></main>; }
