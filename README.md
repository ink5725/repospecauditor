# SpecAuditor 独立复现

基于论文 *SpecAuditor: Generating Audit Specifications for LLM-Driven Bug
Detection*（2025）的独立复现实现。，在 Linux 内核 v6.17-rc3 上
完成 100 个 CVE 补丁的端到端复现。

## 方法（三阶段）

| 阶段 | 内容 | 实现 |
| ---- | ---- | ---- |
| Stage 1 | 从历史 bug 补丁提取种子规范 `{entity, constraint}` → LLM 差异验证（pre 违反 / post 满足）→ 语义泛化 | `sa/stage1.py` |
| Stage 2 | 文档语义检索发现相似实体（top-100）→ LLM 判断约束适用性并生成新规范 | `sa/stage2.py` |
| Stage 3 | AST 查询定位候选 → LLM 违规检查 → 上下文感知报告修剪（最多 5 轮） | `sa/stage3.py` |

## 目录结构

```
repro-specauditor/
├── sa/                    # 核心实现（约 1900 行）
│   ├── llm_client.py      # LLM 客户端（JSON 容错解析、重试、token 统计）
│   ├── embedding.py       # 嵌入客户端（API / 本地双后端）
│   ├── vector_store.py    # numpy 向量库（L2 on 归一化，score=1-distance）
│   ├── code_index.py      # tree-sitter AST 索引（59.8 万函数 / 440 万调用点）
│   ├── ast_tools.py       # tree-sitter AST 解析
│   ├── doc_indexer.py     # 文档语料解析
│   ├── git_ops.py         # 补丁解析（git diff -W、pre/post 函数提取）
│   ├── prompts.py         # 三阶段提示词（对应论文 Table 1-3）
│   ├── stage1.py          # 种子规范提取 + 验证 + 泛化
│   ├── stage2.py          # 相似实体发现 + 新规范生成
│   ├── stage3.py          # AST 定位 + 违规检查 + 报告修剪
│   └── config.py          # .env 配置加载
├── scripts/               # 实验脚本
│   ├── fetch_docs.py      # 抓取内核文档语料
│   ├── build_doc_db.py    # 构建文档向量库
│   ├── index_codebase.py  # 构建代码 AST 索引
│   ├── collect_100_seeds.py  # NVD 收集 100 个种子补丁
│   ├── run_e2e.py         # 端到端流水线（Stage1→2→3）
│   ├── run_stage2.py / run_stage3.py / run_stage3_100_parallel.py  # 分阶段运行（并发+断点续跑）
│   ├── review_reports.py  # 196 报告严格复审
│   ├── reproduce_table6.py    # Table 6：实体类型分布
│   ├── reproduce_table7_llmonly.py  # Table 7：LLM-only 基线
│   ├── table7_ctrl_official47.py   # 官方 47 目标对照实验
│   └── summarize_*.py     # 结果汇总
├── data/                  # 数据与产物
│   ├── seed_commits_100.csv    # 100 个种子补丁（10 类 × 10）
│   ├── kernel_api_docs/        # 文档语料（14709 实体-描述对）
│   ├── doc_vectors/            # 嵌入向量库（14126 向量）
│   ├── code_index.sqlite       # 代码 AST 索引（1.2GB）
│   └── outputs_100/            # ★ 全部实验结果（见下）
├── config/llm.env.example     # LLM / 嵌入配置模板
├── requirements.txt
├── REPRODUCTION_REPORT.md     # ★ 完整复现报告（Table 5/6/7/9）
└── README.md
```

## 实验结果（`data/outputs_100/`）

| 文件 | 内容 |
| ---- | ---- |
| `stage1_out.json` | 100 种子规范 + 差异验证（84/100 通过，84%） |
| `stage2_out.json` | 55 个生成规范 |
| `stage3_reports.json` | 340 个违规报告（含修剪判定，196 保留） |
| `stage3_review.json` | 196 条严格复审（**105 REAL_BUG** / 63 FP / 14 CW / 3 ERR） |
| `REAL_BUG_105_list.csv` | 105 个漏洞清单（函数、文件、类型、证据） |
| `REAL_BUG_105_fixstatus.csv` | 修复状态（社区提交提及情况） |
| `UNFIXED_BUGS_REPORT.md` | 未修复漏洞报告（披露状态分析） |
| `table6_classification.json` | Table 6：实体类型分布 |
| `table7_llm_only.json` | Table 7：LLM-only 基线（函数级 74/105、文件级 52/105） |
| `table7_ctrl_official47.json` | 官方 47 目标对照实验（25/39） |
| `table7_top30.json` | 精选 30 个最强证据漏洞 |
| `llm_usage_summary.json` | 各阶段 token 消耗（Table 9 依据） |
| `table5/7/9_reproduction.md` | 各表格复现文档 |
| `implementation.md` / `experiment_setup.md` | 实现与环境说明 |

## 快速开始

```bash
pip install -r requirements.txt
cp config/llm.env.example config/llm.env   # 填入 LLM 端点与密钥

# 1) 准备内核源码（论文实验对象 v6.17-rc3）
# 2) 构建语料与索引（约 1-2 小时）
python scripts/fetch_docs.py --out data/kernel_api_docs
python scripts/build_doc_db.py --docs data/kernel_api_docs --db data/doc_vectors
python scripts/index_codebase.py --root /path/to/linux --db data/code_index.sqlite

# 3) 端到端复现（Stage1 → Stage2 → Stage3）
python scripts/run_e2e.py --kernel /path/to/linux --seeds data/seed_commits_100.csv \
    --doc-db data/doc_vectors --code-db data/code_index.sqlite \
    --env config/llm.env --out data/outputs_100
```

## 与论文的关键差异

1. **LLM**：DeepSeek-V4-Flash-0731（论文用 Claude Sonnet 4），提示词结构一致
2. **向量库**：numpy 自实现替代 Chroma（检索语义等价）
3. **AST 检索**：tree-sitter 自建索引替代 Weggli（论文声明可替换）
4. **嵌入**：本地运行 bge-large-en-v1.5（同款模型），阈值 0.15（本地分布调优）
5. **成本**：约 $2.10 vs 论文 $164.73（1.3%，见 Table 9 复现）

详见 `REPRODUCTION_REPORT.md`。
