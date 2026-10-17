# 运行时强制交付入口

Skill文字不能控制所有聊天产品的展示过程。因此提供一个真正“先检查、后展示”的本机入口，不假装普通聊天已经接入。

## 直接使用本机Codex

已安装Python 3.9+、Codex CLI且已完成本机登录时，把问题通过stdin交给：

```bash
python scripts/run_decision.py
```

可在终端键入问题后结束输入，或让调用程序写入stdin。Windows结束键入可按Ctrl+Z再回车；PowerShell也可把问题字符串通过UTF-8管道传入。使用ASCII以外字符时建议`python -X utf8`。

脚本继承本机Codex的模型与推理配置，不指定替代模型，不读取/复制登录凭据，不安装软件，不索取API Key。Windows优先查找`codex.exe`；只有npm包装器时请用`--codex <原生codex.exe路径>`，不使用`shell:true`。默认最长等待600秒，可用`--timeout`在1—3600秒内设置；失败不自动重试、不降级为未检查答案。

执行路径：本机Codex `exec --sandbox read-only --ask-for-approval never --ephemeral --json --output-schema` → 截留全部模型事件 → 要求成功回合与JSON草稿 → 来源/字段检查 → 确定性渲染 → 输出正文。运行失败、解析失败、来源错误或行动字段缺失，均不输出草稿正文；运行日志不转发给终端，防止把未检查内容或隐私当作答案。

这是本脚本的展示门，不是语义正确性证明、通用OS隔离或对所有Codex配置/工具的安全认证。执行仍依宿主的规则、登录、网络和工具权限；不要把只读沙箱解释成对网络工具的权限承诺。

## 接入你自己的Agent/UI

已有模型的宿主不必再启动Codex。将最终草稿传给`decision_gateway.deliver(record, root=skill_root)`或CLI `decision_gateway.py`，只展示其成功返回值；异常或非零退出时展示“待补充/交付被拦截”，不得显示原始流、旧缓存或自行重写后的答案。不允许通过直接调用`check_decision`后继续展示另一个未经核对的答案绕过本约定。

可以自动强制的是字段完整、来源ID/路径/行号有效、目录卡不可作论据、最终来源与行动不丢失。不能自动证明的是原文是否真的支持结论、反方是否足够强、作者本人会否同意、用户事实是否真实、实际执行结果是否更好。这些仍需正文审阅、留出评测与用户反馈。

普通GPT上传文件但不能执行脚本时，只能手工核对；应标记未经过强制网关，不能承诺同等拦截能力。

实现依据：[官方非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)、[官方CLI参数](https://learn.chatgpt.com/docs/developer-commands?surface=cli)。以本机实际`--help`与验收结果核对兼容性，不绕过版本错误。
