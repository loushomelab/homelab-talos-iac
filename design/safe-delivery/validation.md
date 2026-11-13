# HOM-7 验证记录

执行时间：2026-10-29 UTC（上海时间跨入 2026-10-30）。范围仅本设计及合成模型，
不表示已完成生产入口实施、部署验证或监控恢复。

## 只读取证

- main 与默认 HEAD：`21854fdfe1083da83678ec17b3222ec621d7e061`。
- 外部 tag：`git ls-remote` 核实 `service/v1.3.2` 为
  `63e8d077cba1363e570d9530bcfdead2f255488c`，与 sandbox 观测相符。
- 两个 GET：`kubectl --request-timeout=15s -n argocd get applications -o json`、
  `kubectl --request-timeout=15s get deployments,statefulsets,daemonsets -A -o json`。
  原始结果只在内存中处理，写入文件前移除 values、配置、环境变量和消息。
- 39/39 Application 声明文件可定位；source 模式、source 顺序与坐标/targetRevision
  与 main 相同；42 个 source 的 revision 及 57 个 workload 已记录。
  详情和准确时间窗在 `observed.json`；不含 endpoint 和运行 Pod imageID 核验。
- 原工作副本 HEAD 保持 `ee08022c00017fbf2598f08f6af89a2d12ca1cf0`，工作区无变更。

## 合成进程测试

```sh
python3 -m unittest discover -s design/safe-delivery -p 'test_*.py' -v
python3 design/safe-delivery/mock_delivery.py < design/safe-delivery/example-synthetic.json
```

5 个 unittest 方法执行 **43 个模拟 CLI 子进程**：

| 输入 | 数量 | 实际进程退出码 |
| --- | --- | --- |
| 正常 Git、Helm、Helm+Git、外部 Git chart、values-only Git、DaemonSet、无 workload 配置 app | 7 | 0 |
| 拒绝场景：31 个主要故障 + 外部 repo/顺序错误 2 个 + 零容量/StatefulSet revision 2 个 | 35 | 1 |
| 无效输入 | 1 | 2 |

主要故障覆盖：未知/带 shell 内容的 app、sync 请求、陈旧或 dirty 本地副本、远端移动、
过期/未来证据、旧父提交、相同 Chart 版本但 spec 错误、source 模式/repo/path 改变、
缺 revision、统一 SHA、错误 Git SHA、旧 comparedTo、失败或运行中的 operation、
ComparisonError、OutOfSync/Degraded、字段错误、workload 缺失/未就绪/旧 generation/
额外旧副本、TLS 失败、登录重定向、错误响应断言。

观测中的 ready 状态未用于这些通过判定。测试构造的 spec 摘要、时间、字段和 endpoint
是合成值；每种 source 仅复用静态坐标与 revision 来说明映射差异。

## macOS 隔离复核

另用随 HOM-7 评论附上的 `hom-7-verify.py` 执行上述测试：

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' \
  /opt/homebrew/bin/python3 hom-7-verify.py
```

该运行器位于项目工作目录的 `.multica/`，相邻目录 `hom-7-safe-delivery/` 是独立 clone。
在其他位置使用时调整运行器的 `repo` 路径。它先用 TCP connect 探针确认网络限制实际生效，
然后在工作目录内创建临时 PATH spy，覆盖 kubectl、argocd、git、curl、task、helm，设置
无效 kubeconfig。子进程监视器只允许调用当前 Python 和模拟模型，不允许其他 argv。
运行结束自动删除临时 spy 目录。

实际输出：

```text
NETWORK_GUARD: outbound TCP denied with PermissionError
Ran 5 tests
OK
PROCESS_VERDICTS: {"0": 7, "1": 35, "2": 1}
FORBIDDEN_TOOL_CALLS: 0
```

这是模型的隔离与失败传播证据，不是旧 Taskfile 的隔离证明。
本机未安装 Go Task；没有声称执行 `task val:all`。设计不改应用，未运行 main 中旧的
client dry-run 入口；其离线替代已由 PR #137 交付并由 HOM-4 验证。

## 静态交付检查

- `git diff --check`：通过。
- 对新增交付文件运行 pre-commit：适用 hooks 均通过；YAML 与 Renovate hooks 因无对应
  改动跳过。另运行 `pre-commit run --all-files`，仓库已有文件的全部 8 项 hooks 通过，
  包括 YAML 和 Renovate 校验；这些检查不等同于完整 Kubernetes/CRD schema 校验。
- 本 PR 不改变 `Taskfile.yaml`、`AGENTS.md`、`argocd/`、`.github/`；不存在清单或同步配置变更。
- 原始集群 GET 输出不纳入 PR；发布的 evidence 仅含上述 allowlist 字段。
- 外部 CI 由 PR 触发后独立运行，不作为本次前台任务等待条件；不合并、不部署。

后续入口真实实现须另验远端解析/认证失败、超时、制品摘要、spec 规范化、追踪身份与完整
rollout 策略。模型中布尔断言代表这些步骤的输入结果，不是它们已被实现的证据。
