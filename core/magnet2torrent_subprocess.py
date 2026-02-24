# -*- coding: utf-8 -*-
"""磁力→种子 子进程入口（纯 Python BEP-9 优先，libtorrent 兜底）

在独立进程中执行，避免任何 DLL 崩溃拖垮主 GUI。
用法: python -m core.magnet2torrent_subprocess <magnet文件路径> <结果pickle路径>
"""

import sys
import pickle
import os


def main():
    # 抑制 Windows "应用程序已停止工作" 弹窗
    if sys.platform == "win32":
        try:
            import ctypes
            # SEM_FAILCRITICALERRORS(0x01) | SEM_NOGPFAULTERRORBOX(0x02)
            ctypes.windll.kernel32.SetErrorMode(0x0003)
        except Exception:
            pass

    if len(sys.argv) < 3:
        sys.stderr.write("usage: python -m core.magnet2torrent_subprocess <magnet_file> <result_file>\n")
        sys.exit(2)

    magnet_path = sys.argv[1]
    result_path = sys.argv[2]

    if not os.path.isfile(magnet_path):
        with open(result_path, "wb") as f:
            pickle.dump((None, None, "磁力文件不存在", ["magnet_file not found"]), f)
        sys.exit(1)

    with open(magnet_path, "r", encoding="utf-8") as f:
        magnet_uri = f.read().strip()

    log_lines = []
    torrent_bytes = None
    suggested_name = None
    err = ""

    # ── 方式一：纯 Python BEP-9（首选，无 DLL 依赖）─────────────────
    try:
        log_lines.append("[子进程] 方式一：纯 Python BEP-9（无需 libtorrent）")
        from core.magnet_fetch import fetch_metadata
        torrent_bytes, suggested_name, err = fetch_metadata(
            magnet_uri, timeout_seconds=50, log_lines=log_lines
        )
        if torrent_bytes:
            log_lines.append("[子进程] 纯 Python 方式成功")
        else:
            log_lines.append("[子进程] 纯 Python 方式失败: " + (err or "未知"))
    except Exception as e:
        import traceback
        log_lines.append("[子进程] magnet_fetch 异常: " + str(e))
        log_lines.append(traceback.format_exc())
        err = "纯 Python 方式异常: " + str(e)

    # ── 方式二：libtorrent 兜底（若纯 Python 未取到数据）──────────────
    if not torrent_bytes:
        log_lines.append("[子进程] 方式二：尝试 libtorrent（兜底）")
        try:
            from core.torrent_magnet import magnet_to_torrent
            tb, sn, lt_err = magnet_to_torrent(magnet_uri, timeout_seconds=30, log_lines=log_lines)
            if tb:
                torrent_bytes  = tb
                suggested_name = sn
                err = lt_err or ""
                log_lines.append("[子进程] libtorrent 方式成功")
            else:
                log_lines.append("[子进程] libtorrent 方式失败: " + (lt_err or "未知"))
                if not err:
                    err = lt_err or "两种方式均未获取到数据"
        except Exception as e2:
            log_lines.append("[子进程] libtorrent 异常: " + str(e2))

    log_lines.append("[子进程] 最终 bytes=%s" % (len(torrent_bytes) if torrent_bytes else None))

    with open(result_path, "wb") as f:
        pickle.dump((torrent_bytes, suggested_name, err or "", log_lines), f)
    sys.exit(0)


if __name__ == "__main__":
    main()
