# 更新记录 / Changelog

## 2.3.4 — 2026-10-16

修复安全弹出异常、暂停状态覆盖和主题串色；优化紧凑状态保存、缓存进度汇总及常驻只读哈希进程；为目标写入、刷盘和提交增加取消检查，保留原有校验强度。88 项测试通过，覆盖 Windows 阻塞读写取消与暂停恢复；发行版窗口启动、2.3.3 增量升级及失败回滚验证通过。

Fixed safe-eject errors, overwritten pause state and cascading theme colors. Added compact checkpoints, cached progress totals, persistent read-only hash workers and cancellation checks for target writes, flushes and publication, preserving verification strength. All 88 tests passed, including Windows blocked I/O cancellation and pause/resume recovery. Packaged window startup, delta upgrade from 2.3.3 and failure rollback were also verified.


## 2.3.3 — 2026-10-11

精简未使用的 Qt 组件，提高发行包压缩等级；构建输出移出 push，Setup 升级清理对应旧组件。保留完整字体和四种语言。实际启动及多目标校验通过；完整 .upd 的相同文件替换在本机失败，现补充仅替换三个变化文件的 2.3.2 → 2.3.3 增量包（约 2.6 MiB）；限完整 2.3.2 安装使用。

Removed unused Qt components, increased package compression, moved build outputs outside push, and added exact obsolete-component cleanup on Setup upgrade. Retains full fonts and all four languages. Native startup and packaged verification passed; Full .upd replacement of identical files failed locally; a ~2.6 MiB delta replacing three changed files is now provided exclusively for complete 2.3.2 installations upgrading to 2.3.3.

## 2.3.2 — 2026-10-11

修复更新后主窗口隐藏；哈希校验移入独立只读进程，覆盖文件关闭阻塞时的超时和暂停，异常时不提交副本。保留 16:9 启动比例。78 项自动化测试通过。

Fixed hidden windows after updates. Isolated read-only hashing now covers blocked file close, timeout, and pause without publishing unverified copies. Retains 16:9 startup sizing. All 78 automated tests passed.


## 2.3.1 — 2026-10-11

### 简体中文

修复校验及暂停时的界面阻塞：集中校验顺序读取，磁盘保存移出全局锁并合并频繁检查点，加入 Windows 读取取消、超时与等待状态。恢复任务时复用完整临时副本，校验失败的副本仍会重新拷贝并验证。启动窗口改为自适应屏幕的 16:9 比例。更新中英文 README 与维护约定。

已通过 73 项自动化测试，覆盖真实 Windows 阻塞读取取消、慢速保存与暂停恢复。

### English

Fixed verification and pause responsiveness with sequential batch reads, state writes outside the global lock, coalesced checkpoints, Windows read cancellation, timeouts, and a storage-wait indicator. Resume reuses complete staged files while failed verification still triggers recopy and verification. Startup now uses a screen-adaptive 16:9 window. Updated bilingual documentation and maintenance guidelines.

Validated with 73 automated tests, including real pending Windows I/O cancellation, slow checkpoint writes, and pause/resume recovery.

## 2.3.0 — 2026-10-11

### 简体中文

新增多目标备份与路径记忆，准备页可直接选择 SHA-256 或 MD5。集中校验采用绿色拷贝、蓝色校验双进度条。新增专用 `.upd` 更新包，支持完整性检查、解压替换、失败回滚和自动重启。

2.2.x 及更早版本需先通过 Setup 升级至 2.3，后续才能使用 `.upd`。已通过 65 项自动化测试及实际升级、回滚验证。

### English

Added multiple backup destinations with remembered paths and SHA-256 or MD5 selection on the preparation page. Batch verification now displays separate green copy and blue verification progress bars. Dedicated `.upd` packages support integrity checks, extraction, file replacement, rollback on failure, and automatic restart.

Users on 2.2.x or earlier must upgrade to 2.3 through Setup before using `.upd`. Validated with 65 automated tests and real upgrade and rollback checks.
