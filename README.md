# 肺癌临床每日速递

每日自动检索 PubMed 肺癌临床文献，DeepSeek AI 生成中文核心结论，GitHub Pages 托管。

## 功能

- **每日 7:00 AM（北京时间）** 自动更新
- **PubMed 检索**：临床 RCT、Meta、指南、系统综述
- **淋巴结专题**：肺癌淋巴结分期、清扫、前哨淋巴结、EBUS 等
- **AI 总结**：每篇文章一句中文关键结论 + 关键词
- **影响因子 & 分区**展示
- **重点推荐**：按期刊影响力 + 文献类型加权排序 Top 5-8
- **全量归档**：按日期可翻看任意往期

## 技术栈

- Python（PubMed E-utilities + DeepSeek API）
- GitHub Actions（每日定时 + 手动触发）
- GitHub Pages（静态托管）

## 配置

在仓库 Settings → Secrets and variables → Actions 中添加：

| Secret | 必填 | 说明 |
|--------|------|------|
| `DEEPSEEK_API_KEY` | 是 | DeepSeek API 密钥 |
| `NCBI_API_KEY` | 否 | PubMed E-utilities API 密钥（提高频率限制） |

## 手动运行

Actions → Lung Cancer Daily Brief → Run workflow

## 本地运行

```bash
pip install -r requirements.txt
DEEPSEEK_API_KEY=your_key python -m scripts.fetch_pubmed
DEEPSEEK_API_KEY=your_key python -m scripts.summarize
DEEPSEEK_API_KEY=your_key python -m scripts.generate
```

## 许可证

MIT
