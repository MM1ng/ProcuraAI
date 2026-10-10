# 脱敏历史报告说明

以下为原始 REPORT.md 的脱敏副本，不是本轮新测试或新静态审计。原报告中的历史自述不替代 FREEZE_REVIEW.md 和 verification.json 的独立核验，尤其完整运行版本与保护文件前后原始记录尚未闭环。原始SHA指向本地原件，不是此脱敏副本。

---

# Batch 3A-1 修复证据

基线及完成时HEAD：c047b9d1ee1b67c1e340e15e5122fb4fb26d1025。仅本批代码级验收通过；独立只读复审PENDING，运行服务未重启/未部署；不得自动进入Batch 3A-2或Jev灰度。

## 修改前根因（产品修改前已在聊天提交）

main.py:43 caller_boundary保护名单不包含两个接口。observability.py原17直接调用dashboard_service.py:11，再调用local_tracer.py:86读取共享TRACE_FILE，未做管理员授权。llm.py原30直接safe_llm_invoke，llm_service.py:144 get_llm_model后在167执行_call_dashscope；USE_MOCK_LLM仅是回退条件，不是禁止外部调用。

## 修改后

observability.py:18-26：独立X-Observability-Token -> debug_access.require_traces_admin -> 非空OBSERVABILITY_ADMIN_TOKEN与hmac.compare_digest字节比较 -> no-store -> observability_traces。缺失/错误/未配置/空白token直接403且不读日志；普通caller凭据没有管理员权限。

llm.py:31-48：APP_ENV仅development/test + LLM_TEST_ENABLED严格true + 独立LLM_TEST_TOKEN/X-LLM-Test-Token -> no-store -> mock_llm_response。本入口不再导入或调用safe_llm_invoke，不进入get_llm_model/_call_dashscope；未启用或非法环境404，授权失败403。管理员token、Jev控制token、caller cookie/CSRF均不作为调试权限。正常聊天模型服务不变。

没有写.env或新运行配置；新增授权变量读取放在专用helper，不改变共享Settings或配置缓存。

## 精确文件清单与stat

- backend/app/api/llm.py：21插入，4删除。
- backend/app/api/observability.py：9插入，2删除。
- 新backend/app/services/debug_access.py：31行。
- 新backend/tests/test_debug_access_batch3a1.py：161行。

本批4文件222插入6删除。git diff --stat仅显示两份tracked API修改（30插入6删除），新文件用git diff --no-index --stat /dev/null <path>核对，未暂存。全工作区git diff --stat仍含用户原有data/observability_logs.json、data/orders.json、frontend/next-env.d.ts差异，不能把它们归为本批改动。

## Red -> Green -> Regression

| 运行 | PASS | FAIL | ERROR | SKIP | exit |
|---|---:|---:|---:|---:|---:|
| 初次临时目录未创建（red.xml） | 0 | 0 | 26 | 0 | 1 |
| 实际Red（red-actual.xml） | 0 | 26 | 0 | 0 | 1 |
| 同源Green（green.xml） | 26 | 0 | 0 | 0 | 0 |
| Regression（regression.xml） | 77 | 0 | 0 | 0 | 0 |

初次运行未到应用测试，不作为漏洞证据；原XML保留。随后实际Red显示未授权日志读取次数1、模型调用禁执行Mock次数1。合法管理员读隔离真实日志及no-store、constant-time检查也在同一26项测试中。

Red/Green测试源码SHA：6C5997CF6AC6D7C34D24EC700A0B2B4FA0CB5895CB2703CABEAB492EB1B23C42，修改产品后未改该测试。原有测试和conftest均未修改，未删除/skip/xfail/弱化断言。

Regression=26新测试+43原transaction_snapshot_batch1+8原caller身份/会话/订单边界。模型调用链禁止断言覆盖新接口全部拒绝和授权Mock路径；原交易测试只用隔离JSON/SQLite及SDK Mock，无真实下单/支付。既有conftest重定向orders、traces、runtime和identity SQLite；临时Jev开关仅存在测试子进程，权威false/traffic0。既有Python -B，不安装依赖。

完整实际执行命令、cwd、每次exit及保护SHA见execution.json。JUnit保留逐case结果与Red失败栈，不以报告自述代替执行证据。

JUnit SHA：
- red.xml E9DF63E1EBF5CF6CA25299CFC69DC3C9E8AC7731BD0EFC5892D290F17A60701B
- red-actual.xml E1D8E84D8B0A761C590E628DC877FFC505AFBEAEDF5A7E459474D90E452EBD02
- green.xml A0D075C5535AD6B57696509991FAF8996FA5E939C69DF309C90A2D3369046085
- regression.xml 85366C45D7BE50A136A8FF06706CF0425D91AC88FF849321D67033C60A93EC50

## 保护及残余风险

测试前后真实orders/logs及procurement.db、decision_runtime.sqlite3、transaction_identity/registry.sqlite3共5文件SHA相同。订单/日志原有Git差异保留。未重启服务、未读输出API密钥、未创建commit/PR、未push；Agent/Jev/支付/LLM服务/配置/前端未改。

未执行完整suite、浏览器、真实provider、线上访问、独立代码复审。此前失败未重跑或删除，不能声称全仓库测试通过。

Bearer token需运营方安全生成/保管/轮换，禁止放浏览器前端或URL；本批不配置真实token。两个端点的schema校验失败可先返回框架422（无读取/模型调用），其默认错误缓存头未作额外middleware改造；授权成功和权限拒绝路径no-store已验证。授权管理员仍能读取原始共享日志（设计目标）；日志脱敏、其他接口/summary/status安全边界不在本批。普通业务回归仅上述51项。尚未部署，当前服务的安全状态不能由磁盘修复推定。

Superpowers短设计经用户批准后实施，先同源Red再最小Green；本轮完成停止等待独立只读复审。
