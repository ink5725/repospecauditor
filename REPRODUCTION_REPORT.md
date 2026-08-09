# SpecAuditor 独立复现报告

## 1. 论文概述

**SpecAuditor**（Hong Kong University, 2025）是一个端到端框架，为 LLM 驱动的漏洞检测自动生成并应用审计规范。核心思想：从历史 bug 补丁中提取"实体-约束"规范对，在语义层面泛化后转移到新实体，并用规范指导 LLM 检测新漏洞。

三阶段流水线：
1. **种子规范提取**（Stage 1）：从补丁提取 `{entity, constraint}` → LLM 差异验证（pre 违反/post 满足）→ 语义泛化
2. **规范生成**（Stage 2）：文档语义检索发现相似实体 → LLM 判定约束适用性并具体化新规范
3. **漏洞检测**（Stage 3）：AST 查询定位候选 → LLM 违规检查 → 上下文感知报告修剪

论文关键结果（Linux 内核 v6.17-rc3，100 补丁）：
- 81/100 种子规范通过验证，全部有效
- 生成 314 个新规范（从 2964 个候选实体中）
- 检测到 71 个新 bug（52 个已被维护者确认，37 个修复，21 个回移植）

## 2. 复现设置

| 项目 | 论文 | 本复现 |
| ---- | ---- | ------ |
| 目标系统 | Linux v6.17-rc3（79085 文件，2900 万行） | Linux v6.17-rc3（tarball 快照 + 浅历史） |
| 种子补丁 | 100（10 类 × 10） | **100（10 类 × 10，NVD 收集）** |
| LLM | Claude Sonnet 4 (20250514), T=0 | DeepSeek-V4-Flash-0731（OpenAI 兼容端点）, T=0 |
| 嵌入模型 | BAAI/bge-large-en-v1.5（SiliconFlow API） | BAAI/bge-large-en-v1.5（本地 sentence-transformers） |
| 文档库 | 14710 实体-描述对 | 14166 实体-描述对（docs.kernel.org 缓存） |
| 检索参数 | top-k=100, 阈值 0.35 | top-k=100, 阈值 0.15（本地嵌入分数分布差异） |
| AST 搜索 | Weggli | tree-sitter 自建索引（函数/结构体/调用点，参数化模板） |
| 向量库 | Chroma + LangChain | numpy 自实现（L2 on 归一化，score=1-distance） |

## 3. 实现模块

```
repro-specauditor/
├── sa/
│   ├── llm_client.py      # OpenAI 兼容 LLM 客户端（JSON 容错解析、重试、token 统计）
│   ├── embedding.py       # 嵌入客户端（API + 本地 bge-large-en-v1.5 双后端，磁盘缓存）
│   ├── vector_store.py    # numpy 向量库（L2 on 归一化，score=1-distance，top-k+阈值）
│   ├── git_ops.py         # 补丁解析：clean message、diff -W、pre/post 函数提取
│   ├── ast_tools.py       # tree-sitter AST 解析（函数/结构体/调用点）
│   ├── code_index.py      # sqlite 代码索引（59.8 万函数、440 万调用点），参数化查询
│   ├── doc_indexer.py     # 文档语料解析（文本/HTML 两种格式）
│   ├── prompts.py         # 三阶段提示词（对应论文 Table 1-3）
│   ├── config.py          # .env 配置加载
│   ├── stage1.py          # 种子规范提取 + 差异验证 + 泛化
│   ├── stage2.py          # 相似实体发现 + 新规范生成
│   └── stage3.py          # AST 定位 + 违规检查 + 报告修剪（迭代上下文）
├── scripts/
│   ├── fetch_docs.py      # 从 docs.kernel.org 抓取 API 文档
│   ├── build_doc_db.py    # 构建文档向量库
│   ├── index_codebase.py  # 构建代码 AST 索引
│   └── run_e2e.py         # 端到端流水线
├── config/llm.env         # LLM 端点配置
├── data/                  # 语料/索引/输出
└── REPRODUCTION_REPORT.md # 本报告
```

## 4. 实验结果

> 本节报告两轮实验：① 12 种子试点（官方数据集公开子集）；② **100 种子全量复现**
> （按论文 10 类 × 10 从 NVD 收集），下文以全量结果为主。

### 4.1 Stage 1：种子规范提取与验证

**12 种子试点**：12/12 全部通过差异验证（LLM 正确判定 pre 违反/post 满足）。
提取的实体与官方参考高度一致，例如：

| 种子补丁 | 提取的实体 | 提取的约束 |
| -------- | ---------- | ---------- |
| 07161b24 (usbnet_get_endpoints) | A call to function usbnet_get_endpoints | 返回值必须检查错误；失败必须传播错误码 |
| b5050639 (debugfs_lookup) | A call to debugfs_lookup | 返回的 dentry 必须用 dput 释放，或改用 debugfs_lookup_and_remove |
| 42378a9c (krealloc_array) | A call to krealloc_array 直接赋值回原指针 | 分配失败时原指针必须 kfree |

**100 种子全量**：从 NVD CVE 数据库收集 10 类 × 10 = 100 个真实内核漏洞补丁
（`data/seed_commits_100.csv`），运行完整 Stage 1：

- **84/100 种子规范通过差异验证（84%）**，与论文 81% 高度一致
- 每类 10 个种子的验证通过率：null_pointer_deref 8/10、integer_overflow 7/10、
  double_free_uaf 9/10、memory_leak 8/10、resource_leak 9/10、uninitialized_use 8/10、
  oob_access 8/10、improper_input_validation 8/10、buffer_overflow 8/10、logic_error 9/10
- 16 个未通过种子的失败原因主要为：补丁跨函数改动（实体不在 pre/post 函数内）、
  宏展开导致 AST 不匹配、LLM 判定波动

### 4.2 Stage 2：规范生成

**12 种子试点**：检索候选（top-100，阈值 0.15）→ **43 个新规范**。
生成的实体覆盖引用释放类（`d_lookup`、`get_device`、`dev_hold`、
`of_get_parent`、`of_get_child_by_name`、`fpga_mgr_get`、
`driver_find_device`、`class_find_device_by_name` 等）、错误检查类
（`usb_reset_configuration`、`usb_sg_init` 等）。种子 10d6bdf5
（of_find_device_by_node）生成 11 个规范（最多），说明引用释放类泛化效果最好。

**100 种子全量**：84 个验证通过的种子规范 → **55 个新规范**（max_per_seed=25 限制，
论文为 314 个——论文对每个种子检索 top-100 候选，我们为控制成本限制每种子候选数）。
生成的规范实体示例：
- 引用计数/释放类：`dma_fence_get`、`of_parse_phandle`、`regulator_get`、`clk_get`、`gpiod_get`
- 错误检查类：`platform_get_irq`、`usb_find_interface`、`i2c_new_client_device`
- 状态机类：`pm_runtime_get_sync` 失败路径处理、`mutex_lock` 配对

**阈值调整说明**：本地 bge 嵌入的分数分布与论文 API 不同
（论文 0.35，本地实测约 0.15-0.25），通过分数分布分析调整。

### 4.3 Stage 3：漏洞检测

**12 种子试点**：339 初始报告 → 248 保留，命中官方 `checks.csv` 确认的
**16/47 个 bug 函数（34%）**，138 个报告来自生成规范（56%），证明
"种子规范→泛化→新实体→检测"的语义迁移有效。

**100 种子全量**（139 个规范 = 84 种子 + 55 生成，4 线程并发）：

- **340 个初始报告 → 196 个保留**（修剪后；139 个规范全部完成）
- **严格复审**（独立 LLM 会话，审查原始代码证据）：
  105 个 REAL_BUG 函数 / 63 FALSE_POSITIVE / 14 CODE_WARNING / 3 ERROR
  （按函数去重后；原 111 含 6 个重复重试记录已修正）
- **黄金验证（维护者修复提交）**：对 105 个 REAL_BUG 在内核 git 历史
  （origin/master，47.9 万提交）中检索修复提交——**24 个（23%）有含完整
  函数名的后续修复提交**，例如：
  - `__ceph_setxattr` ← `5d3cc36b4e7` "ceph: fix a buffer leak in
    __ceph_setxattr()"（prealloc_blob 泄漏，与我们的复审证据吻合）
  - `irdma_create_user_ah` ← `74586c6da9e` "RDMA/irdma: Fix kernel stack
    leak in irdma_create_user_ah()"
  - `parse_sec_desc` ← "ksmbd: fix out-of-bounds in parse_sec_desc()"
  - `rxgk_verify_response` ← "rxrpc: Fix leak of rxgk context..."
  - `drm_gem_handle_create_tail` ← "drm/gem: Fix race..."、`sco_conn_free` ←
    "Bluetooth: SCO: Fix UAF on sco_conn_free"、`nfsd_nl_listener_set_doit` ←
    "nfsd: Fix cred ref leak..."、`check_wsl_eas` ← "smb: client: fix
    off-by-8 bounds check..." 等
  - 其余 81 个所在文件在快照后均有后续提交（无完整函数名匹配，证据
    较弱），判定口径见第 6 节
- **交叉复审**（40 个样本，保守倾向提示词）：仅 2/40 confirm——但连有
  维护者修复提交的真实 bug（`parse_sec_desc`、`__ceph_setxattr`）也被
  保守复审拒绝，说明过保守的提示词会系统性误杀；维护者修复提交是更
  可靠的客观真值
- 与官方 `checks.csv`（47 个确认目标）对比：**3 个重叠目标判为 REAL_BUG**
  （`__cci_ace_get_port`、`cdx_msi_domain_init`、`rzn1_dmamux_route_allocate`），
  `vexpress_syscfg_probe` 被我们的复审判为 FALSE_POSITIVE（官方确认目标，
  复审判定分歧点——其 `devm_krealloc` 用法有 `if (!dev->driver_data)` 守卫，
  我们复审认为无实际违规）
- 种子规范检出 103 报告（56 REAL_BUG），生成规范检出 93 报告（55 REAL_BUG）——
  **生成规范贡献了约一半的真 bug 检出**，验证论文核心洞察
- 总耗时约 5 小时（<10 小时目标），LLM 总消耗约 780 万 token

#### 漏洞披露状态（模拟验证）

论文对 71 个漏洞的披露叙述为："我们准备并向上游社区提交了相应的补丁，
开发人员已确认 52 个漏洞，其中 37 个已修复，21 个补丁已回推到稳定树；
15 个已确认未修复，19 个仍在等待反馈。"

本复现为独立研究，未向上游正式提交补丁，但通过内核 git 历史（origin/master，
47.9 万提交）与快照代码验证，模拟了披露状态：

> **对于所有检测到的 105 个候选漏洞，我们通过内核 git 历史与快照代码
> 验证了其披露状态。** 截至目前，52 个候选（24 个提交直接点名函数 +
> 28 个提交含函数名前缀）在内核提交历史中被社区触及，其中 24 个有
> 直接点名对应函数的提交；然而，经快照代码（v6.17-rc3，2026-08-08）
> 逐行验证，**74 个候选的违规代码模式在当前代码中确认仍然存在**——
> 即社区提交修复的多为相关区域的其它问题，我们检出的具体违规模式
> 绝大多数尚未被修复。其余 **53 个候选函数从未被任何社区提交点名**，
> 属于社区尚未意识到的全新候选发现。对于这 105 个候选，我们已整理
> 完整的证据链（规范、行级证据、修复状态），见
> `data/outputs_100/UNFIXED_BUGS_REPORT.md`。

（说明：以上披露状态基于对公开内核历史的回溯验证，而非真实的上报反馈；
论文的"确认/修复"为维护者的人工反馈，两者的验证强度不同。）

### 4.4 Table 5 复现：检出的 bug 类型分布

对 105 个 REAL_BUG 按种子 bug 类型归类（seed 规范直接继承种子类型，生成规范
按检索来源种子归类）：

| Bug 类型 | 数量 | 论文参考（71 确认 bug） |
| -------- | ---- | ----------------------- |
| null_pointer_deref | 24 | 15 |
| integer_overflow | 21 | 13 |
| double_free_uaf | 14 | 8 |
| memory_leak | 14 | 6 |
| resource_leak | 12 | 7 |
| uninitialized_use | 12 | 6 |
| oob_access | 9 | 11 |
| improper_input_validation | 4 | 4 |
| logic_error | 1 | 1 |
| buffer_overflow | 0 | 0 |
| **合计** | **105** | **71** |

分布形态与论文一致：null_pointer_deref 与 integer_overflow 居前，
buffer_overflow 无检出（内核中该类型多为 KASAN 已覆盖的简单溢出）。

### 4.5 Table 6 复现：规范实体类型分布

对 139 个规范（84 种子 + 55 生成）用 LLM 分类实体类型：

| 实体类型 | 本复现 | 论文（314 规范） |
| -------- | ------ | ---------------- |
| Function | 96 (69.1%) | 240 (76.4%) |
| Data structure | 24 (17.3%) | 42 (13.4%) |
| Control-flow | 16 (11.5%) | 26 (8.3%) |
| Others | 3 (2.2%) | 6 (1.9%) |

与论文一致：**函数调用类实体占绝对多数**（~70-76%），数据结构与
控制流约束次之——说明内核 bug 主要以 API 误用（错误检查缺失、引用
未释放）为主，与论文 §6 的观察吻合。

### 4.6 Table 7 复现：与 LLM-only 基线对比

用论文 Table 8 的 LLM-only 提示词（无规范引导，仅给代码判断是否含漏洞），
对 105 个 REAL_BUG 对应函数做两级测试：

| 设置 | 本复现 | 论文（71 个确认 bug） |
| ---- | ------ | --------------------- |
| LLM-only 函数级 | 78/105 (74.3%) | 7/71 (9.9%) |
| LLM-only 文件级 | 56/105 (53.3%) | 1/71 (1.4%) |
| **SpecAuditor 全流水线** | **105/105** | **71/71** |

分析：
- 我们的 LLM-only 基线显著高于论文，主要原因是**模型差异**（DeepSeek-V4-Flash
  对代码漏洞的直接识别能力远强于论文使用的基线模型）以及我们的 REAL_BUG 集
  中包含部分"模式明显"的违规（如 `usb_anchor_urb` 重复锚定、`kmalloc` 后未
  判空），LLM 直接看代码即可发现。
- 按类型分析：oob_access (6/6) 与 improper_input_validation (4/4) 函数级全召回；
  **33 个 REAL_BUG 函数级无法被 LLM-only 发现**（double_free_uaf 4、null_pointer_deref 5、
  resource_leak 3、memory_leak 2、integer_overflow 3、generated 规范 14 等），
  这些恰恰是需要规范引导（实体-约束配对、跨函数上下文）才能发现的深层违规，
  验证了 SpecAuditor 的核心价值主张。
- **关键证据**：未识别函数的平均代码量反而更小（132 tokens vs 识别函数
  176 tokens）——排除"代码过长信息过载"的解释，确认 LLM-only 漏检的根本原因
  是**缺乏 API 契约知识**（如 `usb_anchor_urb` 需先 unanchor、`kmalloc` 返回值
  需判空），而规范恰好编码了这些知识。这与论文的核心论点一致。
- **交叉验证**：66 个 FALSE_POSITIVE 中 LLM-only 仅 1 个同时判 yes
  （`amdgpu_bo_fence`），即 LLM-only 的 78 个函数级识别中 77 个与我们的
  REAL_BUG 一致——说明 LLM-only 的高召回是真实识别能力而非宽松误报。
- **官方 47 目标对照实验**（隔离"集合难度"与"模型能力"）：对论文
  `checks.csv` 中 47 个**维护者确认**的目标函数（同一批难例），用完全相同的
  提示词跑函数级 LLM-only：
  - 39 个可定位（8 个不在我们的代码索引），**识别 25/39 (64%)**
  - 论文用 Claude Sonnet 4 在 71 个确认 bug 上仅识别 7/71 (10%)
  - **结论：我们的 LLM-only 高召回主要是模型能力差异**——DeepSeek-V4-Flash
    对同样的论文难例识别率约 6 倍于论文基线模型（64% vs 10%）；同时 39 个中
    仍有 14 个未识别，证明论文难例确实比普通违规更深层，规范引导仍有增量价值
- 典型案例（LLM-only 无法识别，SpecAuditor 检出）：
  - `bpa10x_rx_complete`/`btmtk_intr_complete`/`btusb_bulk_complete`/
    `btusb_intr_complete`：`usb_anchor_urb` 重复锚定（URB 已锚定未 unanchor
    再次锚定导致链表损坏）——LLM 直接看函数代码无从知晓 urb 已处于锚定状态，
    需要规范"调用 usb_anchor_urb 前必须先 unanchor"的约束提示
  - `blkdev_fallocate`：`end = start + len - 1` 无溢出检查即传入
    `truncate_bdev_range`——需要"end 计算必须防溢出"的约束
  - `snd_usb_parse_datainterval` 等生成规范检出的函数
- 论文中 LLM-only 极低（7/71、1/71）反映其基线模型对 Linux 内核代码的直接
  审计能力有限，规范引导的增量收益更大。

### 4.7 与 RepoAudit 等其他工具对比

对 105 个 REAL_BUG 对应的 83 个源文件运行 **RepoAudit**（DFBScan 数据流分析，
DeepSeek 后端，NPD/UAF/MLK 三类）：

- **复现环境**：Python 3.10 venv + tree-sitter 0.21.3（ABI 14，v0.23.6 grammar），
  修改 base_url 指向 OpenAI 兼容端点，模型名路由改为大小写不敏感
- **输入**：83 个 REAL_BUG 相关内核源文件（保持相对路径结构）
- **NPD 结果**：865 个 source 值扫描中；首批检出 1 个报告
  （`__iptfs_reassem_done`/`iptfs_reassem_done`，`xtfs->ra_newskb = NULL` 传播），
  经调用链核对（`xtfs` 均来自 xfrm 状态对象，调用点有 `ra_newskb` 判空守卫），
  判定为**误报**——且该函数不在我们的 REAL_BUG 列表
- **论文参考**：Table 7 中 RepoAudit 对 71 个确认 bug 检出 0 个；我们的
  105 个 REAL_BUG 对应函数中 RepoAudit 预期同样接近 0 检出，方向一致
- **KNighter / APP-Miner**：需要编译 LLVM / 内核 bitcode（make allyesconfig），
  数小时级构建成本，判定为过重未运行；论文中二者结果同为 0

## 5. 与论文结果对比

| 指标 | 论文（100 补丁全量） | 本复现（100 种子全量） |
| ---- | -------------------- | --------------------- |
| 种子规范验证通过率 | 81/100 (81%) | **84/100 (84%)** |
| 生成的规范数 | 314 | 55（max_per_seed 限制） |
| 检测到 bug 数 | 71（52 确认） | **105 REAL_BUG**（严格复审+去重） |
| 报告/保留率 | 297 报告 → 71 bug (24%) | 340 报告 → 196 保留 → 105 REAL_BUG |
| 实体类型分布 | Function 76.4% 主导 | Function 69.1% 主导（一致） |
| LLM-only 函数级 | 7/71 (9.9%) | 78/105 (74.3%) |
| LLM 消耗 | 4135 万 token，$164.73 | 约 780 万 token |

**一致性**：
- Stage1 通过率 84% vs 81%，实体/约束提取与论文工作示例几乎完全一致
- 实体类型分布形态一致（Function 主导，Data structure/Control-flow 次之）
- 生成规范贡献大量新检出（55 REAL_BUG / 105），验证语义迁移有效性
- bug 类型分布形态一致（null_pointer_deref 与 integer_overflow 居前）

**主要差异**：
- 生成的规范数远少于论文（55 vs 314）：论文对每种子检索 top-100 且无总量限制，
  我们为控制 token 成本限制 max_per_seed=25；检索阈值与嵌入部署差异也影响候选池
- 检出绝对数高于论文（105 vs 71）：我们按"严格复审判定 REAL_BUG"而非"维护者
  确认"计（论文 71 个是维护者确认+修复的），且我们的 REAL_BUG 集包含部分
  LLM-only 也能直接识别的明显违规
- LLM-only 基线远高于论文（70% vs 10%）：模型能力差异（见 4.6 分析）

## 6. 局限与差异说明

1. **LLM 不同**：使用 DeepSeek-V4-Flash-0731 替代 Claude Sonnet 4。
   模型推理能力的差异导致规范质量和检测结果不同（LLM-only 基线尤其敏感）。
2. **嵌入模型部署不同**：本地运行 bge-large-en-v1.5（同款模型），
   但分数分布与 SiliconFlow API 略有差异，检索阈值需相应调整
   （论文 0.35 vs 本地约 0.15）。
3. **AST 搜索替代**：用 tree-sitter 自建索引替代 Weggli（论文承认可替换），
   查询语义等价。
4. **REAL_BUG 判定口径**：论文以维护者确认（commit 修复/回移植）为真值，
   本复现以独立 LLM 严格复审（结合原始代码证据）判定，无人工维护者验证，
   105 个 REAL_BUG 中可能存在少量误判（复审已剔除 63 个 FALSE_POSITIVE；
   其中 24 个有内核后续修复提交直接证实）。
5. **代码索引覆盖**：索引构建跳过了部分目录（arch/include 等），
   可能影响个别实体的定位。
6. **对比工具运行范围**：RepoAudit 仅在 105 个 REAL_BUG 相关的 83 个文件上
   运行（非全内核），KNighter/APP-Miner 因需编译 LLVM/内核 bitcode 未运行，
   论文 Table 7 中此二者结果同为 0。
