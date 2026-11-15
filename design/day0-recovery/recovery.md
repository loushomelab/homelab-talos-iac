# 恢复分流、证据清单与 RPO/RTO

本文件不含执行恢复的授权。所有生成备份、恢复、故障演练及生产测试写入都须专项计划批准；
本轮仅核对现有状态和记录。后续操作者先重新取证，不能把本快照当作实时健康证明。

## 恢复分流与停止点

| 路径 | 判断条件 | 未来实施步骤/验收 | 必须停下的情况 |
| --- | --- | --- | --- |
| R0 单 CP/宿主暂失 | 原盘存在、其余 etcd 多数可达 | 先核查宿主/网络/存储；优先恢复原成员可达性；必要时审查替换成员方案；验证成员一致、API、DNS、卷与业务 | 身份不明、双重 IP、Ceph/NAS 异常或缺容量；不能直接 bootstrap 新集群 |
| R1 全站掉电后上电 | 原数据完整，无证据指向不可恢复多数丢失 | 按 Day-0 D2→D3 检查原节点/仲裁，再恢复依赖；原 etcd 不做重新 bootstrap | 多数无法恢复、磁盘异常；转 R2 审核，不能循环 reset |
| R2 etcd 多数永久丢失 | 已排除恢复仲裁；存在受控 snapshot 与原 secrets/config | 保护原盘；冻结 GitOps；在隔离环境以同一原集群身份/兼容版本重建控制面，从明确 snapshot 恢复一次；验证成员、revision/关键对象、API 和应用数据指向，再单独审批切换 | 缺 snapshot/hash/原 secrets、旧 CP 尚能接入、目标不隔离；不自动跳过 hash 校验 |
| R3 PBS VM/LXC 恢复 | 明确 snapshot、磁盘 manifest、依赖、目标 VMID/IP | 先保证 datastore/chunks 与必要密钥可读；新 VMID/隔离网络恢复；检查磁盘/启动/数据；禁用回连生产的 collector/job；审查切换 | PBS 自身不可启动且只有其 OS 盘备份；无 chunks；禁止覆盖原 VMID/IP 或同时启动重复 etcd 身份 |
| R4 Longhorn 卷 | 确认可用 replica 或有独立 backup；已界定相关 DB 一致点 | 优先保留现有 replica；隔离恢复到新卷/PVC并读取摘要/文件基线；DB 与资产配套验收 | replica 同宿主全部丢失、无已验证备份；不要强行选旧副本/删 PVC；reclaimPolicy=Delete |
| R5 PostgreSQL/Redis | 已知 PGDATA/WAL/tablespace、版本/扩展、backup 类型与目标点 | 隔离新 LXC/实例，恢复批准的 CT/逻辑/base backup 与完整 WAL 链；PG 启动与只读完整性/业务一致性检查；切换另批 | CT rootfs 备份未覆盖外置数据、WAL 链断、版本不兼容、无法匹配 Forgejo 等文件资产 |
| R6 NAS/S3/监控 | 已核对真实 endpoint、pool/磁盘、NAS 外副本、IAM 与恢复点 | 依 HOM-8 G0–G7 的数据/权限/备份门禁重新审查；隔离新 bucket/prefix 恢复并核摘要/历史读；后端就绪后分批 collector | 不把“当前 Pod Ready”视为可覆盖生产对象；缺副本/审批则停止数据恢复，保持现有证据 |

R2 应依据固定版本 [Talos 1.13 灾备文档](https://docs.siderolabs.com/talos/v1.13/build-and-extend-talos/cluster-operations-and-maintenance/disaster-recovery.md)
编写逐节点执行计划：先判断可否恢复仲裁，保留原 secret material，明确目标节点 Preparing
状态与唯一恢复发起点。该官方流程含擦除 EPHEMERAL 等破坏性步骤，本草案故意不提供
可直接执行的 reset/bootstrap 命令；它们须列入具体批准清单。

不能把三个不同时间的 CP VM snapshot 同时还原当成已验证 etcd 灾备；也不能把单台
worker 的 VM snapshot 当作跨 Longhorn/数据库一致备份。恢复控制面里的 Secret 可能过期，
对象可能指回生产 PVC、PG 和 S3，必须在启用 Argo、ESO、collector、CronJob 前完成隔离审查。

## 恢复证据清单

“缺失”表示未取得足够证明，不等于备份必然不存在。每项闭合必须包含操作者、时间、
源/目标身份、工具/版本、日志引用、摘要、结果和可重现的验证方式。

| 保护对象 | 本轮已取得 | 待补齐的具体证据/只读核验方法 | 负责人角色 |
| --- | --- | --- | --- |
| etcd | 三成员正常状态；CP VM PBS snapshot | 备份目录/外部调度记录中的 snapshot 时间、revision、摘要、独立保管位置；原 secrets 与 config 安全引用；隔离恢复结果。不要为补表直接创建 snapshot | Talos 管理者 |
| 六 VM | PVE 磁盘配置、PBS 各 VM 最新 snapshot、PBS backup task OK | 每份 backup manifest/disk 覆盖、版本/boot 依赖、实际 restore 到新 VMID 的启动/数据验证；任务 OK 不等于 restore OK | PVE/PBS 管理者 |
| PBS 服务及 chunks | CT154/NFS/raw 路径、datastore list、最新 job/snapshot | PBS config/ACL/加密与密钥保管引用、chunk/index verification 成功报告、NAS 外副本、从另一宿主恢复服务与可读 datastore 的证据 | PBS/NAS 管理者 |
| PG 151/152 | 3960x 上运行，rootfs Ceph；CT snapshot 和 PBS task OK | 私密核对配置中实际 PGDATA、WAL、tablespace 与 CT mount 的覆盖；PG 版本/扩展；dump/base backup、WAL 归档成功时间/连续性、隔离恢复与只读业务基线 | 数据库管理者 |
| Redis 153 | 同宿主，CT snapshot 和 PBS task OK | RDB/AOF 模式、持久化路径与 snapshot 关系、会话/队列丢失的允许范围；隔离实例恢复验证 | 身份/数据库管理者 |
| Longhorn 七卷 | 卷状态、每 replica nodeID，Backup/RecurringJob 为空 | 真实数据目录与 VM 磁盘覆盖；备份位置/时间/摘要、恢复到新卷后的文件验证；pulse/dind 副本共宿主风险修复方案 | 存储/应用管理者 |
| S3/监控 | 当前后端和 collector ready；main 声明 RF=1、无 PVC；未取对象 | 私密核对 ESO endpoint 映射、当前 NAS pool/磁盘；bucket/隐藏元数据/IAM 的 NAS 外一致副本；按 HOM-8 校验历史对象与查询；写权限测试与恢复另批 | NAS/监控管理者 |
| Git/IaC/凭据 | 固定 main SHA；引导 Secret 名称、store 状态 | 集群外 Git/制品访问、HCP state/执行路径、原 Talos secrets/CA、Doppler/仓库/PBS key 安全引用的灾难可取回性 | 平台/安全负责人 |

本轮 PBS latest snapshot（UTC；详见 `pbs_latest_snapshots`）：

| 对象 | 最新时间 | PBS 最近 backup 状态 |
| --- | --- | --- |
| VM110 / 111 | 2026-11-04 18:00:10 / 18:00:38 | OK / OK |
| VM112 / 113 | 2026-11-04 18:00:01 / 18:00:10 | OK / OK |
| VM114 / 115 | 2026-11-04 18:00:00 / 18:00:08 | OK / OK |
| CT151 / 152 | 2026-11-04 18:01:18 / 18:01:38 | OK / OK |
| CT153 | 2026-11-04 18:01:56 | OK |
| CT154 PBS 自身 | 2026-08-25 18:01:57 | 本轮近期任务无；当前 job 排除自身 |

这些时间是备份标识时间，不是业务事务一致点或实测 RPO。当前观察距最新一批约 22 小时，
下一次调度尚未到；不把其判作过期失败，也不承诺未来每天必然成功。

按 [PVE 容器挂载说明](https://github.com/proxmox/pve-docs/blob/master/pct.adoc)，
mount point 是否备份必须核对类型和 backup 配置；PBS 数据盘现场是 backup=0。
按 [PostgreSQL 物理备份/PITR 要求](https://www.postgresql.org/docs/17/continuous-archiving.html)，
在线恢复点需要相应 base backup 与连续 WAL；CT snapshot 的存在不能代替该证据。
PG 当前大版本未核验，17 文档仅用于机制参考，实际恢复必须匹配现场版本。
PBS 的 [恢复说明](https://pbs.proxmox.com/docs/backup-client.html#restoring-data)
也不能替代本环境的密钥、chunks 与恢复记录。

## RPO / RTO 待确认

RPO 是可接受的数据损失窗口，RTO 从事件开始至目标业务验收。下表均未获数值承诺，
不能将备份周期当成已实现 RPO，或把镜像下载/数据库回放排除在 RTO 之外。

| 服务层 | 现有线索 | 必须由成员/负责人确认 |
| --- | --- | --- |
| API/etcd | 三成员；每日 VM snapshot；独立 etcd snapshot 未证实 | 最大可丢对象变更时间、目标 API 恢复时间、etcd snapshot 周期/保留/集群外保管 |
| 身份/核心 PG 与 Redis | 151/153 共宿主；近期 CT 备份 | 登录/权限/队列可接受损失、是否需要 PITR、最大停机、身份恢复的业务优先级 |
| Forgejo/n8n 等 DB+卷 | DB 与文件/插件分别保存 | 跨两类数据的一致恢复点；仓库/附件/工作流基线、允许的重放/人工补偿 |
| 观测 PG | 152 和身份库同宿主 | 仪表板/配置与遥测各自 RPO、恢复优先级和历史丢失范围 |
| Longhorn 资产 | 每日 VM snapshot；pulse 三副本同宿主 | 每卷 RPO/RTO、独立 backup 目标/保留、三物理域保障与修复窗口 |
| Mimir/Pyroscope | 当前正常副本；RF=1/无 PVC、外部对象存储 | 接受未落对象的内存/WAL 损失范围；历史数据可丢弃条款适用范围；NAS 外副本目标与停机预算 |
| PBS/NAS/全站 | PBS 控制面共宿主；数据盘依赖单 NAS | NAS/宿主全损后的独立恢复点、备份密钥负责人、恢复制品和备用容量、完整 RTO |

日备份可作为“计划周期约 24h”的声明；只有持续成功、覆盖完整、校验与恢复通过才可
评估是否满足业务 RPO。RTO 应在获准隔离演练中分别测量：基础设施→API/DNS→
Secret/存储→身份/DB→业务→监控，并把人工作业/审批/外部依赖等待计入。

## 下一次演练的可审查方案模板

1. 选择单个保护对象和已有备份，列 snapshot ID、校验摘要、密钥安全引用、版本；
   没有候选备份时另提备份创建方案，不在演练中临时覆盖生产。
2. 列出隔离宿主/网络、新 VMID/IP/PVC/bucket、容量及禁止回连的生产目标；
   原数据保留，只读证据先行；etcd 恢复环境不能与原成员互通。
3. 固定实施 PR/脚本 SHA、操作者和批准清单。每步列写影响、超时、停止点、
   是否可通过 Git 回退；明确对象存储/数据库写入无法靠 revert 撤销。
4. 验收预先确定：API/etcd 身份与对象基线、PG 数据库/角色与业务读取、卷文件摘要、
   S3 历史对象/查询、登录与端点；本轮不创建用户数据或执行 SQL 来生成基线。
5. 记录开始、各屏障完成、恢复点时间、实测损失与耗时；保留日志和摘要，
   通过后另批生产切换。失败时保留证据，清理隔离资源也按批准清单执行。

后续审批应针对具体对象/窗口/影响，不能将本文件或历史手工笔记视为通用恢复许可。
本 issue 可按文档及取证范围验收；上述未执行项是运行恢复的门禁和后续工作。
