# 彼端桌宠源码开发指南

## 技术栈

- Python 3.12
- Git LFS：保存 GIF 动作资源，避免普通 Git 大包上传超时
- Tkinter：桌宠窗口和“情侣小窝”界面
- Pillow：GIF 解码、透明帧处理和图标加载
- Pystray：Windows 系统托盘
- JSON：本地状态和共享文件夹同步
- PyInstaller：单文件 EXE
- Inno Setup 7：Windows 中文安装程序

## 本地运行

```powershell
git lfs install
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\src\biduan_pet.py
```

`run.bat` 也可以在已创建虚拟环境后启动程序。

## 运行测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s .\tests -v
```

当前测试覆盖：

- 默认状态深拷贝和稳定设备 ID
- 两台设备的状态、留言和互动交换
- 非法同步文件拒绝
- 闰年纪念日计算
- 旧状态、旧形象模式和设置迁移
- “我的状态/TA 的状态”桌面来源选择
- 11 类动作清单、61 个状态 GIF 和拖拽 GIF
- GIF 帧数、持续时间、尺寸和二值透明边缘
- 四档动作轮换间隔

## 构建 EXE

```powershell
.\build_exe.ps1
```

脚本会安装构建依赖、生成图标、运行测试，并输出 `dist\BiDuan.exe`。

## 构建安装程序

安装 Inno Setup 7 后运行：

```powershell
.\build_release.ps1
```

输出位于 `release\BiDuan_Setup_<版本>.exe`。`dist`、`release`、`build`、虚拟环境和本地工具均不提交到源码仓库。

## 动作资源

运行时动作位于 `assets\animations`，`manifest.json` 定义状态和 GIF 的对应关系。

所有 GIF 使用 Git LFS 管理。克隆仓库前应安装 Git LFS；若克隆后只有 LFS 指针文件，可在仓库目录运行 `git lfs pull` 下载完整素材。

从原始素材目录重新导入：

```powershell
.\.venv\Scripts\python.exe .\tools\import_animation_assets.py "C:\path\to\原始动作目录"
```

导入脚本会：

1. 按预设目录名映射 11 类状态。
2. 复制并统一命名 GIF。
3. 读取尺寸、帧数和帧持续时间。
4. 生成新的 `manifest.json`。

原始素材目录不属于运行时依赖，不应写死在主程序中。

## 核心数据流

```text
用户选择我的状态
    -> StateStore 保存本地状态
    -> 写入共享目录中的本设备 JSON
    -> 第三方云盘同步文件
    -> 对方 StateStore 导入为 partner 状态
    -> 对方按本机 status_source 决定是否显示该动画
```

桌宠动画只解码当前 GIF，避免一次性把全部动作加载到内存。状态动画按设置的间隔更换同类变体；拖动期间临时切换到拖拽 GIF，松手恢复选定来源的状态。

## 本地数据结构

主数据文件为 `%APPDATA%\BiDuanPet\state.json`。新增字段时应：

1. 在 `DEFAULT_STATE` 中提供默认值。
2. 在 `StateStore.ensure_runtime_defaults()` 中迁移无效或旧值。
3. 保持旧版本 JSON 可读。
4. 为迁移和核心行为增加测试。

## 版本发布检查

1. 同步更新 `APP_VERSION`、`installer\biduan.iss` 和 `installer\version_info.txt`。
2. 运行全部单元测试。
3. 检查桌宠透明边缘、拖拽动画和状态来源切换。
4. 检查五个主菜单页面在小窗口下可滚动。
5. 构建 EXE 和安装程序。
6. 在隔离目录执行安装、启动、退出和卸载测试。
7. 确认卸载后 `%APPDATA%\BiDuanPet` 数据仍保留。

## 后续重构建议

当前 MVP 主要集中在 `src\biduan_pet.py`。进入云同步阶段前，建议逐步拆分为：

- `state_store.py`：本地数据和迁移
- `animation.py`：GIF 解码、状态映射和轮换
- `sync.py`：共享目录与未来网络同步接口
- `desktop_pet.py`：透明桌宠窗口
- `control_panel.py`：情侣小窝界面
- `windows_integration.py`：托盘、开机启动和单实例

拆分应伴随测试迁移，避免一次性重写造成行为回退。
