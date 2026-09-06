import type { Metadata } from "next";

export const metadata: Metadata = { title: "图片处理与隐私说明" };

export default function PrivacyPage() {
  return <main className="inner-page">
    <header className="page-hero"><p className="eyebrow">PRIVACY</p><h1>图片处理与隐私说明</h1><p>上传前请确认你有权使用图片，并且图片不包含不必要的个人信息。</p></header>
    <section className="prose-card">
      <h2>处理目的</h2><p>上传图片仅用于提取色彩、图像特征及检索相似纹样，不用于确认文化含义、权利状态或商业授权。</p>
      <h2>保存与删除</h2><p>系统可能为完成异步分析而临时保存图片。匿名上传内容最长保留 24 小时，随后由清理任务删除；分析记录可能保留输入摘要、算法版本和非原始图片结果，用于审计与故障排查。</p>
      <h2>请勿上传</h2><p>请勿上传身份证件、人脸、联系方式、未公开商业资料，或你无权处理的作品。公开候选库仅展示通过人工审核且允许公开的内容。</p>
      <h2>联系与删除请求</h2><p>正式公网部署时，运营方必须在此处补充有效联系方式和数据删除申请渠道；未补充前不得开放公众上传。</p>
    </section>
  </main>;
}
