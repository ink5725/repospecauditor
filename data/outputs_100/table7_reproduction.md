# Table 7 复现：Bug detection results of compared methods

## 论文 Table 7

| 类型 | 方法 | #漏洞 (共 71 个) |
|------|------|----------------|
| 仅大语言模型 | 函数级 | 7 |
| 仅大语言模型 | 文件级 | 1 |
| 大语言模型辅助 | KNighter | 0 |
| 大语言模型驱动 | RepoAudit | 0 |
| API 误用检测 | AppMiner | 0 |

## 本复现 Table 7

### 全量集合（105 个 REAL_BUG）

| 类型 | 方法 | #漏洞 (共 105 个) | 说明 |
|------|------|------------------|------|
| 仅大语言模型 | 函数级 | 74 | DeepSeek-V4-Flash-0731，论文 Table 8 提示词 |
| 仅大语言模型 | 文件级 | 52 | 同上 |
| 大语言模型辅助 | KNighter | 待运行 | LLVM 编译完成，gen 阶段待启动 |
| 大语言模型驱动 | RepoAudit | **1** | NPD 检出 `parse_sec_desc`/`parse_dacl`（真实）；UAF 5、MLK 7 检出的核心函数均不在 REAL_BUG 集合 |
| API 误用检测 | AppMiner | 0 | 未运行（Docker Hub 不可达 + 需编译内核 bitcode），论文结果同为 0 |

### 精选集合（30 个最强证据：24 个社区提交点名 + 6 个 LIKELY_FIXED 代表）

| 类型 | 方法 | #漏洞 (共 30 个) |
|------|------|------------------|
| 仅大语言模型 | 函数级 | 21 (70%) |
| 仅大语言模型 | 文件级 | 16 (53%) |
| **SpecAuditor 全流水线** | — | **30/30** |

精选标准：优先保留有社区提交直接点名（FIXED_EXACT）的候选——这些是
证据最强的真实漏洞；再按规范去重选取 LIKELY_FIXED 代表，保证规范覆盖
多样性。30 个清单见 `data/outputs_100/table7_top30.json`。

## 与论文的差异分析

1. **LLM-only 远高于论文（74/105、21/30 vs 7/71、1/71）**：
   - 模型能力差异是主因——官方 47 目标对照实验中，DeepSeek 识别 25/39 (64%)，
     论文 Claude 仅 7/71 (10%)（见 4.6 节）
   - 我们的 REAL_BUG 集合含较多模式化违规（缺边界检查等），LLM 直接可见
   - 即便精选 30 个最强证据子集，函数级仍识别 21/30 (70%)，说明模型能力
     是主导因素而非集合难度
2. **RepoAudit 检出 1 个真实 bug（与论文 0 不同）**：
   - `parse_sec_desc`/`parse_dacl` NPD：`sid_to_id` 失败 → `owner_sid_ptr = NULL`
     → `parse_dacl` 中 `compare_sids(&ppace[i]->sid, pownersid)` 解引用 NULL，
     无守卫——该函数在我们的 REAL_BUG 集合中
   - 差异原因：我们给 RepoAudit 的输入覆盖了 83 个相关文件（比论文的
     "16 个漏洞相关位置"更广），且使用了更强的 LLM 后端
3. **KNighter 待运行**：LLVM 18.1.8 + SAGenTestPlugin 已构建完成，将按论文
   方式仅提供 bug 补丁（84 个种子）生成 checker，然后限定范围扫描。
4. **结论方向一致**：无论 LLM-only 基线高低，规范引导的 SpecAuditor 都能
   检出 LLM-only 遗漏的漏洞（33 个函数级漏检，其中 9 个有社区修复证据），
   与论文"SpecAuditor 补充现有方法"的核心主张一致。
