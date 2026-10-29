# HOM-8：NAS/S3 准入与监控链路恢复方案

**结论：继续维护，当前不允许恢复。** 本 PR 完成只读核对和可审查方案；没有恢复采集、
调整副本、改配置、写 S3、合并或部署。恢复需要成员针对实施 PR、准入证据和回退风险确认。
NAS 从执行机不可达不能证明磁盘损坏或维护仍在施工，但足以阻止宣称存储已就绪。

## 当前证据（2026-10-30 上海时间）

集群 GET 的精确 UTC 时间见 [observed.json](observed.json)，网络探测时间为
2026-10-29 16:08:36–16:08:44 UTC（上海 10-30 00:08）。各次 GET 非原子快照。

| 核对项 | 本轮结果 | 边界 |
| --- | --- | --- |
| 远端 main | `21854fdfe1083da83678ec17b3222ec621d7e061` | 独立 worktree 从该提交建分支；用户原副本未切分支、修改或重置 |
| 前置交付 | [HOM-7 PR #138](https://github.com/loushomelab/homelab-talos-iac/pull/138)，`2ee64a9fd209abe490f3157f77183f805c4aa517`，OPEN | 只参考设计；未把其文件或工具当成 main 已有能力 |
| 校验工具 | [PR #137](https://github.com/loushomelab/homelab-talos-iac/pull/137)，`4309f53fa8afa1dd70d242b4a55122054eea0e53`，OPEN | 本 PR 不依赖它已合并 |
| K8s | context `homelab-talos-lan`，6/6 节点 Ready | 不等于 S3 或数据链路正常 |
| Argo | 三个后端/采集 Application Healthy/Synced；live spec 与基线文件完整相等 | 三者均用 `sources`，revision 数组分别为 `1.14.3`、`6.2.0`、`2.3.1` |
| 父链 | `monitoring-tier-3`、`monitoring-configs` 同步上述 main SHA | Helm 版本不能替代父 tier 的配置 SHA |
| Alloy | DS desired/current/ready 全 0；没有节点携带维护 selector 标签 | 维护阻断有效 |
| Mimir | distributor/gateway/querier/frontend/scheduler、compactor、三组 ingester、三组 store-gateway 均 0；operator/exporter 各 1/1 | 对应服务无 ready EndpointSlice 地址 |
| Pyroscope | 后端和内置 alloy 两个 StatefulSet 均 0/0 | 对应服务无 ready 地址 |
| 凭据同步 | `monitoring-secrets` Ready=True/SecretSynced，ClusterSecretStore Valid/ReadOnly | 未读取 Secret 值；这不证明 S3 账号权限或有效性 |
| HTTP | Mimir `/prometheus/api/v1/query?query=up` 和 Pyroscope `/ready` 均 503，正常 TLS 验证 | 从执行机经过现有入口，非 Pod 内连通性证据；curl exit=0 也不算通过 |
| NAS/S3 | 旧 NAS 地址 SSH 最初超时，固化探测为 Host is down；9000 live/ready 均连接超时 | 旧地址来自配置/历史记录，未解密当前 `S3_ENDPOINT`，不能证明它仍是当前真实目标 |
| 采集目标 | 全集群只有 `monitoring/unifi-poller` PodMonitor，无 ServiceMonitor | 恢复不能承诺已有节点、K8s 全套指标覆盖 |

网络退出码和 HTTP 状态见 [probes.json](probes.json)。字段化集群证据只保留状态、名称、
容量/volume 类型及 source 坐标；不含 Secret、配置正文、对象内容或个人资料。

## 准入清单：所有项均须有时间、操作者和证据

状态“缺失”表示本轮没有取得足够证据，不表示相关系统必然故障。全部闭合前保持维护。

| 门禁 | 通过条件/需补证据 | 当前 |
| --- | --- | --- |
| G0 维护窗口 | NAS 负责人明确维护结束、当前地址/版本/服务、允许恢复写入；记录 RTO/RPO 与操作窗口 | 缺失 |
| G1 NAS 健康 | 当前 pool GUID/拓扑正确、ONLINE、错误计数无增长；磁盘 SMART/近期 scrub、容量与 inode/配额、水位和重启后服务恢复证据 | SSH 不可达，缺失；不启动 scrub/自检来补证据 |
| G2 数据保护 | 两个 bucket 及 MinIO 隐藏元数据/IAM 的 NAS 外一致副本、备份时间/位置/校验和与隔离恢复记录；TrueNAS 配置与 secret seed 安全保存 | 缺失；不能只用同池快照或 VM 系统盘备份代替 |
| G3 S3 读路径 | 在私密会话核对 ESO 的 `DB_MINIO_ENDPOINT → S3_ENDPOINT`；从未来实际运行节点/Pod 网络验证 DNS、路由、live/ready；以各自服务账号 HeadBucket、限量 List、Head/Get 已知历史对象并核对摘要 | 未执行认证对象读取；缺失，健康 HTTP200 单独不够 |
| G4 S3 写/权限 | 审查两账号分别对 `s3-mimir`、`s3-pyroscope` 的最小所需 List/Get/Put/Delete 权限、配额/保留策略；经专项确认在批准测试前缀 Put/Get 校验后 Delete，留审计回执 | 本轮禁止 S3 写入，未执行；缺失；不在生产已有 key 上试写 |
| G5 数据连续性 | 保存维护前最后样本/对象时间、已 flush 的可验证记录、历史查询基线；明确维护间隙不能自动补采；无 PVC 状态下接受潜在未落盘数据丢失的 RPO | Git 注释称已 flush，但没有独立当前证据；缺失 |
| G6 K8s 与采集 | 节点容量、RBAC/CRD、Secret 引用、端口及 eligible nodes 清单；确认 metrics 分片和 profiles 目标标签，避免重复采集 | Ready/CRD/ESO 已核对；容量、运行采集和分片未验收 |
| G7 审批 | 逐阶段 PR 的确切 SHA、字段/资源 diff、render、预期 endpoints、监控/回退清单，成员确认允许合并并恢复 | 本 PR 仅方案，未申请或取得恢复确认 |

旧本地审计 `homelab-infra/docs/n100x8-baremetal-truenas-migration-2026-10-10.md`
（另有 10-11 修订）曾记录 MinIO `/data` 落在 `tank/minio-data`、周期快照/复制任务为空、
PBS 备份失败且过期。**这些均为历史背景，本轮没有复核，不能当成当前故障或当前备份证明。**
名为 `tank/s3-mimir` 的 dataset 不代表 bucket 实际物理落点；PBS datastore 若在同一 NAS，
也不算 NAS 外保护。不得为了补证据尝试导入池、改 IAM、导出凭据或创建备份任务。

## 逐组件恢复顺序（待确认的实施设计）

每一行是独立审批和 GitOps 交付屏障；不得把所有改动一次合并后依靠同为 wave 3 自动排序。
所有应用目前自动 sync/selfHeal/prune，合并实施 PR 就可能立即产生副作用。
本 PR 只新增 `design/` 文档，不会改变 Application。

| 阶段 | 文件/建议字段与期望资源 | 放行条件与回退点 |
| --- | --- | --- |
| P0 准备 | 关闭 G0–G7；冻结 chart 版本与 secret 引用；记录历史读取样本/摘要；保留双采集器为 0 | 缺一项即停；不改 NAS、bucket、IAM 或数据 |
| P1 Mimir ingester | `mimir.yaml`：`ingester.replicas: 1`；删除 ingester 的临时 `zoneAwareReplication` 覆盖，恢复 chart 的 prepareDownscale=true 与间隔 12h | render 为 zone-a/b/c 各 1；ring 全部 ACTIVE、/ready 200、S3 无错误；无新采集，失败先调查，不能盲目 downscale |
| P2 Mimir 历史读取 | `store_gateway.replicas: 1`，删除其临时 zoneAwareReplication 覆盖（默认 30m）；再逐批恢复 `query_scheduler.replicas: 2` → `querier.replicas: 1` → `query_frontend.replicas: 1` → `gateway.replicas: 1` | store-gateway 三 zone 各 1；各批 rollout/ready/ring 通过再交付下一批；历史查询与预留基线相符；失败可回退本批无状态 reader 字段 |
| P3 Mimir compactor | `compactor.replicas: 1`，保持现有持久化设置 | 先核对 retention/删除策略、历史读取与备份；无对象存储错误、无异常删除。compactor 启动会改对象，不存在仅靠 revert 撤销对象变化的回退 |
| P4 Pyroscope 后端 | `pyroscope.yaml`：`pyroscope.replicaCount: 1`；顶层 `replicaCount` 同步为 1 避免误导；`alloy.controller.replicas: 0` 保持 | 实际只有后端 STS 变 1，/ready 与历史 profile 查询通过；单体后端启动也可能写入/压缩，必须先完成 G2/G4 |
| P5 单节点 Alloy | `alloy.yaml`：以已有 `kubernetes.io/hostname: worker-01` 替换维护 selector；不改节点标签、权限、hostPID、目标 URL；内置 pyroscope-alloy 仍 0 | 一个 eligible worker 的 DS desired/ready=1；两后端均可用；完成 [新时间戳验收](acceptance.md)，连续观察 15min |
| P6 扩展 Alloy | 先审查并启用 Helm `alloy.clustering.enabled: true`，两个 `prometheus.operator.*monitors` 块各加 `clustering { enabled = true }`；确认 peer Service/发现参数与 target 分配，再移除 canary hostname selector | 本轮 3 个控制平面有 NoSchedule taint、无额外 tolerations，通常只有 3 个 worker eligible，不能要求 DS=6；逐节点核对，重平衡期间允许有界重复但不能持续重复/乱序 |
| P7 稳定 | Grafana 原 datasource URL 保持：Mimir gateway `/prometheus`、Pyroscope `:4040`；观察 24h 并记录维护缺口 | 功能、存储持久性、错误/容量趋势及重平衡通过才可结束维护；此方案不承诺已运行验证 |

建议容量是恢复起点，沿用维护前单副本字段并明确 scheduler=2（chart 默认）。
**Mimir replicas=1 在启用 zone-aware 的固定 chart 中渲染为三个 zone 各 1，不是总共 1。**
当前 `replication_factor: 1`、`persistentVolume.enabled: false` 不变；没有三副本耐久保证。
顶层 `zones: []` 不关闭实际 `zoneAwareReplication.zones`。保留准备/间隔防护，不能复制维护时
`prepareDownscale:false`、`0s` 作为恢复后的常态。

P6 是解决当前全局 monitor 在多个 DS Pod 中重复 scrape 的必要设计步骤：只去掉 selector
会让多个采集器发现同一 PodMonitor。clustering 参数已查固定 chart 及官方组件文档，
但尚未运行验证；实施 PR 必须校验 Alloy 配置、peer 发现、网络和目标唯一归属。
eBPF 本地发现仍按 `HOSTNAME=spec.nodeName`，本轮实测引用正确；现有 service_name 来自
`app` 标签，缺标签的业务必须选带有效标签的基准工作负载，不能把空结果判为成功。
`pyroscope-alloy` 默认保持关闭以避免与独立 DS 重复；若要恢复它，另列目标与去重规则并批准。

## 中止、回退与数据边界

任一阶段出现新存储错误、持续 401/403/5xx、ring 不 ACTIVE、Pod 重启/容量压力、查询回归，
或采集后两次连续检查没有新样本，停止推进并记录时间、版本与受影响范围。
使用批准的补偿 PR 保持 Git 声明一致，不运行 `task sync`、`task clean:pods`、手工 scale/patch。

| 失败位置 | 优先动作（均为未来需授权实施） | 不可越过的边界 |
| --- | --- | --- |
| P0 | 保持当前零副本状态，补准入证据 | 不绕过网络、权限、备份缺口 |
| P1–P4，尚无采集 | 保持 collector 暂停；无状态读组件可通过补偿 PR 回到前一状态；调查后端 WAL/flush 与对象写入 | 后端重启也可能存在 replay/compaction，不把“没恢复采集”当作“零写入” |
| P5/P6 metrics 异常 | 先用 PR 将 Alloy selector 恢复为当前维护阻断，停止新采集；保留 Mimir/Pyroscope 运行以排空和持久化 | Alloy WAL 为临时存储时停止 Pod 会损失队列；接受风险、尽可能先 drain，不能先关后端 |
| 需要后端退回零副本 | 确认 collector 停止、队列已排空、ingester/Pyroscope 落盘并有 S3 读取证明后，再走 graceful shutdown/downscale 设计和补偿 PR | 无 PVC、RF=1；若存储不可用不能安全 flush，保持后端并升级人工决策，不保证无损停机 |
| bucket/数据异常 | 停止推进；保护原对象和证据，拟定独立恢复到新 bucket/隔离环境的方案 | Git revert 不能回滚 S3；禁止覆盖生产 bucket、清 WAL、强制删 Pod/PVC、还原快照或忘记 ring 节点 |

Mimir HTTP 管理接口的 prepare/flush 即使不是 kubectl 也有写副作用。本轮没有调用；将来如需
使用，须在具体实施方案中单独列出并获准，不能用它绕过“零直接集群修改”。

## 验证与复核

本轮仅本地渲染固定 charts（Mimir 6.2.0、Pyroscope 2.3.1、Alloy 1.14.3），
核对当前零副本与建议恢复副本/zone/prepare 注解；没有执行这些建议配置。
具体本地检查、重现命令及功能通过标准见 [acceptance.md](acceptance.md)。
本 PR 完成的是方案验收，运行恢复验收全部留待获准后执行。

可复用约束已在本文沉淀：零副本 Healthy 不代表可用；备份必须覆盖真实对象数据；
zone/嵌套 replica 字段须先 render；恢复后回退必须考虑无 PVC 和外部存储副作用。
没有改写个人 Obsidian vault。
