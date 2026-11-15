# 验收与证据采集

## 本方案交付的本地验证

基线：main `21854fdfe1083da83678ec17b3222ec621d7e061`。只更改本目录。
拉取固定版本 chart 后从 Application `spec.sources[0].helm.valuesObject` 提取 values，
用 `helm template <release> <chart.tgz> -n monitoring -f <values.yaml>` 离线渲染，未向集群提交。
当前 Mimir 渲染出 12 个零副本业务 workload、两个 1 副本辅助 Deployment；
Pyroscope 两个零副本 STS；Alloy DS 携带维护 nodeSelector。
将 README P1–P4 的建议值仅在本地副本试算：Mimir 三个 ingester 和三个 store-gateway
均各 1，prepare-downscale 注解恢复，scheduler=2；Pyroscope 后端=1、内置 alloy=0。
这些检查验证字段作用，不证明运行时 storage、Alloy clustering 或新样本功能。

P6 的本地试算也通过：渲染包含 `--cluster.enabled`、`--cluster.join-addresses`、
peer Service，维护 selector 已移除。尚未用 Alloy 二进制做配置校验或运行时分片验收。

本轮校验结果：

| 检查 | 结果 |
| --- | --- |
| `pre-commit run --all-files` | 全部通过，含 YAML、私钥、冲突、体积和 Renovate 校验 |
| `kubectl apply --dry-run=client --request-timeout=5s -R -f argocd/apps/` | 通过；仅 client dry-run，无资源写入 |
| 同命令作用于 `argocd/configs/` | 失败：既有 Homepage config 被当作 K8s manifest、未替换模板以及 Kustomization 缺对应 CRD；本 PR 未修改这些文件 |
| Renovate JSON 解析、两份证据 JSON 解析、Markdown 代码围栏与 `git diff --check` | 通过 |
| 固定三 chart 的当前/建议字段渲染 | 通过上述检查；仅本地临时 values，未提交实施 manifest |

本机没有 `task`，因此直接运行 Taskfile 对应检查。configs 的全量递归检查是基线的
文件分类问题，已由独立 [PR #137](https://github.com/loushomelab/homelab-talos-iac/pull/137)
处理该类离线校验范围；本 PR 不修改/合并它，也不声称全量 dry-run 通过。

只读复核命令（在正确 context 下执行，输出先脱敏再分享）：

```bash
git ls-remote origin refs/heads/main
kubectl config current-context
kubectl --request-timeout=12s get nodes
kubectl --request-timeout=12s -n argocd get applications
kubectl --request-timeout=12s -n monitoring get deployments,statefulsets,daemonsets,pvc
kubectl --request-timeout=12s -n monitoring get endpointslices
kubectl --request-timeout=12s -n monitoring get externalsecrets
kubectl --request-timeout=12s get servicemonitors,podmonitors -A
```

证据中的 Application spec 相等结果来自本地解析基线 YAML、live GET 后在内存比较；
不保存完整 live Application、Secret 或包含运行环境的日志。snapshot 不是持续监控。

## 获准恢复后的功能验收（本轮未执行）

每阶段记录目标配置完整 SHA、chart 版本、观测 UTC、采集视角、通过/失败、脱敏响应摘要。
缺失值、空数组、超时或无可测基准均标为失败/未验收，不能因 HTTP200 或图表有历史曲线放行。
保存实施前的历史时间段、labels、对象摘要；开始 P5 时记录 `T0`。

| 层 | 通过标准 | 失败处理 |
| --- | --- | --- |
| 声明交付 | 父 monitoring-tier-3 的 `status.sync.revision` 等于批准的配置 SHA；子应用的有序 `status.sync.revisions` 等于 chart 版本；live values 与实施文件相等 | Helm 版本未变不代表 values 已更新；任何字段不符即停止 |
| 工作负载 | 每个修改字段在生成 workload 出现，generation 已观察；rollout 完成、ready=desired 且 desired>0；Service 有 ready EndpointSlice，Mimir rings 正常 | 不把 0/0、只看总绿色或 rollout 超时当成功 |
| NAS/S3 | G1–G4 全通过；Pod 网络可达、无 S3 auth/timeout；原有历史对象摘要相符 | 机外 live/ready 仅辅助；缺凭据/备份不放行 |
| Mimir 新数据 | 下列查询均成功、有非空结果；基准 target `up=1`，真实样本 timestamp>T0 且距当前不超过 `max(120s, 2×实际 scrape interval)`；两次间隔至少两个 scrape interval 的读取时间戳严格递增 | 不使用 Prometheus 响应外层 evaluation time 冒充样本时间；失败则保持单节点或暂停采集 |
| Alloy 发送 | 直接读取 Alloy `/metrics`：highest-sent timestamp 随时间增长；15min 内 pending 无持续增长，failed/dropped 无增量；profile sent 有增量、dropped 无增量 | 自监控未被 scrape 时直接 GET，指标缺失要查当前版本而不是按零处理 |
| Pyroscope 新数据 | 实际 profile type/目标标签非空；只查询 T0 之后区间，至少两个不同时间桶有正样本；同时间窗返回非空 flamegraph 且总样本>0 | 有标签但 profile 为空、只有旧时间段数据或 200 空体均失败 |
| S3 持久性 | 等待实际配置的 block cut/upload 周期与 bucket sync 后，读取新 block 的元数据/时间边界；查询已落块的新数据及维护前历史基线成功 | 只从 ingester 内存读到数据不算持久性通过；不以强制重启/清缓存证明 |
| Grafana | 两 datasource 健康；Explore 对上述新时间窗返回相同 target/时间与 profile flamegraph | 登录页/主页正常不等于数据正常 |
| 扩展后 | 每个 eligible worker 有本地 profile 样本；monitor targets 只有一个活跃分配，重平衡后无持续重复/乱序；24h 无新增存储错误/容量告警 | 当前无 control-plane tolerations，不要求控制平面覆盖；扩大范围需另审 |

## Mimir 查询

沿用仓库 datasource 路径：从现有批准网络入口 GET
`https://mimir.646499453.xyz:8443/prometheus/api/v1/query`；Pod 网络使用
`http://mimir-gateway.monitoring.svc.cluster.local/prometheus/api/v1/query`。
当前 multitenancy=false，不添加租户头。鉴权入口若变更，先更新方案；不绕过 TLS/访问控制。

首先查询 `up`，从结果确定对应 `monitoring/unifi-poller` 的真实 job/instance labels。
以下 `<job>`、`<instance>` 必须替换为该 target 的真实值，不预设 job 名等于资源名。

```promql
up{job="<job>",instance="<instance>"}
timestamp(up{job="<job>",instance="<instance>"})
time() - timestamp(up{job="<job>",instance="<instance>"})
```

另选该 target 的一个真实业务计数器，检查它在 T0 后有样本，避免只通过 scrape 产生的 up。
GET `/prometheus/api/v1/query_range`，传 `query`、T0 后的 `start`/`end` 和实际 scrape interval
相称的 `step`，核对序列包含新数据、没有意外断档。HTTP200 且 `status=success` 仍须检查
`data.result` 非空。维护前后不是连续采集，间隙必须标注；不回填伪造时间戳。

直接读取 Alloy metrics 时重点观察实际暴露的：

```text
prometheus_remote_storage_queue_highest_sent_timestamp_seconds
prometheus_remote_storage_samples_pending
prometheus_remote_storage_samples_failed_total
prometheus_remote_storage_samples_dropped_total
pyroscope_write_sent_profiles_total
pyroscope_write_dropped_profiles_total
```

## Pyroscope 查询

在获准恢复后，通过现有 Pyroscope 入口或 Pod 网络的 `http://pyroscope.monitoring.svc:4040`
使用以下查询 RPC。它们用 HTTP POST 但语义只读，不调用 `/ingest`、push 或管理接口。

1. 对 `/querier.v1.QuerierService/ProfileTypes` 提交 `start`/`end`（epoch 毫秒），
   取实际 `profileTypes[].ID`（按当前返回结构核对字段），不硬编码 profile type。
2. 通过同前缀 `LabelValues` 查询 `service_name`，只选 canary 节点上有工作量且带有效标签的应用；
   必要时带上 namespace/pod 约束，记录其 Pod/node 对应关系。
3. `SelectSeries` 提交如下查询体（占位符替换成实际数字/类型/标签，Content-Type=application/json）：

```json
{
  "start": "<T0之后的epoch毫秒，实际请求用整数>",
  "end": "<当前epoch毫秒，实际请求用整数>",
  "profileTypeID": "<ProfileTypes返回值>",
  "labelSelector": "{service_name=\"<实际应用>\",namespace=\"<实际namespace>\"}",
  "groupBy": ["pod"],
  "step": 15
}
```

4. 对 `SelectMergeStacktraces` 使用同一 start/end/profileTypeID/labelSelector（去除 groupBy/step），
   检查 flamegraph 非空且有正样本。若实际 profile 类型不匹配或标签缺失，修正证据，不能改查询
   为整段历史来掩盖无新数据。API 与响应结构以已部署 Pyroscope 2.3.1 核对，latest 文档不构成
   版本兼容保证。

## 参考依据

- [固定 Mimir chart 6.2.0](https://github.com/grafana/helm-charts/tree/mimir-distributed-6.2.0/charts/mimir-distributed)：本地 pull/template 已核对实际 zone、replica 和 prepare 行为。
- [Mimir HTTP API](https://grafana.com/docs/mimir/latest/references/http-api/)：查询使用 Prometheus HTTP prefix。
- [Pyroscope HTTP API](https://grafana.com/docs/pyroscope/latest/reference-server-api/)：类型发现、时间序列和 flamegraph 查询。
- [Alloy remote_write](https://grafana.com/docs/alloy/latest/reference/components/prometheus/prometheus.remote_write/) 与 [pyroscope.write](https://grafana.com/docs/grafana-cloud/send-data/alloy/reference/components/pyroscope/pyroscope.write/)：发送/丢弃/队列观测。
- [Alloy PodMonitor](https://grafana.com/docs/alloy/latest/reference/components/prometheus/prometheus.operator.podmonitors/) 与 [ServiceMonitor](https://grafana.com/docs/alloy/latest/reference/components/prometheus/prometheus.operator.servicemonitors/)：多实例须配置 clustering 才能分担目标。
