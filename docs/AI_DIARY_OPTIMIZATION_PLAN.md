# AI Diary Optimization Plan

## Long-Term Goal

让 AI 日记逐步具备：

- 本地活动感知：从电脑使用记录里识别今天做了什么。
- 今日时间线整理：把零散窗口记录合并成更像人的事件段落。
- 隐私可控的 AI 日记生成：用户能控制采集、保留、清理和是否发送到云端模型。
- 本地/云端模型切换：DeepSeek 用于文字生成，MiniCPM 用于本地照片理解，模型配置可保存和检测。
- 长期个人记忆：先生成候选，用户确认后才写入长期记忆。
- 粉色少女心 UI：每个页面持续按 `docs/ui-reference/pink-diary/` 的参考图校准。

## Current Progress

- UI 已完成一轮按参考图重做：看板、我写日记、她写日记、回顾、活动、记忆、设置。
- 活动页已能展示今日总时长、活跃状态、分类占比、应用排行、原始时间线和隐私控制。
- 今日总结已从原始 JSON 展示改为“她整理好的今日线索”，并持久化到 `daily_summaries`。
- 活动摘要已能把连续相同/相近的窗口记录合并成事件段，并在活动页展示“事件段 / 原始记录”。
- 每日总结已增加“上午 / 下午 / 晚上 / 凌晨”的时段化整理，并持久化到 `daily_summaries.dayparts`。
- 草稿生成和她写日记会优先读取已整理的 `daily_summaries.events`，再结合长期记忆和手动补充。
- “她写日记”页面已展示证据链：活动事件段、应用事项、照片线索、隐私边界。
- “她写日记”页面活动线索证据卡已追加近 30 天长期趋势，生成前就能看到她会参考的长期节奏依据。
- 活动页和证据链已展示标题脱敏状态：今日命中脱敏规则的数量、时长和隐私说明。
- 活动事件已增加生活化描述，草稿和她写日记提示词会减少应用名、窗口标题、进程名直出。
- 她写日记证据链里的主要应用已增加 `display_name`，页面优先显示“AI 编程助手 / 浏览器 / 远程连接工具”等生活化名称；原始 `app_name` 仍保留在 evidence 中用于追溯。
- 今日活动接口和活动页/看板应用排行也已增加并优先展示 `display_name`，减少 `Codex.exe`、`msedge.exe` 等机器名直出。
- 活动页合并事件段和原始时间线也已增加并优先展示 `display_name`，事件句子里保留原始 `app_name` 字段用于追溯，但界面更接近日常语言。
- 今日活动的常见窗口主题已增加 `display_title`，摘要高亮会优先显示“AI 日记页面 / 浏览器 / 远程连接窗口”等生活化标题，减少 `Codex`、`Microsoft Edge`、数字远程窗口等原始标题直出。
- 她写日记会把本次生成采用的证据快照保存到日记条目，回顾页可查看当时参考依据。
- MiniCPM 视觉模型已桥接到本地 `http://127.0.0.1:8001`，设置页显示模型名、服务地址和“启用照片理解”开关；旧的视觉状态/设备/测试照片块已按用户要求从页面移除。
- “照片理解”已有隐私开关：关闭后图片仍可上传/保存，但不会发送给视觉模型，草稿证据会标记为 `skipped`。
- “我写日记”上传图片后，生成草稿会调用 MiniCPM 提取照片线索，并在页面显示“她看到的照片线索”。
- 用户日记保存时会把照片识别证据写入 `entries.evidence.photos`，回顾页可追溯当时照片线索。
- “她写日记”的证据包 `/api/diary/evidence` 已纳入当天用户日记中保存的照片线索，她生成日记时会自然参考这些线索。
- 设置页已按用户要求移除可见 Ollama 卡片，右上模型卡改为 MiniCPM；Ollama 字段暂保留为隐藏兼容配置。
- `/api/vision/test` 保留为健康检查和开发验证入口；设置页不再暴露手动测试照片卡片，避免打乱参考图布局。
- 活动页隐私控制已增加 `/api/privacy/audit` 审计摘要，集中展示活动记录、窗口标题、脱敏关键词、排除应用、保留策略、最近生效时间、照片理解开关和当天照片理解调用统计；清理活动后会显示最近一次清理结果。
- 活动页已继续按参考图 04 收敛：顶部“她看见了今天的你”去掉硬边框内盒并加入轻花朵背景，右侧隐私控制卡加入本地保存提示，隐私审计列表收成可滚动轻列表，避免首屏变成冗长表单，同时保留记录活动、窗口标题、保留天数、保存、清理等真实操作。
- 看板页顶部四张统计卡已按参考图 07 重排为“连续写作天数 / 总日记数 / 我的日记 / 她的日记”，并接入 `/api/stats/streak`、用户日记数和她的日记数。
- 看板页顶部卡片字体、间距和高度已按参考图继续收敛，统计卡改为更接近参考图的大卡片比例，数字字号和插画比例更突出，同时避免大字断行和信息层级混乱。
- 前端已建立统一字体变量，并隔离导航图标字体；看板标题、统计数字、单位、说明文字的字号层级已重新校准，避免页面字体显得杂乱。
- 看板页“日记统计”区已按参考图 07 收敛为横向统计板：左右作者统计、中间爱心插画感区域，左右统计字段统一为总字数、平均字数、记录天数、情绪平均值。
- 看板页“日记统计”区已继续压缩高度，让首屏节奏更接近参考图 07：顶部统计卡更高，下方统计板更轻，不再抢占首页主视觉。
- 看板页中部图表区已继续按参考图 07 校准：生活节奏趋势图增加纵轴刻度、底部日期和多条趋势线；日记热力图的格子、月份/星期标签和图例间距更接近参考图。
- 看板页底部“今天她观察到”已改成轻量便签式观察条，保留活动感知摘要但不再抢占参考图 07 的主视觉节奏。
- 看板页已继续按参考图 07 收敛首屏高度：底部“今天她轻轻记到”观察条改为贴在日记统计区下沿的轻浮条，保留 `/api/activity/trends` 和跨日对比摘要，但不再把看板撑出 1680x945 首屏滚动。
- “我写日记”页已继续按参考图 01 校准：主卡整体下移、正文纸张行距收紧到更接近横线纸张、右侧 AI 分析卡高度与左主卡更一致。
- “我写日记”页已移除左主卡底部常驻重复状态条，改为有真实操作消息时才显示；桌面上传区保持 1 个上传格 + 5 张缩略图一排且不出现内部滚动条。
- “我写日记”页窄屏布局已修复：主卡和 AI 分析卡改为单列堆叠，上传缩略图区域可横向滚动，步骤条改为两列小胶囊，避免横向溢出和文字挤压。
- “她写日记”页已按参考图 02 从单一大卡片重构为“今日观察”和“她的视角”两张独立卡片；保留全部生成/证据/保存相关 id，并补充桌面信纸顶部粉色信封边、右下折角感和移动端状态条流式布局。
- “她写日记”页桌面观察卡已移除右上角重复副标题，页面标题下保留说明文字，观察卡本身只保留“今日观察”主标题，更接近参考图 02 的清爽首屏。
- “她写日记”页桌面信纸已继续按参考图 02 校准：正文从中间偏右移回左侧信纸书写区，保留右侧邮戳和花束装饰空间，折纸粉色背景减淡；移动端信纸布局保持独立规则，不受桌面调整影响。
- “记忆”页已继续按参考图 05 收敛：长期记忆/候选预览列表保持紧凑滚动高度，候选记忆表格边框和滚动条弱化，右侧“关于记忆”说明卡保留花朵点缀，主列表保持干净纸卡感；确认记住、忽略、编辑、置顶、忘掉等真实操作仍全部保留。
- “设置”页已按参考图 06 继续校准模型设置区：DeepSeek / MiniCPM 分段控件、模型输入卡、右侧模型说明卡、测试结果卡的字体和间距更接近参考图；修复全局 input 样式误伤 checkbox，MiniCPM“启用照片理解”恢复为正常粉色复选框，不再撑坏视觉模型卡。
- 已新增 `tools/check_ai_diary_health.py` 本地健康检查脚本，默认只读验证 AI 配置、活动配置、隐私审计、今日活动、每日总结、日记证据链、日记列表、连续写作、热力图和 MiniCPM 视觉状态结构；视觉服务离线会作为 warning，不阻断其他核心能力检查。
- MiniCPM 视觉服务已增加显式启动能力：后端新增 `POST /api/vision/start`，健康检查脚本新增 `--vision-start` 参数；实测可拉起 `E:\Claude\workshop\models\minicpm-v-4.6-ms`，当前设备为 NVIDIA GeForce RTX 4060 Laptop GPU。设置页不显示启动按钮，避免恢复旧视觉状态面板。
- 健康检查脚本已新增 `--vision-image <path>` 参数，可把本地图片上传到 `/api/vision/test` 进行真实照片理解验证；实测 `write-upload-coffee-ref.png` 能被 MiniCPM 描述为咖啡、窗边桌面和日常放松氛围。
- 日记生成上下文已继续生活化：`context_preview` 和草稿/她写日记使用的活动上下文会把 `Codex.exe`、`msedge.exe`、`SunloginClient` 等机器名转成“AI 编程助手 / 浏览器 / 远程连接工具”等表达；完整证据对象仍保留原始 app 名和事件字段，方便回顾页追溯。
- 生成上下文已增加二次文本清洗：即使旧的每日总结中已保存 `Codex`、`Microsoft Edge` 等产品/窗口名，输出给草稿和她写日记前也会转为“AI 编程助手 / 浏览器”等生活化表达；健康检查会把 `Codex`、`Microsoft Edge`、`SunloginClient`、`ShellHost` 等列为 `context_preview` 泄漏 token。
- 活动页已新增跨日节奏对比：后端提供 `GET /api/activity/compare?days=7`，用今天和近 7 天有记录的日子比较总时长和活动分类差异；活动页“她看见了今天的你”会显示生活化观察，历史不足时会提示今天先作为新的生活基准。
- 跨日节奏对比已扩展作息/专注信号：`/api/activity/compare` 返回 `rhythm`，包含首次活动时间、最后结束时间、事件段数量、平均事件段时长和最长专注段；历史足够时会生成“更早/更晚进入状态”“更集中/更碎”“最长连续做事时间变化”等观察。
- 活动趋势摘要接口已新增：`GET /api/activity/trends?days=30` 返回近 7-90 天逐日活动、作息/专注 rhythm、活跃天数、平均活动时长、平均开始时间、最近最长专注段和趋势观察，为后续看板趋势图提供稳定数据源。
- 跨日节奏对比和长期趋势已接入日记生成证据链：`/api/diary/evidence` 返回 `comparison` 和轻量 `trends`，`context_preview` 会包含“和平时相比”和“近30天趋势”段落；草稿和她写日记会自然参考今天与近 7 天节奏差异，以及近 30 天作息/专注变化。
- 回顾页证据快照已展示当次保存的 `evidence.comparison.insights`、`comparison.rhythm.today` 和轻量 `trends`，用户查看她写过的日记时能看到“和平时相比”的生成依据、当时的开始时间/活动段数/最长专注段，以及近 30 天长期趋势；旧日记没有证据快照时会显示轻提示，说明这是旧版保存记录，不伪造证据。
- 回顾页已为泛标题条目增加显示标题推导：当数据库标题只是“她的日记 / 我的日记 / 无题”时，列表和详情会从正文第一句提炼可读标题，不改动原始数据，但避免回顾列表一排重复标题。
- 回顾页已继续按参考图 03 收敛：列表纸张卡片颜色减淡、滚动条弱化，右侧日记详情卡上移到接近页面标题位置，正文信纸行距压紧，证据快照限制为轻提示高度，导出按钮保持首屏可见。
- 健康检查脚本已加入回顾页前端契约断言：默认检查 `renderReviewEvidence(entry)` 是否仍读取并展示 `evidence.comparison.insights`，防止后续 UI 重构把证据闭环改丢。
- 跨日节奏对比和长期趋势已接入看板观察条：看板“今天她轻轻记到”会在今日活动摘要后追加“和平时相比”和“近 30 天”观察，并优先展示作息/专注类 `rhythm.insights`；活动页会合并展示整体对比和作息/专注观察，健康检查已加入 `Dashboard activity comparison` 前端契约断言。
- 看板“生活节奏趋势”图已接入 `/api/activity/trends`：以最近活跃天展示活动时长、最长专注和进入状态三条折线，沿用参考图式粉/蓝/紫多线视觉；数据不足时仍保持轻量占位。

## Next Iteration

1. 补充更多端到端测试，覆盖活动事件合并、总结生成、照片理解开关、草稿生成和她写日记。
2. 继续细化看板趋势图视觉，让活动时长、最长专注和进入状态的刻度/图例更贴近参考图 07。
3. 继续扩展隐私审计视图：已增加最近一次生效时间、清理按钮结果和照片理解调用次数，下一步可补充按天查看历史审计。
4. 继续校准粉色参考图细节，优先逐页做桌面首屏截图对照：看板图表/统计区、左侧陪伴卡片、设置页模型卡、移动端“她写日记”证据卡。
5. 让每篇她写的日记支持重新生成/对比上一版。
6. 为视觉测试结果增加“保存为照片线索”选项，由用户确认后才写入某篇日记证据。

## Verification Checklist

- `python tools\check_ai_diary_health.py` 应通过核心只读健康检查；MiniCPM 未启动时允许出现 `Vision status` warning，但不应出现 failed。需要主动拉起视觉服务时运行 `python tools\check_ai_diary_health.py --vision-start`。
- 需要确认照片理解真实可用时运行 `python tools\check_ai_diary_health.py --vision-image static\assets\reference\write-upload-coffee-ref.png`；应返回 `Vision image test` pass，并包含非空中文描述。
- `node` 脚本解析 `static/index.html` 内联脚本通过。
- `python -m py_compile database.py main.py activity_tracker.py` 通过。
- `/api/activity/today`、`/api/daily-summary`、`/api/ai/config` 返回 200。
- `/api/activity/compare?days=7` 返回 `today`、`baseline`、`baseline_active_days` 和 `insights`，健康检查中的 `Activity comparison` 应通过。
- `/api/activity/compare?days=7` 返回 `rhythm.today` 和 `rhythm.baseline`，包含 `first_start_time`、`last_end_time`、`event_count`、`avg_event_text` 和 `longest_focus_text`；健康检查中的 `Activity rhythm comparison` 应通过。
- `/api/activity/trends?days=30` 返回 `days`、`summary`、`insights`、`active_days` 和 `window_days`，且 `summary` 包含平均/最近活动时长、开始时间和最长专注段；健康检查中的 `Activity trends` 应通过。
- `/api/diary/evidence` 应返回 `comparison.insights`，且 `context_preview` 应包含“和平时相比”；健康检查中的 `Diary evidence comparison` 和 `Diary context comparison` 应通过。
- `/api/diary/evidence` 应返回轻量 `trends.summary`、`trends.insights`、`active_days` 和 `window_days`，且 `context_preview` 应包含“近30天趋势”；健康检查中的 `Diary evidence trends` 和 `Diary context trends` 应通过。
- “她写日记”页证据卡应展示近 30 天趋势，健康检查中的 `Her evidence trends` 应通过。
- “她写日记”页桌面观察卡不应重复显示页面副标题；布局检查会确认观察卡右上说明被隐藏，避免首屏信息重复。
- “她写日记”页桌面信纸正文应从左侧书写区开始，不能重新偏移到中间；正文宽度应给右侧邮戳和花束留出空间，移动端信纸不应横向溢出。
- 含 `evidence.comparison.insights`、`comparison.rhythm.today` 和 `trends` 的她写日记条目在回顾页应显示“和平时相比”“节奏”和“近30天”证据行；历史旧条目没有 evidence 时回顾页应显示旧版证据快照说明，不应空白或报错。
- 回顾页列表和详情标题不应直接显示泛标题“她的日记”或“她今天的日记”；泛标题条目应从正文推导可读显示标题，并纳入搜索匹配。
- 回顾页桌面详情卡应像参考图 03 一样靠近页面标题，而不是被左侧筛选区整体压低；证据快照盒高度应保持轻量，不应重新撑成大块开发信息面板。
- 健康检查中的 `Review evidence comparison` 应通过，证明回顾页渲染函数仍保留 comparison 与 rhythm 展示逻辑。
- 健康检查中的 `Dashboard activity comparison` 应通过，证明看板观察条仍会优先展示跨日作息/专注对比，并追加 `/api/activity/trends` 的“近 30 天”趋势摘要。
- 浏览器验证桌面和手机无横向溢出。
- 生成今日总结后，活动页显示可读内容，而不是 JSON。
- 活动页时间线优先显示合并事件段，并标出“合并 N 段”。
- 活动页右侧隐私控制应保持参考图 04 式紧凑卡片：审计项可滚动但不撑高首屏，本地保存提示可见；顶部观察卡的跨日对比文本不应重新出现硬边框内盒。
- 记忆页长期记忆列表和候选记忆表格应保持参考图 05 的紧凑“记忆盒”比例，不得重新撑成后台表格；右侧“关于记忆”说明卡应保留花朵点缀，并且所有候选确认/忽略与长期记忆管理按钮保持真实可用。
- `/api/diary/draft` 返回 `context_source=daily_summary`，证明草稿优先使用已整理总结。
- `/api/diary/evidence` 返回 daily summary 证据，且她写日记页桌面/手机均可见证据卡。
- `/api/diary/evidence.activity.top_apps` 有数据时应包含 `display_name`，健康检查中的 `Diary evidence app names` 应通过；她写日记页“应用 / 事项”应优先展示 `display_name`。
- `/api/activity/today.top_apps` 有数据时应包含 `display_name`，健康检查中的 `Today activity app names` 应通过；活动页应用排行和主要应用应优先展示 `display_name`。
- `/api/activity/today.summary.events` 和 `summary.timeline` 有数据时应包含 `display_name`，健康检查中的 `Activity event app names` 应通过；活动页时间线应优先展示 `display_name`。
- `/api/activity/today.summary.top_topics` 有数据时应包含 `display_title`，健康检查中的 `Activity topic titles` 应通过；今日活动 highlights 不应直接暴露 `Codex`、`Microsoft Edge`、`.exe` 等机器化标题 token。
- `/api/daily-summary` 返回 `dayparts`，活动页和她写日记证据卡能显示上午/下午/晚上等时段摘要。
- `/api/activity/today` 和 `/api/diary/evidence` 返回脱敏统计，页面显示今日脱敏状态。
- `python tools\check_ai_diary_health.py` 中的 `Diary context humanized` 应通过：`/api/diary/evidence.context_preview` 不应直接暴露 `.exe`、`msedge`、`SunloginClient`、`ShellHost` 等机器名；完整 evidence 允许保留原始字段供追溯。
- 她写日记返回的 entry 包含 `evidence`，回顾页可显示证据快照；测试写入会被清理。
- `/api/vision/status` 返回 MiniCPM 在线状态；关闭照片理解时返回 `status=disabled`，且不启动/调用视觉服务。
- `/api/diary/draft` 在上传图片且照片理解开启时返回 `image_evidence`；关闭时返回 `skipped=true` 而不是普通识别失败。
- 用户日记保存照片证据后，`/api/diary/evidence` 返回 `photos.items`，她写日记页展示“照片线索”证据卡。
- 设置页桌面布局中 DeepSeek 与 MiniCPM 并列显示，不再出现可见 Ollama 卡片；侧边说明也不再写 Ollama。
- 设置页 MiniCPM 启用照片理解复选框应保持正常 18px 控件尺寸，不得被全局 input 宽高样式撑开；桌面下模型卡和右侧说明卡不应横向溢出。
- `/api/vision/test` 可用现有静态图片返回描述，并且测试前后 `static/uploads` 文件数量不增加。
- `/api/privacy/audit` 返回隐私规则列表、最近生效时间、最近清理结果、今日脱敏统计、保留期内/过期活动数量、照片理解开关状态和当天照片理解调用统计。
- 看板页首屏四张统计卡的文案顺序、数据来源和视觉层级与 `pink-diary-reference-07.png` 对齐，且长数字/单位不换行。
- 看板页首屏四张统计卡应保持同一行，卡片高度接近参考图的大卡片比例，统计数字字号不低于 42px，长数字/单位不换行。
- 看板页“日记统计”横向统计板左右字段完整、情绪平均值统一显示 `/100`，中间爱心区域不挤压左右统计卡。
- 看板页生活节奏趋势图应显示参考图式纵轴刻度和日期标签，并用 `/api/activity/trends` 渲染活动时长、最长专注和进入状态三条趋势线；热力图卡应保持 6 行月份、7 列星期标签、21 列记录格和完整图例，不出现文字重叠。
- 看板页底部观察条应保持轻量高度，活动摘要最多显示两行，不影响上方统计与图表区域。
- 看板页在 1680x945 桌面视口下不应被底部观察条撑出首屏滚动；观察条应保持窄浮条形态，标题隐藏，正文最多两行，同时健康检查中的 `Dashboard activity comparison` 应继续通过。
- “我写日记”页正文纸张横线应与文字行距对齐，桌面布局下左主卡和右侧 AI 分析卡高度接近，上传区 1 个上传格 + 5 张缩略图应整齐一排。
- “我写日记”页初始状态不应在左主卡底部重复显示“分析基于...”状态条；该区域仅在生成、保存、上传等操作后作为反馈显示。
- “我写日记”页窄屏下 `documentElement.scrollWidth` 不应大于视口宽度；上传缩略图可横向滚动，步骤条不应挤压换乱。
