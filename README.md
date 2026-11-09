# 诗音桌面伙伴

一个以《eden*》诗音为灵感的非官方 Windows Live2D 桌宠。此仓库是 **0.9.13 的源码版**。

- **桌面交互**　Live2D 待机、触摸反馈、情绪表情和动作。
- **聊天与陪伴**　独立模型配置、中日双语回复、语音交谈、屏幕共享和实时陪伴。
- **记忆与人格**　跨对话记忆、知识图谱、阅读笔记、角色卡与现实认知。
- **电脑助手**　通过独立权限设置调用本机工具，可按配置确认操作。

## 从源码启动

在 Windows 上安装 Node.js 24 和 Python 3.12 或 3.13，在仓库根目录执行：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci
npm test
```

从 [v0.9.13 发布页](https://github.com/Lunona/eden-sion-desktop/releases/tag/v0.9.13) 下载 `Sion-Live2D-v105-v0.9.13.zip`，把其中的 `assets` 文件夹解压到仓库根目录。准备下表中的 Cubism Core，再执行 `npm start`：

| 本地路径 | 用途 |
| --- | --- |
| `assets/live2d/sion/Sion_H20R12.model3.json` | 与现有参数及动作目录匹配的 Live2D 模型入口，以及它引用的贴图、动作和物理资源 |
| `src/vendor/live2dcubismcore.min.js` | 从 Live2D 官方 SDK 获取的 Cubism Core for Web |

源码启动时默认在仓库的 `data/` 新建本地资料。可在界面添加自己的模型连接，或在启动前用 `SION_PYTHON` 指向其他 Python 环境。电脑操作及本地语音识别需要另行配置。若使用 Whisper，本地环境需安装 `faster-whisper`，可在界面设置 Python 和模型路径。

### 本地语音

在「模型与语音」配置自己的 GPT-SoVITS 服务和参考音频，也可使用 `tools/Start-Voice.ps1` 启动已有的 GPT-SoVITS 安装。脚本从本机环境变量读取 `SION_GPT_SOVITS_DIR`、`SION_VOICE_PYTHON`、`SION_VOICE_GPT_WEIGHTS` 与 `SION_VOICE_SOVITS_WEIGHTS`。多情绪参考支持 `SION_VOICE_REFERENCE_MANIFEST` 和以分号分隔的 `SION_VOICE_REFERENCE_ROOTS`。诗音的语音项目单独维护。 [eden-sion-gpt-sovits](https://github.com/Lunona/eden-sion-gpt-sovits)

## 公开范围与致谢

仓库包含应用和记忆功能的源代码，v105 运行时模型在发布页单独下载。API 密钥、聊天和记忆数据、个人配置、Live2D SDK 及语音资产请保存在本地。模型包附有独立的同人资产声明。

源码按 [GNU AGPL-3.0](LICENSE) 发布。感谢 **lxfight** 和 LivingMemory 的贡献者提供知识图谱实现，也感谢 **menglimi** 的《我会永远陪着你》为陪伴机制提供设计参考。改编范围、上游链接和权利说明见 [第三方声明](THIRD_PARTY_NOTICES.md)。
