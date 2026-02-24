# -*- coding: utf-8 -*-
"""Pure-Python magnet→torrent downloader — no libtorrent / DLL needed.

Algorithm
─────────
1. 解析磁力链接：info_hash + tracker 列表
2. HTTP tracker announce → compact peer 列表
3. DHT bootstrap get_peers → peer 列表（兜底）
4. 对每个 peer：BEP-10 extension handshake + BEP-9 ut_metadata 交换
5. SHA-1 校验 → 封装 .torrent 字节
"""

import asyncio
import hashlib
import os
import socket
import struct
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

from .bencode import bencode, decode_next   # decode_next(data, pos) → (obj, pos_after)


# ═══════════════════════════════════════════════════════════════
#  Minimal raw bencode decoder（string 值保持 bytes，不 UTF-8 解码）
# ═══════════════════════════════════════════════════════════════

def _bdec(data: bytes):
    """Decode bencode; all string values returned as raw bytes."""
    def _d(s: bytes, i: int):
        c = s[i : i + 1]
        if c == b"i":
            e = s.index(b"e", i + 1)
            return int(s[i + 1 : e]), e + 1
        if c == b"l":
            i += 1; out = []
            while s[i : i + 1] != b"e":
                v, i = _d(s, i); out.append(v)
            return out, i + 1
        if c == b"d":
            i += 1; out = {}
            while s[i : i + 1] != b"e":
                k, i = _d(s, i); v, i = _d(s, i); out[k] = v
            return out, i + 1
        col = s.index(b":", i)
        n = int(s[i:col]); st = col + 1
        return s[st : st + n], st + n
    v, _ = _d(data, 0)
    return v


# ═══════════════════════════════════════════════════════════════
#  BitTorrent 协议常量
# ═══════════════════════════════════════════════════════════════

_PSTR = b"\x13BitTorrent protocol"
_RSV  = bytearray(8)
_RSV[5] |= 0x10          # BEP-10 extension protocol bit
_RSV  = bytes(_RSV)

_UT_META_LOCAL_ID = 3    # 我们向 peer 宣告的 ut_metadata ext-id


# ═══════════════════════════════════════════════════════════════
#  HTTP Tracker announce → peer 列表
# ═══════════════════════════════════════════════════════════════

def _tracker_peers(url: str, info_hash: bytes, peer_id: bytes,
                   timeout: int = 10) -> List[Tuple[str, int]]:
    qs = (
        "?info_hash=" + urllib.parse.quote(info_hash, safe="")
        + "&peer_id="  + urllib.parse.quote(peer_id,   safe="")
        + "&port=6881&uploaded=0&downloaded=0&left=999999999"
        + "&compact=1&event=started&numwant=60"
    )
    try:
        with urllib.request.urlopen(url.rstrip("/") + qs, timeout=timeout) as r:
            resp = _bdec(r.read())
        raw = resp.get(b"peers", b"")
        if not isinstance(raw, bytes):
            return []
        peers = []
        for off in range(0, len(raw) - 5, 6):
            ip   = socket.inet_ntoa(raw[off : off + 4])
            port = struct.unpack(">H", raw[off + 4 : off + 6])[0]
            if port:
                peers.append((ip, port))
        return peers
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════
#  DHT bootstrap get_peers（单轮 UDP 广播，兜底用）
# ═══════════════════════════════════════════════════════════════

_DHT_BOOT = [
    ("router.bittorrent.com",  6881),
    ("router.utorrent.com",    6881),
    ("dht.transmissionbt.com", 6881),
]


def _dht_peers(info_hash: bytes, timeout: int = 8) -> List[Tuple[str, int]]:
    msg = bencode({
        "t": "aa", "y": "q", "q": "get_peers",
        "a": {"id": os.urandom(20), "info_hash": info_hash},
    })
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)
    peers: List[Tuple[str, int]] = []
    try:
        for h, p in _DHT_BOOT:
            try:
                sock.sendto(msg, (socket.gethostbyname(h), p))
            except Exception:
                pass
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, _ = sock.recvfrom(4096)
                r = _bdec(data).get(b"r") or {}
                for entry in (r.get(b"values") or []):
                    if isinstance(entry, bytes) and len(entry) == 6:
                        peers.append((
                            socket.inet_ntoa(entry[:4]),
                            struct.unpack(">H", entry[4:])[0],
                        ))
            except socket.timeout:
                break
            except Exception:
                continue
    finally:
        sock.close()
    return peers


# ═══════════════════════════════════════════════════════════════
#  BEP-10 / BEP-9  per-peer 异步处理
# ═══════════════════════════════════════════════════════════════

class _Peer:
    __slots__ = ("_ih", "_pid", "_pieces", "_size", "_uid")

    def __init__(self, info_hash: bytes, peer_id: bytes):
        self._ih     = info_hash
        self._pid    = peer_id
        self._pieces: Dict[int, bytes] = {}
        self._size   = 0
        self._uid: Optional[int] = None

    async def run(self, host: str, port: int) -> Optional[bytes]:
        try:
            r, w = await asyncio.wait_for(asyncio.open_connection(host, port), 8.0)
        except Exception:
            return None
        try:
            return await asyncio.wait_for(self._proto(r, w), 25.0)
        except Exception:
            return None
        finally:
            try:
                w.close()
            except Exception:
                pass

    async def _proto(self, r, w) -> Optional[bytes]:
        # ── BitTorrent handshake ───────────────────────────────
        w.write(_PSTR + _RSV + self._ih + self._pid)
        await w.drain()
        hs = await r.readexactly(68)
        if hs[28:48] != self._ih or not (hs[25] & 0x10):
            return None

        # ── BEP-10 extension handshake ─────────────────────────
        pl = bencode({"m": {"ut_metadata": _UT_META_LOCAL_ID}})
        w.write(struct.pack(">IB", len(pl) + 2, 20) + b"\x00" + pl)
        await w.drain()

        # ── Message loop ───────────────────────────────────────
        while True:
            n = struct.unpack(">I", await r.readexactly(4))[0]
            if n == 0:
                continue
            if n > 16 << 20:
                return None
            msg = await r.readexactly(n)
            if msg[0] != 20:
                continue
            eid, body = msg[1], msg[2:]
            if eid == 0:
                res = await self._on_ext_hs(body, w)
                if res is not None:
                    return res
            elif eid == _UT_META_LOCAL_ID:
                res = self._on_meta(body)
                if res is not None:
                    return res

    async def _on_ext_hs(self, body: bytes, w) -> Optional[bytes]:
        """处理 peer 的 extension handshake，提取 ut_metadata ID 和 metadata_size。"""
        try:
            d, _ = decode_next(body, 0)   # 用 decode_next：key 为 str，便于 .get()
        except Exception:
            return None
        if not isinstance(d, dict):
            return None
        m   = d.get("m") or {}
        uid = m.get("ut_metadata")
        if not uid:
            return None
        self._uid = uid
        sz = d.get("metadata_size", 0)
        if not sz:
            return None
        self._size = sz
        # 请求所有 metadata piece
        for i in range((sz + 16383) // 16384):
            req = bencode({"msg_type": 0, "piece": i})
            w.write(struct.pack(">IB", len(req) + 2, 20) + bytes([uid]) + req)
        await w.drain()
        return None

    def _on_meta(self, body: bytes) -> Optional[bytes]:
        """处理 ut_metadata 数据包，拼装并校验 info dict。"""
        try:
            d, pos = decode_next(body, 0)   # bencode dict + 后面是原始 piece 数据
        except Exception:
            return None
        if not isinstance(d, dict) or d.get("msg_type") != 1:
            return None
        idx   = d.get("piece",      0)
        total = d.get("total_size", 0)
        if total:
            self._size = total
        self._pieces[idx] = body[pos:]
        if not self._size:
            return None
        need = (self._size + 16383) // 16384
        if len(self._pieces) < need:
            return None
        data = b"".join(self._pieces[i] for i in range(need))[: self._size]
        # SHA-1 校验
        return data if hashlib.sha1(data).digest() == self._ih else None


# ═══════════════════════════════════════════════════════════════
#  并发 peer 协调器
# ═══════════════════════════════════════════════════════════════

async def _fetch_from_peers(info_hash: bytes,
                            peers: List[Tuple[str, int]],
                            log) -> Optional[bytes]:
    peer_id = b"-PY0001-" + os.urandom(12)
    sem     = asyncio.Semaphore(15)   # 最多 15 路并发

    async def one(h: str, p: int):
        async with sem:
            return await _Peer(info_hash, peer_id).run(h, p)

    log("[P] 并发连接 %d 个 peer（最多 15 路）" % len(peers))
    tasks   = [asyncio.ensure_future(one(h, p)) for h, p in peers]
    pending = set(tasks)
    result: Optional[bytes] = None

    while pending and result is None:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            try:
                v = t.result()
                if v is not None:
                    result = v
                    break
            except Exception:
                pass

    for t in pending:
        t.cancel()
    return result


# ═══════════════════════════════════════════════════════════════
#  Public entry point
# ═══════════════════════════════════════════════════════════════

def fetch_metadata(
    magnet_uri: str,
    timeout_seconds: int = 60,
    log_lines: Optional[List[str]] = None,
) -> Tuple[Optional[bytes], Optional[str], str]:
    """纯 Python 磁力→种子，无需 libtorrent。

    Returns:
        (torrent_bytes, suggested_filename, error_message)
    """
    from .torrent_magnet import parse_magnet

    def log(msg: str):
        if log_lines is not None:
            log_lines.append(msg)

    # ── 1. 解析磁力链接 ──────────────────────────────────────
    log("[P1] 解析磁力链接")
    ih_hex, name, trackers = parse_magnet(magnet_uri)
    if not ih_hex or len(ih_hex) != 40:
        return None, None, "无效的磁力链接（缺少有效 info_hash）"
    info_hash = bytes.fromhex(ih_hex)
    log("[P1] hash=%s  trackers=%d" % (ih_hex[:8] + "...", len(trackers)))

    # ── 2. 获取 peer 列表 ────────────────────────────────────
    peers: List[Tuple[str, int]] = []
    peer_id = b"-PY0001-" + os.urandom(12)

    log("[P2] HTTP tracker 宣告")
    for tr in trackers:
        if tr.lower().startswith("http"):
            got = _tracker_peers(tr, info_hash, peer_id)
            if got:
                log("[P2]   %s → %d peers" % (tr[:55], len(got)))
                peers.extend(got)
        if len(peers) >= 150:
            break

    if not peers:
        log("[P3] tracker 无结果，启用 DHT 引导节点")
        peers = _dht_peers(info_hash)
        log("[P3] DHT → %d peers" % len(peers))

    if not peers:
        return (
            None, None,
            "未找到任何 peer。\n\n可能原因：\n"
            "  · 磁力链接无活跃 tracker / DHT 节点\n"
            "  · 网络受限（防火墙/代理）\n"
            "  · 资源已失效（无人做种）",
        )

    # ── 3. BEP-9 metadata 下载 ───────────────────────────────
    log("[P4] BEP-9 metadata 下载（超时 %d 秒）" % timeout_seconds)
    info_bytes: Optional[bytes] = None
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        info_bytes = loop.run_until_complete(
            asyncio.wait_for(
                _fetch_from_peers(info_hash, peers[:120], log),
                timeout=float(max(timeout_seconds - 12, 20)),
            )
        )
    except (asyncio.TimeoutError, TimeoutError):
        log("[P4] 超时，未获取到 metadata")
    except Exception as ex:
        log("[P4] 异常: " + str(ex))
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            for t in pending:
                t.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
        except Exception:
            pass

    if not info_bytes:
        return (
            None, None,
            "未能从 peer 下载 metadata（超时或无响应 peer）。\n\n"
            "建议：\n"
            "  · 确认磁力链接有效且有人做种\n"
            "  · 检查防火墙是否放行对外 TCP 连接（端口 6881 等）\n"
            "  · 使用 qBittorrent / aria2 直接打开磁力链接",
        )

    # ── 4. 封装 .torrent ─────────────────────────────────────
    log("[P5] 封装 .torrent 文件")
    try:
        raw = _bdec(info_bytes)
        raw_name = raw.get(b"name", b"download")
        if isinstance(raw_name, bytes):
            raw_name = raw_name.decode("utf-8", errors="replace")
        suggested = (name or str(raw_name) or "download").strip()
        suggested = suggested.replace("/", "_").replace("\\", "_")
        if not suggested.endswith(".torrent"):
            suggested += ".torrent"
        # 直接包裹 info_bytes，保留原始编码，避免二次 encode 引入差异
        torrent_bytes = b"d4:info" + info_bytes + b"e"
        log("[P5] 完成，.torrent 大小 %d 字节" % len(torrent_bytes))
        return torrent_bytes, suggested, ""
    except Exception as ex:
        return None, None, "封装 .torrent 失败: " + str(ex)
