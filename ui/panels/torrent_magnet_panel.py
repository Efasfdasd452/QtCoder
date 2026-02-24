# -*- coding: utf-8 -*-
"""BT 种子与磁力链接互转面板"""

import os
import re
import sys
import tempfile
import pickle
import subprocess
from PyQt5.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QGroupBox,
    QRadioButton,
    QButtonGroup,
    QLabel,
)
from PyQt5.QtCore import QThread, pyqtSignal
from .base_panel import BasePanel
from core.torrent_magnet import torrent_to_magnet


def _sanitize_filename(name: str) -> str:
    """去掉文件名中的非法字符。"""
    name = (name or "download").strip()
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name or "download"


# 子进程崩溃时的说明（0xC0000005 = Windows 访问冲突，多为 libtorrent 等原生库不兼容）
_SUBPROCESS_CRASH_MSG = """磁力→种子 子进程异常退出（退出码 0xC0000005）。

这通常表示 libtorrent 与当前 Python/系统环境不兼容（如 VC 运行库、架构不一致等），导致加载或调用时发生访问冲突。

建议：
1) 使用「种子→磁力」功能（纯本地，不依赖 libtorrent）；
2) 用 qBittorrent、aria2、迅雷 等工具直接打开磁力链接下载；
3) 若必须在本机生成 .torrent，可尝试在 WSL 或另一台机器上使用本工具。"""


class MagnetToTorrentWorker(QThread):
    """在独立子进程中执行磁力→种子，避免 libtorrent 崩溃(0xC0000005) 拖垮主进程。"""
    result_ready = pyqtSignal(object, object, str, str)  # (torrent_bytes, suggested_name, error_msg, log_text)

    def __init__(self, magnet_uri: str, project_root: str, parent=None):
        super().__init__(parent)
        self.magnet_uri = magnet_uri
        self.project_root = project_root

    def run(self):
        log_lines = []
        magnet_path = None
        result_path = None
        try:
            fd_m, magnet_path = tempfile.mkstemp(suffix=".magnet", prefix="qtcoder_", text=True)
            with os.fdopen(fd_m, "w", encoding="utf-8") as f:
                f.write(self.magnet_uri)
            fd_r, result_path = tempfile.mkstemp(suffix=".pkl", prefix="qtcoder_")
            os.close(fd_r)

            log_lines.append("子进程模式: 不在此进程加载 libtorrent")
            log_lines.append("project_root: %s" % self.project_root)
            log_lines.append("magnet 临时文件: %s" % magnet_path)
            log_lines.append("结果临时文件: %s" % result_path)

            popen_kwargs = dict(
                cwd=self.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            proc = subprocess.Popen(
                [sys.executable, "-m", "core.magnet2torrent_subprocess", magnet_path, result_path],
                **popen_kwargs,
            )
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                self.result_ready.emit(
                    None, None,
                    "子进程超时（60 秒），已终止。",
                    "\n".join(log_lines) + "\n\n[超时] 子进程未在 60 秒内结束。",
                )
                return

            log_lines.append("子进程退出码: %s" % proc.returncode)

            if proc.returncode != 0:
                # 0xC0000005 (ACCESS_VIOLATION) 在 Windows 下常以 -1073741819 返回
                if proc.returncode == -1073741819:
                    log_lines.append("(退出码 0xC0000005 = 访问冲突，多为 libtorrent 库不兼容)")
                    err = _SUBPROCESS_CRASH_MSG
                else:
                    err = "子进程异常退出，退出码: %s" % proc.returncode
                if proc.stdout:
                    log_lines.append("stdout: " + (proc.stdout.read() or b"").decode("utf-8", errors="replace")[:500])
                if proc.stderr:
                    log_lines.append("stderr: " + (proc.stderr.read() or b"").decode("utf-8", errors="replace")[:500])
                self.result_ready.emit(None, None, err, "\n".join(log_lines))
                return

            with open(result_path, "rb") as f:
                data = pickle.load(f)
            torrent_bytes, suggested_name, err, sub_log = data
            log_lines.append("子进程日志:")
            log_lines.extend(sub_log if isinstance(sub_log, list) else [sub_log])
            self.result_ready.emit(
                torrent_bytes,
                suggested_name,
                err or "",
                "\n".join(log_lines),
            )
        except Exception as e:
            import traceback
            log_lines.append("Worker 异常: " + str(type(e).__name__) + ": " + str(e))
            log_lines.append(traceback.format_exc())
            self.result_ready.emit(None, None, "执行异常: " + str(e), "\n".join(log_lines))
        finally:
            if magnet_path and os.path.isfile(magnet_path):
                try:
                    os.unlink(magnet_path)
                except Exception:
                    pass
            if result_path and os.path.isfile(result_path):
                try:
                    os.unlink(result_path)
                except Exception:
                    pass


class TorrentMagnetPanel(BasePanel):
    """种子→磁力（纯本地）/ 磁力→种子（需联网，子进程执行，需指定输出文件夹）。"""

    def __init__(self, parent=None):
        self._torrent_bytes = None
        self._m2t_worker = None
        super().__init__(parent)

    def _build_ui(self):
        super()._build_ui()
        self.input_area.setPlaceholderText(
            "种子→磁力：请点击「导入文件」选择 .torrent 文件，或粘贴 .torrent 路径\n"
            "磁力→种子：在此粘贴 magnet:?xt=urn:btih:... 链接"
        )

    def build_controls(self, layout):
        group = QGroupBox("转换方向")
        g = QVBoxLayout(group)
        self._mode_group = QButtonGroup(self)
        self._btn_t2m = QRadioButton("种子 → 磁力链接（纯本地，不联网）")
        self._btn_m2t = QRadioButton("磁力链接 → 种子文件（需联网，需指定输出文件夹）")
        self._btn_t2m.setChecked(True)
        self._mode_group.addButton(self._btn_t2m)
        self._mode_group.addButton(self._btn_m2t)
        g.addWidget(self._btn_t2m)
        g.addWidget(self._btn_m2t)
        layout.addWidget(group)

        row = QHBoxLayout()
        row.addWidget(QLabel("输出文件夹:"))
        self._out_dir = QLineEdit()
        self._out_dir.setPlaceholderText("磁力→种子时必填，用于保存 .torrent 文件")
        self._out_dir.setReadOnly(True)
        row.addWidget(self._out_dir, stretch=1)
        self._btn_choose_dir = QPushButton("选择目录")
        self._btn_choose_dir.setFixedWidth(90)
        self._btn_choose_dir.clicked.connect(self._choose_output_dir)
        row.addWidget(self._btn_choose_dir)
        layout.addLayout(row)

    def _choose_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出文件夹", self._out_dir.text() or "")
        if path:
            self._out_dir.setText(path)
            self._status("输出文件夹: %s" % path)

    def _import_file(self):
        if self._btn_t2m.isChecked():
            path, _ = QFileDialog.getOpenFileName(
                self, "选择种子文件", "",
                "种子文件 (*.torrent);;所有文件 (*)")
            if not path:
                return
            try:
                with open(path, "rb") as f:
                    self._torrent_bytes = f.read()
                self.input_area.setPlainText(path)
                self._status("已加载种子: %s（纯本地）" % os.path.basename(path))
            except Exception as e:
                QMessageBox.warning(self, "导入失败", str(e))
        else:
            super()._import_file()

    def _on_m2t_finished(self, torrent_bytes, suggested_name, error_msg, log_text):
        """磁力→种子后台任务结束，在主线程更新 UI。"""
        self._exec_btn.setEnabled(True)
        self._exec_btn.setText("▶  执行")
        self._m2t_worker = None

        if error_msg:
            # 失败时：输出区显示错误，日志附在末尾供排查
            detail = "\n\n──── 详细日志 ────\n" + (log_text or "(无日志)")
            self.output_area.setPlainText(error_msg + detail)
            self._out_label.setText("")
            self._status("转换失败")
            return
        if not torrent_bytes:
            self.output_area.setPlainText("未获取到种子数据")
            self._status("转换失败")
            return

        out_dir = self._out_dir.text().strip()
        if not out_dir or not os.path.isdir(out_dir):
            self.output_area.setPlainText("种子已生成，但未指定输出文件夹，请先选择目录后再试。\n（本次数据未保存）")
            self._out_label.setText("%d 字节" % len(torrent_bytes))
            self._status("请指定输出文件夹并重新执行以保存")
            return

        filename = _sanitize_filename(
            (suggested_name or "download").replace(".torrent", "")
        ) + ".torrent"
        filepath = os.path.join(out_dir, filename)
        try:
            with open(filepath, "wb") as f:
                f.write(torrent_bytes)
        except Exception as e:
            self.output_area.setPlainText("保存失败: %s" % e)
            self._status("保存失败")
            return
        self.output_area.setPlainText("种子已生成并保存至:\n%s" % filepath)
        self._out_label.setText("%d 字节" % len(torrent_bytes))
        self._status("已保存: %s" % filename)

    def _on_execute(self):
        if self._btn_t2m.isChecked():
            data = self._torrent_bytes
            if not data:
                path = self.input_area.toPlainText().strip()
                if path and os.path.isfile(path) and path.lower().endswith(".torrent"):
                    try:
                        with open(path, "rb") as f:
                            data = f.read()
                    except Exception:
                        pass
                if not data:
                    self._status("请先通过「导入文件」选择 .torrent 文件")
                    self.output_area.setPlainText("")
                    return
            result = torrent_to_magnet(data)
            self.output_area.setPlainText(result)
            self._out_label.setText("%d 字符" % len(result))
            self._status("转换完成（未联网）")
        else:
            magnet = self.input_area.toPlainText().strip()
            if not magnet or not magnet.startswith("magnet:?"):
                self._status("请输入有效的磁力链接 (magnet:?...)")
                self.output_area.setPlainText("")
                return
            out_dir = self._out_dir.text().strip()
            if not out_dir or not os.path.isdir(out_dir):
                self._status("请先指定输出文件夹")
                self.output_area.setPlainText("请点击「选择目录」指定保存 .torrent 的文件夹。")
                return
            if self._m2t_worker is not None and self._m2t_worker.isRunning():
                self._status("正在获取中，请稍候…")
                return
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self._exec_btn.setEnabled(False)
            self._exec_btn.setText("获取中…")
            self.output_area.setPlainText("正在子进程中获取 metadata（约需数秒～半分钟），请勿关闭窗口…")
            self._status("子进程获取中…")
            self._m2t_worker = MagnetToTorrentWorker(magnet, project_root)
            self._m2t_worker.result_ready.connect(self._on_m2t_finished)
            self._m2t_worker.finished.connect(self._m2t_worker.deleteLater)
            self._m2t_worker.start()
