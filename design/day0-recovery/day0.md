# Day-0 / 整站冷启动 runbook 草案

本文件是供审批的步骤与放行标准，**本轮没有执行任何写步骤**。
执行者不能照此文档直接在生产开始 bootstrap。先完成下列预检，再审批具体实施 PR、
对象清单、制品摘要和窗口；既有集群恢复与全新建群必须分流。

## D0：确定恢复类型与授权

1. 建立事件记录：开始时间、影响范围、值守人、目标 RPO/RTO、上次良好版本；保留原 VM/磁盘。
2. 选择 [恢复分流](recovery.md)：有原 etcd 数据的整站重新上电，不运行新 bootstrap；
   仲裁可恢复时先恢复仲裁；多数数据永久丢失才评估 snapshot 恢复；真正空环境才建新集群。
3. 确认目标是隔离网络/新 VMID/新数据路径，或由成员批准对现有对象的具体影响。
   每一写步骤写明操作者、目标、预期结果、超时、中止方式和可回退范围。
4. 明确 bootstrap 例外：仓库禁止直接 Kubernetes mutation；历史笔记里的 Helm install、
   创建 namespace/token、apply root 并不构成本次授权。具体 Day-0 例外必须单列批准，
   限于初装 Argo、引导 Secret/namespace、root。接管后回到 GitOps，不允许扩大为手工修资源。

未获具体执行批准时，继续交付和审查本方案；停在写步骤前，不阻止文档验收。

## D1：集群外恢复包与安全保管（当前有缺口）

在私密保管系统核对可访问性，记录条目引用/版本/负责人，不复制值到 Git 或 issue：

| 必需项 | 核对方式/放行条件 |
| --- | --- |
| PVE 本地应急管理、SSH/证书信任、NAS/PBS 本地管理 | 不经待恢复的 Authentik，预先核准账号和宿主指纹；不关闭 host key 校验 |
| 原 Talos secrets、每节点 machineconfig、talosconfig/kubeconfig、有效 CA/期限 | 私密保管引用、版本与失效处理；机器全损后仍可取回；不现场重新生成原集群 secrets |
| etcd snapshot 与恢复元数据 | 受控位置、时间/revision、摘要、版本兼容性、密钥与隔离恢复记录；本轮未取得 |
| Git 与 OCI/Helm/镜像制品 | pin Git SHA、chart/image/installer 版本与 digest，具备 GitHub/OCI 访问；不能依赖待恢复 Forgejo |
| Terraform/HCP/Doppler | 各 workspace state 可恢复、锁/执行路径及凭据；不要导出 state 或在日志打印敏感 output |
| 引导 Secret | Doppler service token 的安全来源、最小权限、有效期、注入者和轮换方式；不是从 ESO 自举获取 |
| PBS/NAS | datastore 内容/配置、PVE storage 定义、加密密钥（若启用）和 NAS 配置/secret seed；OS 盘与 chunks 分开 |
| PG/Redis/卷/对象数据 | 一致恢复点、真实落点、manifest/摘要与验证记录；应用配置和二进制资产需一起配对 |

本轮确认已有引导 token Secret 的名称及 store Valid，不能证明 D1 在灾难时成立。
HCP agent 在 3960x；若其不可用，必须先有获准的集群外 runner/agent 恢复方案，
不能临时在管理机直接运行 Terraform apply 绕过交付边界。

## D2：基础设施先行

由 PVE/NAS 负责人核对电源、交换/路由、外部 DNS/NTP、宿主 quorum、SSD/Ceph/NAS 容量与健康。
先核对存储可用再让 guest 使用数据盘；禁止盲目重新初始化池、格式化、创建同名空 datastore。
实际 node/VMID/网桥/MAC/IP/磁盘及 NAS server 要与现场 inventory 对齐。

当前声明入口为 PVE `vms/` 和 `talos/`，不是 Talos IaC GitOps 仓库；
数据库 LXC 本体也不是 `databases/main.tf` 自动创建的资源。
新建/重建 guest、修改 Talos machineconfig 都是未来需批准的写操作。
放行证据为宿主/存储状态、隔离/容量和原盘保护记录，不只看 Terraform plan 能执行。

镜像路径先验证：Zot 125、上游 registries、Talos installer/ISO 的版本摘要、出口与证书。
旧笔记中的 image/chart 版本不能替代本次固定版本；本轮版本是 Talos 1.13.8，
Argo chart 当前声明 10.9.1。实施时重新审核兼容性并冻结，不能在灾难恢复时顺便升级。

## D3：Talos / etcd / API 屏障

既有数据重新上电：保留原身份，检查 time sync、节点服务与 etcd members/status，
先确保多数恢复，再确认 API。新建集群：审核 HCP 的 machine secret 创建、配置应用、
仅一次 bootstrap 的计划；现有 HCL bootstrap 目标为 cp-03，不能与历史手工命令并行执行。
快照灾备：走 [R2](recovery.md)，不要用全新空 etcd 代替业务恢复。

在获得凭据的管理机只读验证（不改变 kubeconfig）：

```sh
talosctl -n 192.168.50.110,192.168.50.112,192.168.50.114 etcd members
talosctl -n 192.168.50.110,192.168.50.112,192.168.50.114 etcd status
kubectl --server=https://192.168.50.110:6443 get --raw=/readyz --request-timeout=10s
kubectl --server=https://192.168.50.112:6443 get --raw=/readyz --request-timeout=10s
kubectl --server=https://192.168.50.114:6443 get --raw=/readyz --request-timeout=10s
kubectl get nodes -o wide --request-timeout=10s
kubectl get endpointslices -n kube-system -l kubernetes.io/service-name=kube-dns --request-timeout=10s
```

放行：身份/成员一致、无双集群、etcd 仲裁、API 就绪、所需节点/CNI/CoreDNS 可用；
DNS 功能需在批准的验证环境从工作负载网络测试，本轮未创建测试 Pod。
失去 API 但已有业务连接存在不构成放行；禁止通过跳过 TLS 验证掩盖入口问题。

## D4：最小 Argo 和引导 Secret（待批准例外）

批准方案应固定 `argocd/bootstrap/values.yaml`、初装 chart 及 root 的 SHA，
提前渲染检查 OIDC/域名/TLS 对尚未启动的 Authentik/Traefik 的依赖，
预设仅管理面可用的初装访问方式，不临时开放公网或放宽 RBAC。

引导契约是 `external-secrets` namespace 的 `doppler-token-global`，键 `dopplerToken`，
由 `doppler-cluster-store` 引用。注入工具从批准的 secret manager 读入，
关闭 shell tracing，不在命令参数、终端回显、临时文件、PR/附件中暴露值；
具体工具、最小权限、审计及轮换回收由安全负责人在实施方案中填实。
此 token 是集群外信任根，不能要求未启动的 ESO 生成自身访问 token。

root 的 source 当前是 `HEAD`。在任何 root 注册或恢复 Argo 自动同步前，
必须冻结所需 revision 并审查全部将被 reconcile 的子 Application。
现有 root/tier/child 多处 automated selfHeal/prune：创建 root 后可能立即改变整个集群。
实施 PR 必须具体定义在何处控制同步/恢复顺序及恢复最终声明的办法，不能假设人工
“逐个点击”能压过已经启用的自动同步，也不能把 HOM-7 未合并设计当作已有安全入口。

## D5：分层放行，不能只等 wave

| 层 | 当前 root 声明 | 必须逐项留证的放行条件 |
| --- | --- | --- |
| operators | wave 0 | 所需 CRD Established、controller Ready、webhook 可访问；避免先发 CR |
| core/secrets | wave 10 | Longhorn 节点/副本/CSI、所需 PVC；MetalLB 地址；namespace 存在；store Valid、ExternalSecret Ready |
| routing/TLS | wave 20 | Traefik 有 ready endpoints、VIP 路径、证书和路由验证；API 不经业务 VIP 冒充 HA |
| identity | wave 25 | PG/Redis 已按同一恢复计划就绪，Authentik 可登录，OIDC/forward auth 符合预期 |
| monitoring | wave 30 | 核对本轮运行基线；灾备后恢复仍须 NAS/S3/权限/数据门禁，先后端与历史读，后 collector |
| workloads | wave 40 | DB 与卷一致点、Secret 引用、rollout、真实端点及登录/读取路径；批准前不执行业务测试写入 |

本轮 `argocd-cm` 只有 Application ignoreDifferences/ignoreResourceUpdates 相关键，
没有 Application health override。wave 不是子应用运行就绪屏障，必须逐项验收。
每层应核对 Git source 的精确 SHA、Helm source/chart revision 数组、具体字段与运行资源；
只看 Healthy/Synced 不够。冻结期间如何阻止下层提前自启必须在 D4 实施方案完成。

## D6：交接与中止

每个屏障失败即停止后续步骤，保留原盘、错误时间和日志摘要；不在现场清 PVC、WAL、
bucket、etcd 数据目录来试错。不通过反复 bootstrap、force sync 或强删 Pod 解除阻塞。
在外部数据库/存储发生写入后，Git revert 不能回滚数据；回退需独立数据补偿方案。

最终交接记录：批准编号、执行 SHA/制品摘要、每层实际/目标状态、备份恢复点与数据损失、
从开始到 API/身份/业务可用的分段耗时、残余风险及负责人。达到业务验收再结束恢复窗口；
“节点 Ready”只完成其中一个屏障。
