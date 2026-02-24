# -*- coding: utf-8 -*-
"""BT 种子与磁力链接互转

- 种子 → 磁力：纯本地，解析 .torrent (bencode)，计算 info_hash，拼 magnet URI。
- 磁力 → 种子：通过 libtorrent 从 DHT/tracker 拉取 metadata 并生成 .torrent（需联网）。
"""

import hashlib
import urllib.parse
from typing import List, Optional, Tuple

from .bencode import bdecode


# ---------------------------------------------------------------------------
#  种子 → 磁力
# ---------------------------------------------------------------------------


def _find_info_bytes(data: bytes) -> bytes:
    """从 .torrent 原始字节中定位并返回 info 字典的原始字节（用于计算 info_hash）。"""
    # 标准 .torrent 中 info 键为 "4:info"，后面紧跟 info 字典的 'd'
    idx = data.find(b"4:info")
    if idx == -1:
        raise ValueError("torrent 中未找到 info 段")
    start = idx + 6  # len("4:info") == 6
    if start >= len(data) or data[start : start + 1] != b"d":
        raise ValueError("info 段格式异常")
    # 找到与起始 'd' 配对的 'e'，正确跳过 string 段
    depth = 0
    i = start
    while i < len(data):
        c = data[i : i + 1]
        if c == b"d" or c == b"l":
            depth += 1
            i += 1
        elif c == b"e":
            depth -= 1
            if depth == 0:
                return data[start : i + 1]
            i += 1
        elif c == b"i":
            end_e = data.find(b"e", i + 1)
            if end_e == -1:
                break
            i = end_e + 1
        elif c in b"0123456789":
            colon = data.find(b":", i)
            if colon == -1:
                break
            length = int(data[i:colon].decode("ascii"))
            i = colon + 1 + length
        else:
            i += 1
    raise ValueError("info 段未正确闭合")


def _collect_trackers(meta: dict) -> List[str]:
    """从解析后的 torrent 中收集所有 tracker URL。"""
    trackers: List[str] = []
    if "announce" in meta and meta["announce"]:
        trackers.append(meta["announce"].strip())
    for item in meta.get("announce-list", []):
        if isinstance(item, list):
            for u in item:
                if u and u.strip() and u.strip() not in trackers:
                    trackers.append(u.strip())
        elif isinstance(item, str) and item.strip() and item.strip() not in trackers:
            trackers.append(item.strip())
    return trackers


def _get_name(meta: dict) -> str:
    """获取 torrent 名称（用于 magnet 的 dn=）。"""
    info = meta.get("info") or {}
    if isinstance(info, dict):
        name = info.get("name") or ""
        if isinstance(name, bytes):
            return name.decode("utf-8", errors="replace")
        return name or "torrent"
    return "torrent"


def torrent_to_magnet(torrent_content: bytes) -> str:
    """将 .torrent 文件内容（字节）转为 magnet 链接。

    Args:
        torrent_content: 完整的 .torrent 文件内容

    Returns:
        magnet:?xt=urn:btih:... 格式的字符串
    """
    try:
        meta = bdecode(torrent_content)
    except Exception as e:
        return f"解析种子失败: {e}"

    if not isinstance(meta, dict):
        return "无效的种子结构：根节点应为字典"

    try:
        info_bytes = _find_info_bytes(torrent_content)
    except ValueError as e:
        return f"定位 info 段失败: {e}"

    info_hash = hashlib.sha1(info_bytes).hexdigest()
    name = _get_name(meta)
    trackers = _collect_trackers(meta)

    params = ["xt=urn:btih:" + info_hash]
    if name:
        params.append("dn=" + urllib.parse.quote(name, safe=""))
    for tr in trackers[:10]:
        if tr:
            params.append("tr=" + urllib.parse.quote(tr, safe=""))

    return "magnet:?" + "&".join(params)


# ---------------------------------------------------------------------------
#  磁力 → 种子（需联网，依赖 libtorrent）
# ---------------------------------------------------------------------------


def parse_magnet(magnet: str) -> Tuple[Optional[str], str, List[str]]:
    """解析 magnet 链接，返回 (info_hash_hex, name, trackers)。"""
    if not magnet.strip().startswith("magnet:?"):
        return None, "", []

    parsed = urllib.parse.urlparse(magnet.strip())
    qs = urllib.parse.parse_qs(parsed.query)
    info_hash = None
    for key in ("xt", "xt.1"):
        for v in qs.get(key, []):
            if v.startswith("urn:btih:"):
                info_hash = v[9:].strip()
                break
        if info_hash:
            break
    if not info_hash:
        return None, "", []

    if len(info_hash) == 40 and all(c in "0123456789abcdefABCDEF" for c in info_hash):
        info_hash_hex = info_hash.lower()
    elif len(info_hash) == 32:
        try:
            import base64
            info_hash_hex = base64.b32decode(
                info_hash.upper() + "=" * (8 - len(info_hash) % 8)
            ).hex()
        except Exception:
            info_hash_hex = info_hash
    else:
        info_hash_hex = info_hash

    name = ""
    for dn in qs.get("dn", []):
        name = urllib.parse.unquote(dn)
        break
    trackers = [urllib.parse.unquote(t) for t in qs.get("tr", []) if t]
    return info_hash_hex, name, trackers


def magnet_to_torrent(
    magnet_uri: str,
    timeout_seconds: int = 30,
    log_lines: Optional[List[str]] = None,
) -> Tuple[Optional[bytes], Optional[str], str]:
    """将磁力链接转为 .torrent 文件内容（需联网）。

    log_lines: 若传入 list，会依次 append 各步骤日志，便于排查。

    Returns:
        (torrent_bytes, suggested_filename, error_message)。
    """
    def log(msg: str) -> None:
        if log_lines is not None:
            log_lines.append(msg)

    try:
        log("[1] 开始 import libtorrent")
        import libtorrent as lt
        log("[2] import libtorrent 成功")
    except (ImportError, OSError) as e:
        err_msg = str(e)
        log("[2] %s: %s" % (type(e).__name__, err_msg))
        # 判断：libtorrent 根本未安装 vs 已安装但 DLL/依赖缺失
        # "No module named 'libtorrent'" 表示模块本身不存在（未安装）
        # 其余 ImportError/OSError 均表示已安装但运行时依赖缺失
        not_installed = isinstance(e, ImportError) and "No module named" in err_msg
        if not_installed:
            return (
                None,
                None,
                "磁力→种子需要 libtorrent，但当前环境未安装。\n\n"
                "请安装: pip install libtorrent\n"
                "（Windows 可从 https://github.com/arvidn/libtorrent/releases 下载对应 wheel）\n\n"
                "原始错误: %s" % err_msg,
            )
        return (
            None,
            None,
            "libtorrent 导入失败（DLL/依赖缺失）：\n  %s\n\n"
            "常见原因：缺少 Visual C++ 运行库，请下载安装：\n"
            "  https://aka.ms/vs/17/release/vc_redist.x64.exe\n\n"
            "若已安装 VC++ 运行库仍报错，建议改用以下方式处理磁力链接：\n"
            "  qBittorrent / aria2 / 迅雷 等客户端直接打开磁力链接" % err_msg,
        )

    log("[3] 解析磁力链接")
    info_hash_hex, suggested_name, trackers = parse_magnet(magnet_uri)
    if not info_hash_hex or len(info_hash_hex) != 40:
        log("[3] 解析失败: btih 无效或缺失")
        return None, None, "无效的磁力链接：未找到有效的 btih (40 位 hex)"
    log("[3] btih=%s trackers=%d" % (info_hash_hex[:8] + "...", len(trackers)))

    import time

    params = None
    if hasattr(lt, "parse_magnet_uri"):
        try:
            log("[4] 使用 parse_magnet_uri")
            params = lt.parse_magnet_uri(magnet_uri.strip())
            log("[4] parse_magnet_uri 成功")
        except Exception as e:
            log("[4] parse_magnet_uri 异常: " + str(type(e).__name__) + " " + str(e))
            pass
    if params is None:
        try:
            log("[5] 使用 add_torrent_params 构造")
            params = lt.add_torrent_params()
            if hasattr(params, "info_hashes"):
                params.info_hashes = lt.info_hash_t(bytes.fromhex(info_hash_hex))
            elif hasattr(params, "info_hash"):
                params.info_hash = bytes.fromhex(info_hash_hex)
            else:
                log("[5] 无法设置 info_hash")
                return None, None, "当前 libtorrent 版本无法设置 info_hash"
            if trackers:
                params.trackers = trackers
            log("[5] add_torrent_params 构造成功")
        except Exception as e:
            log("[5] 异常: " + str(type(e).__name__) + " " + str(e))
            return None, None, "构造参数失败: " + str(e)

    try:
        log("[6] 创建 session")
        ses = lt.session()
        log("[7] add_torrent")
        handle = ses.add_torrent(params)
        log("[8] 等待 metadata (最多 %d 秒)" % timeout_seconds)
        deadline = time.time() + timeout_seconds
        step = 0
        while not handle.has_metadata() and time.time() < deadline:
            try:
                ses.post_torrent_updates()
            except Exception:
                pass
            time.sleep(0.5)
            step += 1
            if step % 6 == 0:
                log("[8] 已等待 %.1f 秒" % (step * 0.5))

        if not handle.has_metadata():
            try:
                ses.remove_torrent(handle)
            except Exception:
                pass
            log("[8] 超时，未获取到 metadata")
            return None, None, "获取 metadata 超时，请检查网络或稍后重试"

        log("[9] 已获取 metadata，生成 .torrent")
        ti = handle.get_torrent_info()
        ct = lt.create_torrent(ti)
        entry = ct.generate()
        torrent_bytes = bytes(lt.bencode(entry))
        try:
            ses.remove_torrent(handle)
        except Exception:
            pass
        suggested = (suggested_name.strip() or "download").replace("/", "_").replace("\\", "_")
        if not suggested.endswith(".torrent"):
            suggested = suggested + ".torrent"
        log("[9] 完成，大小 %d 字节" % len(torrent_bytes))
        return torrent_bytes, suggested, ""
    except Exception as e:
        log("[异常] " + str(type(e).__name__) + ": " + str(e))
        return None, None, "生成种子失败: " + str(e)
