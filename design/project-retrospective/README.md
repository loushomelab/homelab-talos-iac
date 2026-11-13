# HOM-5：K8s 首轮项目复盘

复核日期：2026-11-06（上海）；PR 状态快照截至 2026-11-05 16:56:58 UTC。
本报告供 HOM-11 验收后编写项目最终总报告，覆盖 HOM-2/3/4/6/7/8/9/10 全部成果。

**八项前置任务均已按各自范围验收，不等于改动已进入 main 或运行风险已修复。**
五个交付 PR 均 OPEN、非 draft、未合并，当前各三项 CI 检查成功。main 仍没有
#137 的离线入口和 #164 的 schema 门禁；HOM-7 仍只是设计。监控已有就绪副本，
但没有端到端数据与灾备验收；PBS 有近期成功备份，但可恢复性仍未证明。

后续可审查待办见 [follow-ups.md](follow-ups.md)，结构化 PR/任务快照见
[pr-status.json](pr-status.json)。待办是建议清单，本轮未创建或启动新任务。

## 证据与交付索引

本轮读取各 issue 当前描述、扫描评论线程后展开实际交付，并读取 HOM-11 对相关阶段的
验收记录；同时审阅 PR 文件、设计/runbook 与验证记录。历史测试结果标注为原任务证据，
本轮没有重跑这些代码测试，也没有重新访问集群/PVE/PBS/NAS。

| 任务 | 实际交付与验收证据 | 边界与状态 |
| --- | --- | --- |
| HOM-6 | 2026-10-29 只读架构分析：3 CP/3 Worker、Talos 1.13.8、Kubernetes 1.36.0；配置入口、基线差异、验证问题和后续排序 | done；纯分析无 PR；当时 6/6 节点、39/39 App 健康不能外推为持续健康 |
| HOM-2 | 明确首改范围；提前提交 #137 初版 `aaa116e`，18 项回归及禁网入口通过 | done；与 HOM-3 同一交付，不重复计算两套工具 |
| HOM-3 | [#137](https://github.com/loushomelab/homelab-talos-iac/pull/137) 在初版上修补未引用模板/无扩展名 Kustomization 扫描；21 项禁网回归；31 App、107 配置源、7 渲染检查通过 | done；YAML、重复键、资源基本结构；应用、Chart、同步与 CI 未变 |
| HOM-4 | 独立验收 #137 精确 head；系统禁网与畸形 kubeconfig 下 21/21 回归、7 个预期资源身份、9 个 ConfigMap 文件键和内容匹配；故障注入非零并定位来源 | done；真实 Kustomize 正常路径、受控 stub 渲染故障；Task 未安装，使用等价直接命令；无需集群回退 |
| HOM-7 | [#138](https://github.com/loushomelab/homelab-talos-iac/pull/138)：39 App/42 source/57 workload 映射，按 source 验证设计；43 个模拟 CLI 进程覆盖正常/拒绝/坏输入 | done；7 个 exit 0、35 个 exit 1、1 个 exit 2；真实工具 spy 调用为 0；不是生产验证器 |
| HOM-8 | [#139](https://github.com/loushomelab/homelab-talos-iac/pull/139)：10 月 NAS/S3 准入、分组件恢复顺序、回退边界、新指标/profile/历史对象功能验收 | done；当时继续维护；固定 Chart 渲染与 pre-commit 通过；configs 旧递归 dry-run 失败如实保留，未执行恢复 |
| HOM-9 | [#163](https://github.com/loushomelab/homelab-talos-iac/pull/163)：依赖图、实际宿主/API/DNS/卷/PBS 故障域、Day-0 屏障、恢复分流、RPO/RTO 待确认；38 项只读查询 exit 0 | done；文档/JSON/链接/凭据模式检查与 pre-commit 通过；只有取证与 runbook，无恢复演练 |
| HOM-10 | [#164](https://github.com/loushomelab/homelab-talos-iac/pull/164)：共用分类/渲染，Kubernetes 1.36.0 + 27 种 GVK 锁定 schema，禁网 48 项回归、175 validated/0 skipped/0 failed | done；缺失 schema 显式失败；不覆盖完整 CRD 运行语义、Helm opaque values 或真实恢复 |

### PR 精确版本与当前状态

仓库均为 `loushomelab/homelab-talos-iac`。表中版本是本轮 GitHub 查询及 fetch 核对的 head；
CI 成功指 YAML、kubeconform、Renovate 三个现有 job，不代表项目全部风险闭合。

| PR | 分支 | 精确 head | 状态 / CI |
| --- | --- | --- | --- |
| #137 | `mika/HOM-2-offline-validation` | `4309f53fa8afa1dd70d242b4a55122054eea0e53` | OPEN / 3 SUCCESS |
| #138 | `mika/HOM-7-safe-delivery-design` | `2ee64a9fd209abe490f3157f77183f805c4aa517` | OPEN / 3 SUCCESS |
| #139 | `mika/HOM-8-monitoring-recovery` | `894ace8c0a65c2c3a25a1c388188e1f83351cded` | OPEN / 3 SUCCESS |
| #163 | `mika/HOM-9-day0-recovery` | `2a6749d9a7adee9bdf9687dbd2c4e43fcce10614` | OPEN / 3 SUCCESS |
| #164 | `mika/HOM-10-schema-alignment` | `ccd2967373b51a8b2f221ee06aded06463bd4674` | OPEN / 3 SUCCESS |

Multica 对 HOM-2/3/4/7/8/9/10 的 PR 关联列表仍全部为空；不能据空表推断没有 PR，
也不能据 issue done 推断已合并。本轮以交付评论的明确 URL 经 `gh pr view` 核对，
没有反复改标题或重配集成。关联原因尚未查明，必要时由 workspace owner 专项排查。

## 基线与依赖复盘

10 月 HOM-6 的本地 `ee08022` 落后于当时远端和线上 `21854fdf`，
证据支持“本地副本陈旧”，不支持“线上偏离 main”。HOM-2/3/7/8 从当时远端新建独立分支。
11 月 HOM-9/10 与本报告基线是当前远端 main
`1cc7690082058c603632709dc259136221bd21ab`，不能继续沿用 10 月基线。

#164 的父提交 `1e02a15c59e4f57a47c95e1bc255159d34efae90` 合入了：

- 当前 main `1cc7690082058c603632709dc259136221bd21ab`。
- 未合并 #137 的精确 head `4309f53fa8afa1dd70d242b4a55122054eea0e53`。

其后只有 HOM-10 增量 `ccd2967373b51a8b2f221ee06aded06463bd4674`。
本轮 `git merge-base --is-ancestor origin/pr-137 origin/pr-164` 退出 0，确认祖先关系。
完整 #164 diff 含 #137 五个工具文件；不能当成独立 PR 盲目合并。

未来先审查/合入 #137，再处理 #164；尽量保留已验收依赖的祖先关系。
若 #137 squash/rebase 合并，须在新 main 重放 HOM-10 增量，检查冲突、分类和 schema
一致性，再重新禁网验证与运行相关回归，不能只改 PR base 就假定等价。
即使保留祖先关系，也应核对届时 main/Chart/GVK 的漂移。
#138/#139/#163 是独立文档交付；它们之间的链接是设计引用，不证明已合并或实施。
本报告独立基于 main，只增加复盘文档，无需先合并这些 PR 才能审查。

## 校验入口的经验与边界

输入必须按真实生成方式分类：普通 Kubernetes manifest 直接检查；Homepage 的应用模板
及 generator 文件是构建输入，先用现有 Kustomize 渲染，再检查输出；`kustomization.yaml`
和无扩展名 `Kustomization` 是构建说明。对未分类或未引用 YAML 显式报告并拒绝，
不能忽略整个 configs 来取得成功。兼容既有 Homepage，不迁移或扩大 Kustomize。

#137 在无需 kubeconfig、API discovery 或可达集群的前提下检查 YAML/基本结构，
拒绝远程构建输入并隐藏解析器/渲染器配置正文。正常输入 exit 0；语法、结构、引用、
渲染失败及损坏生成资源必须非零且指出来源。HOM-4 独立故障注入验证了这些约定。
工具、Python/PyYAML、kubectl 内置 Kustomize、Node/Task 等仍须预装；离线不等于无依赖。

#164 将有网络的显式 schema 准备与禁网校验分开。Kubernetes schema 来自
`yannh/kubernetes-json-schema` 的固定 commit，并非 Kubernetes 项目直接发布；
CRD schema 来自对应官方项目的固定 commit。锁文件记录版本、源与输出 SHA256，
不使用浮动目录或远程 fallback。覆盖原生 12 种及 Argo CD、External Secrets、Traefik、
MetalLB、cert-manager、Grafana Operator 的 15 种 GVK，共 27 种。

175 是检查次数：31 App + 125 配置源 + 12 bootstrap + 7 Homepage 渲染，
其中 6 个源对象再次作为渲染输出检查；不能写作 175 个独立部署对象。
相比 #137 的 107 配置源，main 内容与检查范围均已变化，不能把计数增加直接当回归或新增部署。
未知 GVK 可以计入 skipped/missing_schema，但整体命令仍必须失败；skipped 不代表准予通过。
原任务验证了缺失/损坏 schema、未知组/版本、错误字段类型、未知字段、渲染错误及脱敏诊断。

schema 通过不覆盖 CEL、准入 webhook、跨资源引用、opaque Helm values、完整 Helm 工作负载
渲染或运行语义；锁定仓库声明版本也不是实时集群 CRD 版本取证。旧 PR 的绿色 CI 仍使用
旧版 schema 策略，不能倒推有 #164 的覆盖。详见
[#137 VALIDATION](https://github.com/loushomelab/homelab-talos-iac/blob/4309f53fa8afa1dd70d242b4a55122054eea0e53/VALIDATION.md)
与 [#164 VALIDATION](https://github.com/loushomelab/homelab-talos-iac/blob/ccd2967373b51a8b2f221ee06aded06463bd4674/VALIDATION.md)。

Healthy、YAML 语法通过、client dry-run、rollout 成功各证明不同部分，均不能单独证明交付。
运行改动还须核对每个 source 的精确 Git SHA/Chart 版本、有序 revisions、父配置提交与
child spec、实际修改字段、真实 workload/generation/容量和功能响应。不能用本仓库 SHA
替代外部 Git 或 Helm 版本；302 登录页、0/0 就绪和历史曲线都不能证明功能完成。

## 11 月证据对历史结论的修正

以下最新运行结论来自 HOM-9 在 2026-11-05 16:22 UTC 起执行的带时间只读查询
（上海 11-06），不是 HOM-5 新的现场观测。完整记录见
[#163 observed.json](https://github.com/loushomelab/homelab-talos-iac/blob/2a6749d9a7adee9bdf9687dbd2c4e43fcce10614/design/day0-recovery/observed.json)。
各次 GET 非原子快照，不能保证此后持续健康。

| 主题 | 历史证据 | 较新证据及不能外推的部分 |
| --- | --- | --- |
| 监控 | HOM-8 在上海 10-30：Alloy/Mimir/Pyroscope 维护零副本，Mimir 查询与 Pyroscope ready 503，旧 NAS 不可达 | HOM-9：Mimir/Pyroscope 有 ready 副本、Alloy 3/3，内置 pyroscope-alloy 仍 0；不能继续声称仍在维护，也不能声称新数据、历史完整性、S3/NAS 健康已验收 |
| 监控设计 | #139 采用旧 Chart 及维护字段，规定 G0–G7 门禁与分阶段恢复 | 当前 main 已变更；旧建议是参考设计，后续操作先重新对齐版本/字段，不能重放旧维护 selector 或把本复盘当作停采授权 |
| PBS | HOM-6 只读到每日 02:00 的配置声明，早期个人笔记包含更旧失败与拓扑 | HOM-9 核实六 VM、PG CT151/152 的上海 11-05 凌晨 snapshot 与成功 task；未取得完整磁盘/PG WAL 覆盖、校验/隔离恢复及 NAS 外副本 |
| 宿主 | HOM-6 只有 Terraform 三对 CP/Worker 分散的声明 | HOM-9 实测三对确实跨 r720/1920x/3960x；不证明 Ceph、网络、电源等共同故障域已隔离 |

没有查明监控此次恢复的完整审批链，也未重新进行 HTTP、认证 S3 或 NAS pool/磁盘检查；
不能将别的工作造成的运行变化归功于 HOM-7/8/9 的文档 PR。
不能因过去缺证据便断言备份不存在，也不能因有 snapshot/task OK 便声称可恢复。
每日调度约 24h 不是实测 RPO，当前没有实测 RTO 或已确认的业务损失预算。

## 尚未解决的具体风险

| 风险 | 证据与影响 | 后续项 |
| --- | --- | --- |
| 危险入口仍可调用 | 本轮 main 的 `Taskfile.yaml` 仍统一 HEAD patch/prune、猜测 workload 并吞掉 rollout 失败；clean:pods/AGENTS mutation 示例未隔离；#138 只加设计 | F2 |
| API 单入口 | 仓库默认 cp-01，HOM-9 kubeconfig 指向 cp-03；三个 CP readyz 成功不证明 VIP/自动切换 | F5 |
| DNS 同宿主 | 两个 CoreDNS ready endpoint 同在 cp-01；r720 失效会同时失去两个现有端点，影响是拓扑推断、未演练 | F5 |
| 数据与交付控制面共宿主 | PG151/152、Redis153、PBS154、TF agent200、runner201 与 cp-03/worker-03 在 3960x；Ceph rootfs 不证明底层存储已隔离 | F3/F5 |
| 卷副本集中 | pulse 三副本都在 worker-03；dind 卷为 worker-01 两个、worker-02 一个；其余五卷各跨三 worker；7 卷 healthy 不等于全部跨三物理域 | F6 |
| PBS chunks 单 NAS | PBS datastore 经 CT154 数据盘 raw→NFS→单 NAS；数据盘 backup=0，当前 job 排除 PBS 自身；PBS 系统盘恢复不包含 chunks | F3 |
| 恢复保障缺证据 | 独立 etcd snapshot 保管、PBS verify/隔离恢复、PGDATA/WAL/tablespace 与一致点、NAS 外副本、集群外凭据/制品取回均未闭合 | F3/F4/F7 |
| 监控持久性与端到端验收 | Ready 不代表真实新 metrics/profile 和 S3 落块；Mimir RF=1、相关组件无 PVC，不能因多 zone 推断三副本耐久 | F8 |
| 冷启动屏障 | root/tier 有 wave 0/10/20/25/30/40，但无 Application health override；自动 selfHeal/prune 可能抢跑，Day-0 引导存在外部信任根依赖 | F7 |
| schema 持续覆盖 | #164 尚未合并，main 仍用 1.32.0/ignore-missing-schemas；依赖升级需更新锁和证据，CRD 准入语义仍在离线范围外 | F1/F9 |

详细故障域和恢复分流以
[#163 README](https://github.com/loushomelab/homelab-talos-iac/blob/2a6749d9a7adee9bdf9687dbd2c4e43fcce10614/design/day0-recovery/README.md)、
[#163 recovery](https://github.com/loushomelab/homelab-talos-iac/blob/2a6749d9a7adee9bdf9687dbd2c4e43fcce10614/design/day0-recovery/recovery.md)
为准。这里只列证据支持的缺口，不把拓扑推断写成已发生的故障。

## 本轮交付验证与回退边界

本报告只新增 `design/project-retrospective/`，不改变 Taskfile、AGENTS、CI、应用、Chart、
Terraform 或运行配置。原 Talos/PVE 工作副本及上层仓库已有修改均保留。
文档范围的验收是来源、精确版本/依赖、链接、计数、敏感信息及仓库静态检查；
不为文档 PR 触发 Argo 同步或声称集群已部署本 PR SHA。

HOM-4 给出的工具回退是经 PR 逆序撤销 #137 两个工具提交，无需集群回退；
#164 若已采用，须同时审查其增量对入口/依赖的关系，不能盲目撤销依赖 merge。
本报告的回退只需撤销文档提交。真正部署/恢复的回退要有具体计划；Git revert
不能撤销 S3 compaction、数据库写入或已丢失的临时 WAL/队列。

本轮实际验证（上海 2026-11-06）：

- `pre-commit run --all-files`：八项全部 Passed，含 YAML、私钥、冲突与 Renovate 检查。
- `git diff --check`、`git diff --cached --check`：退出 0。
- 本地 Python 复核：JSON 可解析、八项前置任务为 done、五个 head 与 fetched refs 相等、
  15 项已有 CI 为 SUCCESS、#137 为 #164 祖先；12 个文档链接有效，固定 SHA 的 blob
  经 `git cat-file -e` 核实，本地链接存在；Markdown 表格列数/围栏及凭据模式检查通过。
- 本轮只改文档，不运行旧 main 的 client dry-run 或 task sync/clean:pods，不重复原代码回归。

本轮未创建备份、读取 Secret 值、改权限、合并、部署或执行故障/恢复演练。
复用经验在本目录整理，个人 Obsidian 仅检索未改写；其中旧 PBS 拓扑不作为当前事实。
HOM-5 交付至 in_review，由 HOM-11 复核后接续项目最终汇总；不代替成员对后续动作的批准。
