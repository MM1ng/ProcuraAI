# Batch 3A-1 Evidence Freeze — independent evidence review

审计代码：`5c4c466f813a43500e56f9090ee8b84d847132c2`；原始基线：`c047b9d1ee1b67c1e340e15e5122fb4fb26d1025`。封存日期2026-10-10 Asia/Shanghai。本轮不修代码、不运行测试、不调用模型、不做部署。代码已完成静态审查是用户提供的状态；本封存不伪装成另一轮静态审计或上线放行。

## XML逐case独立复算

不是复制REPORT的总数：用XML解析器统计每个testcase的failure/error/skipped子节点，并与testsuite声明比较。

| 文件 | 实际case | PASS | FAIL | ERROR | SKIP | execution退出码 |
|---|---:|---:|---:|---:|---:|---:|
| red-actual.xml | 26 | 0 | 26 | 0 | 0 | 1 |
| green.xml | 26 | 26 | 0 | 0 | 0 | 0 |
| regression.xml | 77 | 77 | 0 | 0 | 0 | 0 |
| initial-setup.xml（本地原名red.xml） | 26 | 0 | 0 | 26 | 0 | 1 |

四份逐case总数均与suite属性一致。前三份没有SKIP/ERROR，也没有skipped或xfail标志；Red的全部26份failure和初次26份error文本保留。JUnit不能证明不存在未记录的其他运行/选样或非严格XPASS；源码检查新测试没有skip/xfail装饰器。Regression是定向77项，不是全仓库全绿。

从固定提交的AST提取新增测试函数和字面量parametrize，26个完整参数化名字与Red/Green/Regression中新测试完全一致，Red/Green同序同名。Regression的其他51项均存在于提交中的相应原测试模块；核对函数存在性，不声称重现全部动态pytest收集机制。

## 代码版本关联：部分可验证，不能冒充完全闭环

- Git原始blob SHA256：新增测试为`6C5997CF6AC6D7C34D24EC700A0B2B4FA0CB5895CB2703CABEAB492EB1B23C42`，与execution记录及当前本地测试字节完全相符。
- 两个API本地CRLF与Git LF导致原始字节SHA不同；仅换行归一化后相符。helper和新测试原始字节完全相同。各SHA见verification.json，不能把归一化相等说成原始字节相等。
- execution记录的运行HEAD是旧基线。Green在未提交工作区执行，后续才提交为已审计SHA。目录没有每次运行的完整源码/tree哈希或源码快照；因此历史运行产品代码等于固定提交的完整证明为NOT_VERIFIED。
- Red本来就是修复前运行，不能宣称它针对最终修复提交执行。
- Red/Green命令选择同一个测试文件，XML名称及记录共享SHA一致；没有分开、实时封存的每运行测试文件哈希，逐运行字节身份为NOT_VERIFIED。
- 三份命令、cwd和退出码在execution中完整；XML状态支持这些退出码，但XML本身不携带进程exit code。目录没有独立原始进程终端日志，不能提升为独立验证退出码来源。

## 保护文件记录

execution有5文件汇总SHA，本轮当前文件均与之匹配；这些不是文件内容。目录没有独立before/after原始采集记录，仅一个名为protected_sha256_before_and_after的汇总映射。历史前后不变断言为NOT_VERIFIED，不能用当前一致补写历史证据。目录原件共6份均哈希冻结，原件不改；原件未上传。

## 脱敏与保真

- XML和JSON保留所有case名称、参数、状态、统计、时间、失败/错误原因、命令结构、工作目录语义及退出码。
- 私人绝对目录按最长前缀替换为[REPO_ROOT]、[WORKSPACE_ROOT]、[USER_HOME]；机器hostname替换为[HOST_REDACTED]。命令是原记录的路径脱敏表示，不是本轮执行的新命令；重现者需映射占位符到自己的路径。
- [REPO_ROOT]=仓库根，[WORKSPACE_ROOT]=原仓库上两级父目录，[USER_HOME]=个人用户目录；原cwd对应[REPO_ROOT]\\backend。
- 参数里的fixture-observability-admin-only和fixture-llm-debug-only是提交中硬编码的模拟测试字符串，不是真实管理员/调试token；private-a/private-b是新测试源码中合成日志，不是用户聊天或真实traces。保留它们以保证测试名称与失败原因可核验。
- 未读取.env，不上传业务JSON/SQLite、支付数据、原始用户聊天或凭据。REPORT是历史报告脱敏副本，保留原有自述，前置说明限制，不能当独立证据。
- sha256-manifest.json提供原件/公开副本分别的SHA；公开副本SHA因脱敏不同是预期，不能与原件SHA混用。manifest不包含其自身SHA，提交SHA固定整个包。

## 验收结论

GO仅用于把真实现有结果和显式证据缺口交付独立复审。完整历史代码运行关联、保护文件前后原始记录和独立进程退出日志不足，均NOT_VERIFIED；本包不能替代对固定提交的完整复现运行证明。不得补写或重建历史测试数据。

本轮只提交docs/audits/batch-3a1/中的证据文件；四个已审计文件及其他产品源码不变，audit/batch-3a1分支不变，无PR/合并/部署/Jev启用。本轮完成即停止。
