# HOM-7：按 source 验证的安全交付入口设计

本 PR 交付设计、只读观测及隔离模拟。**现有 `task sync` 和 `task clean:pods`
仍含直接 mutation，尚未修复，不能按本文把它们当作安全入口。** 未触发同步、部署、
清理、恢复或合并。后续入口补丁范围见下文；本 PR 不改变 Taskfile、AGENTS、应用或 CI。

## 基线和证据边界

| 证据 | 本次结果 | 可以证明什么 |
| --- | --- | --- |
| `git ls-remote --symref origin HEAD refs/heads/main` | 默认分支 main；`21854fdfe1083da83678ec17b3222ec621d7e061` | 本次远端基线；不是永远有效的交付目标 |
| 用户原副本（只读） | `ee08022c00017fbf2598f08f6af89a2d12ca1cf0`，工作区 clean | 原副本陈旧；不代表线上偏离远端 |
| 本设计工作副本 | 独立 clone，从上述 main 建分支 | 保留原副本；Multica checkout 返回 repo 未配置，遂使用独立 clone |
| 最新集群快照 | 2026-10-29 15:57:17.995671–15:57:18.302909 UTC；context `homelab-talos-lan` | 39 个 Application、42 个 source、57 个直接受管 workload 的观测 |
| Git source | 本仓库均为上述 main SHA；外部 sandbox 为 `63e8d077cba1363e570d9530bcfdead2f255488c` | 两个仓库的 revision 不可互换 |
| HOM-6 历史证据 | 2026-10-29 23:11–23:14 上海时间 | 历史节点、Pod、TLS 探测；本轮未复测这些功能，不冒充最新证据 |
| HOM-2/3/4 交付 | [PR #137](https://github.com/loushomelab/homelab-talos-iac/pull/137)，`4309f53fa8afa1dd70d242b4a55122054eea0e53`，未合并 | 本地校验已另行交付；本设计独立基于 main，不叠加该分支，不重做其功能 |

完整表见 [inventory.md](inventory.md)，字段化观测见 [observed.json](observed.json)。
39 个线上 Application 的 source 模式、有序 source 坐标、声明 targetRevision 与 main
逐一匹配；这是 source 层面的核对，**没有证明所有 Helm values 或应用字段完全一致**。
快照来自两次 GET，非原子快照，也不是带真实性保证的交付凭证。文件只保留 source 坐标、
状态、资源名称、镜像及容量，不保留 valuesObject、环境变量、Secret、配置正文或错误消息。

39/39 Application 当时 Healthy/Synced。但 Alloy desired=0、Mimir 多组件零副本、
Pyroscope 两个 StatefulSet 零副本仍存在。它们可标为“符合维护声明”，不能标为功能验收通过；
HOM-8 另交恢复方案，本文不改变其状态。

## Source → revision 规则

统一坐标为 `(Application namespace/name, source 模式, 1-based position,
repoURL, chart/path/ref, declared targetRevision)`；目标还绑定 destination、完整期望 spec
摘要及其配置提交。repoURL 只按审核过的映射归一化，未知 URL/别名拒绝，不能按仓库短名猜测。

| source 类型与本例 | 精确期望值 | 验证字段 | 必须额外验证 |
| --- | --- | --- | --- |
| 本仓库 Git 单 source：Homepage、tier、配置 app | 审核后的当前 main 完整 SHA | `status.sync.revision` | source/path、comparedTo、具体配置字段、实际 workload |
| 单项 `sources` 中的 Helm：Forgejo | `17.1.6`，不是本仓库 SHA | `status.sync.revisions[0]` | 父 workloads-tier-4 的 Git SHA + Forgejo 完整期望 spec，尤其 inline values |
| Helm+Git：n8n | 按序 `[2.1.1, <本仓库 main SHA>]` | `status.sync.revisions`，长度与坐标同时匹配 | Git path `argocd/configs/workloads/n8n/manifests`，Helm values、两部分生成资源 |
| Helm+Git values：argocd-self-managed | `[10.9.1, <本仓库 main SHA>]` | 同上 | `ref: values` 对应 `$values/argocd/bootstrap/values.yaml`；无 path 的 values source 不生成 workload |
| Helm+Git manifests：Authentik | `[2026.8.5, <本仓库 main SHA>]` | 同上 | chart 与 Git manifests 分开验证后检查合并资源集 |
| 外部 Git 内 Helm chart：n8n-sandbox | tag `service/v1.3.2` 在其自己仓库解析得到完整 SHA `63e8…488c` | 虽仅一个 source，使用 `status.sync.revisions[0]` | repo 为 `n8n-io/n8n-sandbox-service`，path `charts/n8n-sandbox-service`；不能因 path 含 charts 就当 Helm registry source |
| 真正单 source Helm：cert-manager 等 | 声明的精确 Chart 版本，如 `v1.21.2` | `status.sync.revision` | 父 app Git SHA、期望 spec、CRD 或 workload 的修改字段 |

存在 `spec.sources` 时按它处理，包括长度为 1 的情况，不能按数组长度改用单数 revision。
同时出现 source 与 sources 时按 Argo 语义识别，但入口拒绝歧义声明并要求先走 PR 清理。
有 `chart` 是 Helm 仓库 source；Git 内 chart 仍是 Git revision。拒绝版本范围、未解析的
分支/tag、缺失 revision、未知 plugin/source 类型、变更 source 顺序或数量而未重新审核。
Git tag 使用 peeled commit，不能把 annotated tag 对象 SHA 当作 commit。

Helm 的 Chart 版本并不能证明 inline values 已更新：例如 Forgejo 改 resources 仍可能显示
`17.1.6`。必须先确认父 tier 在目标配置提交完成核对、live child spec 对应目标文件，
再确认修改字段确实进入生成资源。多 source 中重复资源默认视为失败，除非审核计划明确
列出覆盖关系和最终期望值；不能因 revision 数组正确而忽略后一个 source 的覆盖效果。

## 拟定入口：只计划、只验证

日常交付保持 `分支 → 本地验证 → PR → 成员决定合并 → Argo 自动 reconcile → 只读验证`。
本任务不批准合并或部署。拟定两个后续入口 `delivery:plan`、`delivery:verify`：前者生成
可审核的计划，后者读取观测并返回明确结果；两者都没有 sync、prune、patch 或 delete 能力。
自动同步超时只报告未交付，不自动切换到手工同步。

计划至少包含：目标集群/context、Application allowlist、配置仓库完整 URL、基线与审批时间、
每个 source 坐标及独立解析的精确 revision、声明文件与父链、期望 spec 摘要、被修改的
资源字段断言、workload 的 kind/namespace/name、预期非零容量、endpoint 断言及时间预算。
摘要按规范化 JSON 计算，不纳入 status、managedFields 等运行态元数据；运行时默认字段
差异须有审查过的规范化规则。Secret 只验证引用和就绪条件，不读取或摘要真实 Secret 数据。

拒绝规则（默认失败关闭）：

1. app/context/destination 不在已审核 allowlist、参数为空或包含额外 shell 内容，立即退出。
   后续实现使用 argv 数组传参，不做字符串拼接、`eval` 或 `awk | bash`。
2. 配置基线必须由远端读取：校验 URL、默认分支 HEAD/main 的关系、完整 commit 对象存在。
   本地副本 dirty、落后、分叉、未知 commit、未合并 PR SHA 一律拒绝日常交付目标。
   计划阶段读取本地 main 副本的 HEAD，不把正在编辑的 feature branch HEAD 当交付目标。
3. `HEAD` 必须在 source 自己的 repo 中先解析默认分支；`main`、tag 和固定 SHA 也分别解析。
   外部 Git 校验当前 ref 的 peeled commit；Helm 校验精确版本和经信任渠道获取的 chart
   内容摘要/OCI digest。网络、认证、ref、artifact 校验失败即拒绝，不能沿用缓存冒充最新结果。
4. 运行前后重读远端 ref 和 Application source/代际，计划创建时间与快照时间均须在预算内
   （建议初值 300 秒），任何 ref/source/destination/spec 变化要求重新计划；不是自动追随
   新版本。后续应保留开始和结束时间及读取 resourceVersion；跨对象 GET 仍非事务快照。
5. 从 root/tier 到叶子逐层核对。parent 到达配置 SHA 不足以证明 child spec 已更新；两者均须
   验证。root 由 Day-0 管理，若改 root 自身则转入 HOM-9 审核流程，不能假定有父 app。
6. 校验 `status.sync.comparedTo` 与期望 source/destination 对应，comparison 时间足够新，
   revisions 数组长度、位置、坐标和精确值全部匹配。Synced/Healthy 是必要条件，不能替代这些检查。
   Error 条件、未批准的重复资源警告、正在运行或目标版本失败的 operation 均阻断。
   `operationState` 可能是历史记录；不得把历史 Succeeded 当本次成功，也不能因旧版本的
   Failed 永久拒绝已成功的新目标。判断要绑定 syncResult 的目标 revision/spec 与时间。
7. 具体资源字段、workload 和 endpoint 全部达标才能退出 0。缺字段、未支持的 kind、
   无法读取、超时、网络不可达或未经说明的跳过均非零，并列出阶段与资源身份。
   维护零容量只可单独返回 maintenance/incomplete，不得计入功能通过。
8. 回退先形成新的 Git PR，重新计算每个 source 的目标和具体字段；旧本地 SHA 不构成回退授权。
   不提供强制参数绕过基线、直接 sync、prune、删除 Pod 或恢复监控。

外部 branch/tag 可被移动，Helm 同版本也可能被重新发布；只比较版本字符串无法证明制品
字节不变。后续实现必须增加可追溯制品摘要，或明确拒绝无法验证的制品。本模拟不实现下载、
签名或真实制品证明，因此不能充当生产安全门禁。

## Workload 定位和只读精确验证

先从 Application 的 `status.resources` 提取 GVK/namespace/name，再用精确 GET 验证资源
存在和 Argo tracking 身份，并与目标渲染资源集比较；不要仅凭 app 标签推测。
由 operator 创建的子对象需沿 ownerReferences 追溯，单列依赖而非误判为 Argo 直接管理。
允许无 workload 的配置/CRD app，但计划须写明原因和具体资源字段断言，不能空跑成功。

| Application | 本次直接 GET 已确认的真实定位 | 验证要点 |
| --- | --- | --- |
| forgejo | Deployment `forgejo/forgejo` | Chart + 父提交 + 修改字段 |
| homepage | Deployment `homepage/homepage` | Git SHA + 渲染 ConfigMap 指定键的内容摘要 + 实际配置生效断言 |
| n8n | Deployment `n8n/n8n` | 两个 source 的数组及所改字段 |
| n8n-sandbox | Deployment `n8n/sandbox-api`；StatefulSet `n8n/sandbox-privileged-runner` | 外部仓库 SHA；两个 workload 均须核对 |
| forgejo-runner | StatefulSet `forgejo/forgejo-runner` | namespace 不等于 Application 名称 |
| grafana | Deployment `monitoring/grafana` | namespace 不等于 Application 名称 |
| traefik | DaemonSet `traefik/traefik` | 不是 Deployment；desired/updated/ready 均须达标 |
| umami | Deployment `monitoring/umami-umami` | workload 名称和 namespace 都不能套用 app |
| alloy / mimir / pyroscope | 见清单，含 DaemonSet、Deployment、StatefulSet | 维护中零容量不证明采集/查询功能可用 |

后续验证器的 workload 规则：

- Deployment：observedGeneration 对应当前 generation；updated/ready/available/总 replicas
  达到预期，无旧副本/不可用副本和 ProgressDeadlineExceeded。还须对所改 Pod template
  字段与运行 Pod 的镜像 imageID 做需要的版本断言；rollout 成功本身不证明改动字段正确。
- StatefulSet：结合 updateStrategy/partition 验证目标 ordinal；普通 RollingUpdate 要求
  currentRevision=updateRevision、updated/ready 达到预期。OnDelete 或 partition 更新不能
  沿用普通规则，需独立审核计划，默认拒绝。不得为验证执行删除或重启。
- DaemonSet：observedGeneration 当前，desiredNumberScheduled>0，updatedNumberScheduled、
  numberReady、numberAvailable 达标，无 unavailable/misscheduled；策略例外需独立计划。
- 非 workload：核对每个修改字段，例如指定 ConfigMap 键摘要、IngressRoute backend、CRD
  schema/版本标志；ConfigMap 存在不能证明应用已读取。Homepage 历史 subPath/浏览器缓存
  问题说明还需只读服务响应/浏览器断言，本轮只引用历史经验，未执行运行中容器命令。
- endpoint：使用 TLS 验证、连接与总时限、经审核的状态码和响应断言；302 登录页只证明
  入口可达。业务功能验证必须有明确无副作用的读接口；不以 `curl -k` 或非空 HTTP_CODE 通过。
  未提供读接口时明确功能证据缺口，不擅自发送可能写入的业务请求。

以下是本次使用过或后续可使用的只读命令形态，不执行 `--refresh`、patch 或 sync：

```sh
git ls-remote --symref origin HEAD refs/heads/main
git ls-remote https://github.com/n8n-io/n8n-sandbox-service.git \
  refs/tags/service/v1.3.2 'refs/tags/service/v1.3.2^{}'
kubectl --request-timeout=15s -n argocd get application n8n \
  -o jsonpath='{.status.sync.revisions}'
kubectl --request-timeout=15s -n n8n get deployment sandbox-api \
  -o custom-columns=NAME:.metadata.name,GEN:.metadata.generation,OBS:.status.observedGeneration,READY:.status.readyReplicas
kubectl --request-timeout=15s -n n8n rollout status statefulset/sandbox-privileged-runner --timeout=90s
```

精确比较应由后续实现读取结构化 JSON，在内存里提取 allowlist 字段并比较；不输出完整
Application spec、ConfigMap、环境变量或 Secret。所有子步骤的失败必须返回顶层，不用
`|| true`、忽略返回值、只打印 ERROR 后继续，或只有管道末端成功便通过。

## 后续补丁的隔离/移除范围（未实施）

| 文件/入口 | 后续补丁的具体内容 | 验收要求 |
| --- | --- | --- |
| `Taskfile.yaml:18–31` `sync` | 移除 patch/revision/prune 与 rollout 猜测；兼容旧名字只输出迁移提示并 exit 2；新增只读 plan/verify | 旧命令明确失败，kubectl 写操作调用为 0；保留失败退出码 |
| `Taskfile.yaml:86–94` `clean:pods` | 删除通用清理能力；旧入口 exit 2，可提供只读列出异常 Pod 的替代项 | 不再含 delete、awk 生成 shell、全命名空间删除或 `|| true`；无环境开关绕过 |
| `Taskfile.yaml:80–81` `inspect:apps` | 同时显示 source 模式、有序 revisions | n8n/Forgejo/sandbox 不再出现误导性的空 revision |
| `Taskfile.yaml:100+` probe | 传播超时/TLS/不合期望状态失败；按 app 定义 endpoint 断言 | 不接受 -k、ERR 文本或任意 2xx/3xx 作为功能证明 |
| `AGENTS.md` 交付段 | 移除直接 patch 示例和强制 task sync；将“精确 SHA”扩展为按 source 的 revision + spec + 字段验证；以零 mutation 为主约束 | 文档与 Taskfile 一致，不再保留可复制的 mutation 指令 |
| 本地校验入口 | 基于 PR #137 已验证版本继续工作，不撤销其离线能力 | HOM-7 后续补丁不能覆盖 HOM-3/4；CI schema 由 HOM-10 处理 |

实施该补丁需新的明确范围，合并/部署仍由成员决定；本设计 PR 的通过不代表这些入口已隔离。
后续补丁须用 PATH spy 和系统网络隔离验证未知 app、陈旧基线、Helm、多 source、外部 repo、
read 超时、同步失败、字段不符、workload 超时与 endpoint 错误均非零；记录真实工具与 stub 的边界。

## 隔离模拟与复现

仅依赖 Python 3 标准库，不需要 Task、kubeconfig、Argo CLI 或网络：

```sh
python3 -m unittest discover -s design/safe-delivery -p 'test_*.py' -v
python3 design/safe-delivery/mock_delivery.py < design/safe-delivery/example-synthetic.json
```

`example-synthetic.json` 的 source 坐标引用本次清单，父 spec 摘要、时间、字段验证、
rollout、endpoint 结果均为**人为合成**。`mock_delivery.py` 只读取 stdin JSON，输出固定
阶段/原因标识，成功退出 0、契约失败退出 1、无效输入退出 2，没有任何真实命令适配器。
它不是已实现的新入口；尤其不实现远端解析、live 读取、spec 摘要计算、artifact 验证、
owner 追溯、完整 workload 策略或功能探测。测试通过不代表真实交付通过。

用子进程调用模拟 CLI 来核对失败是否确实传播到进程退出码，覆盖 7 个正常 source/workload
组合、31 个主要拒绝场景、外部 repo/顺序错误、零容量/StatefulSet revision 及坏输入。
完整执行记录与计数见 [validation.md](validation.md)。静态观察与合成验收输入分开存放；
observed.json 永远不是下一次上线时可以重用的“通过”文件。

## 参考依据

- [Argo 多 source 与 values 引用](https://argo-cd.readthedocs.io/en/stable/user-guide/multiple_sources/)：source 数组语义和 values-only source。
- [Argo Helm](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/)：Helm 渲染及 Chart targetRevision。
- [Argo 自动同步](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)：Git 驱动的 reconcile。
- [Argo 资源健康](https://argo-cd.readthedocs.io/en/stable/operator-manual/health/)：Application 父子健康边界。
- [Kubernetes Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)：generation、replica 和 rollout 失败条件。

这些文档支持机制；300 秒预算、拒绝策略和隔离范围是本设计的工程选择。
