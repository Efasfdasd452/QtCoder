# -*- coding: utf-8 -*-
"""防火墙规则生成器

支持:
  - iptables      (Linux 经典防火墙)
  - ip6tables     (IPv6 版本)
  - ufw           (Ubuntu/Debian 简化防火墙)
  - firewall-cmd  (firewalld, CentOS/RHEL/Fedora)
  - nftables      (iptables 的现代替代)
  - netsh         (Windows 防火墙)
"""

from dataclasses import dataclass, field
from typing import Optional

# ═══════════════════════════════════════════════════════════════
#  链说明
# ═══════════════════════════════════════════════════════════════

CHAINS = {
    "INPUT": {
        "desc": "入站规则 — 控制从外部进入本机的流量",
        "scene": "保护服务器：只允许特定端口/IP访问本机服务 (如 SSH 22、HTTP 80/443)",
    },
    "OUTPUT": {
        "desc": "出站规则 — 控制从本机发出的流量",
        "scene": (
            "① 限制本机对外连接：阻止恶意软件外连、限制只能访问特定外部服务；"
            "② 本机透明代理：将本机所有出站流量重定向到本地代理端口 "
            "(Clash/V2Ray/sing-box 等)，让不支持代理的程序也能走代理"
        ),
    },
    "FORWARD": {
        "desc": "转发规则 — 控制经过本机转发的流量 (路由/网关)",
        "scene": "当本机作为路由器/网关时，控制内网与外网之间的转发流量",
    },
    "PREROUTING": {
        "desc": "路由前处理 — 数据包进入路由决策之前 (NAT 表)",
        "scene": (
            "① 端口转发 (DNAT)：将外部端口映射到内网主机，如将 80 转发到内网 192.168.1.100:8080；"
            "② 网关透明代理：本机作为网关，将内网设备的所有流量重定向到本地代理端口 "
            "(Clash/V2Ray/sing-box)，内网设备无需任何代理配置即可翻墙"
        ),
    },
    "POSTROUTING": {
        "desc": "路由后处理 — 数据包离开路由决策之后 (NAT 表)",
        "scene": "源地址转换 (SNAT/MASQUERADE)：内网机器通过网关共享公网IP上网",
    },
}

ACTIONS = {
    "ACCEPT":   "允许 — 放行匹配的数据包",
    "DROP":     "丢弃 — 静默丢弃，不回复 (推荐用于外部攻击防御)",
    "REJECT":   "拒绝 — 丢弃并回复 ICMP 错误 (对方能感知被拒绝)",
    "REDIRECT": "重定向 — 透明代理：将流量重定向到本地代理端口 (Clash/V2Ray/sing-box)",
    "LOG":      "记录 — 记录到系统日志后继续匹配后续规则",
}

PROTOCOLS = ["tcp", "udp", "tcp+udp", "icmp", "any"]

PRIVATE_CIDRS = [
    "0.0.0.0/8",
    "10.0.0.0/8",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "224.0.0.0/4",
    "240.0.0.0/4",
]


# ═══════════════════════════════════════════════════════════════
#  规则参数
# ═══════════════════════════════════════════════════════════════

@dataclass
class FwRule:
    action: str = "DROP"              # ACCEPT / DROP / REJECT / REDIRECT / LOG
    chain: str = "INPUT"              # INPUT / OUTPUT / FORWARD / PREROUTING / POSTROUTING
    protocol: str = "tcp"             # tcp / udp / tcp+udp / icmp / any
    src_ip: str = ""                  # 源 IP 或 CIDR，空=any
    dst_ip: str = ""                  # 目标 IP 或 CIDR，空=any
    port: str = ""                    # 端口或范围 (如 80 或 8000:9000)，空=all
    src_port: str = ""                # 源端口 (较少用)
    interface_in: str = ""            # 入站网卡 (如 eth0)
    interface_out: str = ""           # 出站网卡
    comment: str = ""                 # 规则备注
    nat_dst: str = ""                 # DNAT 目标 (PREROUTING 用, 如 192.168.1.100:8080)
    nat_src: str = ""                 # SNAT 源地址 (POSTROUTING 用)
    log_prefix: str = ""              # LOG 前缀
    proxy_port: str = ""              # 透明代理端口 (REDIRECT 用, 如 7893)
    skip_private: bool = False        # 是否跳过私有/保留地址 (透明代理必选)


# ═══════════════════════════════════════════════════════════════
#  生成器
# ═══════════════════════════════════════════════════════════════

def _port_iptables(port: str) -> str:
    """将端口格式转为 iptables 格式 (用冒号表示范围)"""
    return port.replace("-", ":")


def _port_ufw(port: str) -> str:
    """ufw 端口格式 (用冒号表示范围)"""
    return port.replace("-", ":")


def _port_nft(port: str) -> str:
    """nftables 端口格式 (用横杠表示范围)"""
    return port.replace(":", "-")


def _protocols(rule: FwRule) -> list:
    if rule.protocol == "tcp+udp":
        return ["tcp", "udp"]
    return [rule.protocol]


# ─── iptables ─────────────────────────────────────────────────

def _gen_iptables_skip_private(chain_name: str, cmd_prefix: str = "iptables") -> list:
    """生成跳过私有/保留地址的规则 (透明代理必须)"""
    lines = ["# 跳过局域网/保留地址 (避免代理内网流量和回环)"]
    for cidr in PRIVATE_CIDRS:
        lines.append(f"{cmd_prefix} -t nat -A {chain_name} -d {cidr} -j RETURN")
    lines.append("")
    return lines


def gen_iptables(rule: FwRule) -> str:
    lines = []
    lines.append("# iptables — Linux 经典防火墙")
    lines.append(f"# {rule.comment}" if rule.comment else "")

    if rule.action == "REDIRECT":
        return _gen_iptables_redirect(rule, "iptables")

    is_nat = rule.chain in ("PREROUTING", "POSTROUTING")
    table = "-t nat " if is_nat else ""

    for proto in _protocols(rule):
        cmd = f"iptables {table}-A {rule.chain}"

        if proto != "any":
            cmd += f" -p {proto}"

        if rule.interface_in:
            cmd += f" -i {rule.interface_in}"
        if rule.interface_out:
            cmd += f" -o {rule.interface_out}"

        if rule.src_ip:
            cmd += f" -s {rule.src_ip}"
        if rule.dst_ip:
            cmd += f" -d {rule.dst_ip}"

        if rule.src_port and proto in ("tcp", "udp"):
            cmd += f" --sport {_port_iptables(rule.src_port)}"
        if rule.port and proto in ("tcp", "udp"):
            cmd += f" --dport {_port_iptables(rule.port)}"

        if rule.comment:
            cmd += f' -m comment --comment "{rule.comment}"'

        if rule.chain == "PREROUTING" and rule.nat_dst:
            cmd += f" -j DNAT --to-destination {rule.nat_dst}"
        elif rule.chain == "POSTROUTING" and rule.nat_src:
            cmd += f" -j SNAT --to-source {rule.nat_src}"
        elif rule.chain == "POSTROUTING" and not rule.nat_src:
            cmd += " -j MASQUERADE"
        elif rule.action == "LOG":
            prefix = rule.log_prefix or "FW-LOG"
            cmd += f' -j LOG --log-prefix "[{prefix}] "'
        else:
            cmd += f" -j {rule.action}"

        lines.append(cmd)

    return "\n".join(l for l in lines if l)


def _gen_iptables_redirect(rule: FwRule, cmd: str = "iptables") -> str:
    """生成 iptables 透明代理规则"""
    proxy_port = rule.proxy_port or "7893"
    chain_name = rule.comment.replace(" ", "_") if rule.comment else "TRANSPARENT_PROXY"
    chain_name = "".join(c for c in chain_name if c.isalnum() or c == "_")
    mode = "网关模式" if rule.chain == "PREROUTING" else "本机模式"

    lines = []
    lines.append(f"# {cmd} — 透明代理 ({mode})")
    lines.append(f"# 将流量重定向到本地代理端口 {proxy_port}")
    if rule.comment:
        lines.append(f"# {rule.comment}")
    lines.append("")

    lines.append(f"# 创建自定义链")
    lines.append(f"{cmd} -t nat -N {chain_name}")
    lines.append("")

    if rule.skip_private:
        lines += _gen_iptables_skip_private(chain_name, cmd)

    if rule.src_ip:
        lines.append(f"# 仅代理来自 {rule.src_ip} 的流量")

    for proto in _protocols(rule):
        if proto not in ("tcp", "udp"):
            continue
        r = f"{cmd} -t nat -A {chain_name}"
        r += f" -p {proto}"
        if rule.src_ip:
            r += f" -s {rule.src_ip}"
        if rule.port:
            r += f" --dport {_port_iptables(rule.port)}"
        r += f" -j REDIRECT --to-ports {proxy_port}"
        lines.append(r)

    lines.append("")
    lines.append(f"# 将自定义链挂载到 {rule.chain}")

    if rule.chain == "PREROUTING":
        apply_cmd = f"{cmd} -t nat -A PREROUTING"
        if rule.interface_in:
            apply_cmd += f" -i {rule.interface_in}"
        for proto in _protocols(rule):
            if proto not in ("tcp", "udp"):
                continue
            lines.append(f"{apply_cmd} -p {proto} -j {chain_name}")
    elif rule.chain == "OUTPUT":
        for proto in _protocols(rule):
            if proto not in ("tcp", "udp"):
                continue
            lines.append(f"{cmd} -t nat -A OUTPUT -p {proto} -j {chain_name}")

    lines.append("")
    lines.append("# 清理命令 (取消透明代理时执行):")
    lines.append(f"# {cmd} -t nat -D {rule.chain} -j {chain_name}")
    lines.append(f"# {cmd} -t nat -F {chain_name}")
    lines.append(f"# {cmd} -t nat -X {chain_name}")

    return "\n".join(lines)


# ─── ip6tables ────────────────────────────────────────────────

def gen_ip6tables(rule: FwRule) -> str:
    if rule.action == "REDIRECT":
        text = _gen_iptables_redirect(rule, "ip6tables")
    else:
        text = gen_iptables(rule)
        text = text.replace("iptables ", "ip6tables ")
    return text.replace("# iptables", "# ip6tables — IPv6 版本")


# ─── ufw ──────────────────────────────────────────────────────

def gen_ufw(rule: FwRule) -> str:
    lines = []
    lines.append("# ufw — Ubuntu/Debian 简化防火墙")
    lines.append(f"# {rule.comment}" if rule.comment else "")

    if rule.action == "REDIRECT":
        return _gen_ufw_redirect(rule)

    if rule.chain in ("PREROUTING", "POSTROUTING", "FORWARD"):
        lines.append(f"# 注意: ufw 不直接支持 {rule.chain} 链，")
        lines.append("#   需要编辑 /etc/ufw/before.rules 添加 NAT/FORWARD 规则")
        lines.append("")

    action_map = {"ACCEPT": "allow", "DROP": "deny", "REJECT": "reject", "LOG": "allow"}
    ufw_action = action_map.get(rule.action, "deny")

    direction = "in" if rule.chain == "INPUT" else "out" if rule.chain == "OUTPUT" else ""

    for proto in _protocols(rule):
        cmd = f"ufw {ufw_action}"

        if direction:
            cmd += f" {direction}"

        if rule.interface_in and direction == "in":
            cmd += f" on {rule.interface_in}"
        if rule.interface_out and direction == "out":
            cmd += f" on {rule.interface_out}"

        if proto != "any":
            cmd += f" proto {proto}"

        if rule.src_ip:
            cmd += f" from {rule.src_ip}"
        else:
            cmd += " from any"

        if rule.src_port:
            cmd += f" port {_port_ufw(rule.src_port)}"

        if rule.dst_ip:
            cmd += f" to {rule.dst_ip}"
        else:
            cmd += " to any"

        if rule.port:
            cmd += f" port {_port_ufw(rule.port)}"

        if rule.comment:
            cmd += f' comment "{rule.comment}"'

        lines.append(cmd)

    if rule.action == "LOG":
        lines.append("")
        lines.append("# ufw 启用日志:")
        lines.append("ufw logging on")

    return "\n".join(l for l in lines if l)


def _gen_ufw_redirect(rule: FwRule) -> str:
    """ufw 透明代理：需要编辑 /etc/ufw/before.rules"""
    proxy_port = rule.proxy_port or "7893"
    lines = []
    lines.append("# ufw — 透明代理")
    lines.append(f"# {rule.comment}" if rule.comment else "")
    lines.append("#")
    lines.append("# ufw 不直接支持 REDIRECT，需要手动编辑 /etc/ufw/before.rules")
    lines.append("# 在 *filter 段之前添加以下 NAT 规则：")
    lines.append("")
    lines.append("# ---- 添加到 /etc/ufw/before.rules 文件开头 ----")
    lines.append("*nat")
    lines.append(":PREROUTING ACCEPT [0:0]")
    lines.append(":OUTPUT ACCEPT [0:0]")

    if rule.skip_private:
        lines.append("")
        for cidr in PRIVATE_CIDRS:
            lines.append(f"-A PREROUTING -d {cidr} -j RETURN")

    for proto in _protocols(rule):
        if proto not in ("tcp", "udp"):
            continue
        r = f"-A {rule.chain} -p {proto}"
        if rule.src_ip:
            r += f" -s {rule.src_ip}"
        if rule.port:
            r += f" --dport {_port_iptables(rule.port)}"
        r += f" -j REDIRECT --to-ports {proxy_port}"
        lines.append(r)

    lines.append("COMMIT")
    lines.append("# ---- 结束 ----")
    lines.append("")
    lines.append("# 然后重启 ufw:")
    lines.append("ufw disable && ufw enable")
    return "\n".join(lines)


# ─── firewalld ────────────────────────────────────────────────

def gen_firewalld(rule: FwRule) -> str:
    lines = []
    lines.append("# firewall-cmd — firewalld (CentOS/RHEL/Fedora)")
    lines.append(f"# {rule.comment}" if rule.comment else "")

    zone = "public"

    if rule.action == "REDIRECT":
        proxy_port = rule.proxy_port or "7893"
        lines.append(f"# 透明代理：firewalld 不直接支持 REDIRECT")
        lines.append(f"# 推荐使用 --direct 接口调用底层 iptables 规则")
        lines.append("")
        if rule.skip_private:
            for cidr in PRIVATE_CIDRS:
                lines.append(
                    f"firewall-cmd --permanent --direct --add-rule ipv4 nat "
                    f"{rule.chain} 0 -d {cidr} -j RETURN")
            lines.append("")
        for proto in _protocols(rule):
            if proto not in ("tcp", "udp"):
                continue
            r = (f"firewall-cmd --permanent --direct --add-rule ipv4 nat "
                 f"{rule.chain} 1 -p {proto}")
            if rule.src_ip:
                r += f" -s {rule.src_ip}"
            if rule.port:
                r += f" --dport {_port_iptables(rule.port)}"
            r += f" -j REDIRECT --to-ports {proxy_port}"
            lines.append(r)
        lines.append("")
        lines.append("firewall-cmd --reload")
        return "\n".join(l for l in lines if l)

    if rule.chain in ("PREROUTING",) and rule.nat_dst:
        for proto in _protocols(rule):
            if proto == "any":
                proto = "tcp"
            port_part = rule.port or ""
            cmd = (f"firewall-cmd --zone={zone} --permanent "
                   f"--add-forward-port=port={port_part}:proto={proto}"
                   f":toaddr={rule.nat_dst.split(':')[0]}")
            if ":" in rule.nat_dst:
                cmd += f":toport={rule.nat_dst.split(':')[1]}"
            lines.append(cmd)
        lines.append("firewall-cmd --reload")
        return "\n".join(l for l in lines if l)

    if rule.chain == "POSTROUTING":
        lines.append(f"firewall-cmd --zone={zone} --permanent --add-masquerade")
        lines.append("firewall-cmd --reload")
        return "\n".join(l for l in lines if l)

    for proto in _protocols(rule):
        if rule.action == "ACCEPT" and rule.port and proto in ("tcp", "udp"):
            lines.append(
                f"firewall-cmd --zone={zone} --permanent "
                f"--add-port={_port_iptables(rule.port)}/{proto}")
        elif rule.action in ("DROP", "REJECT"):
            rich = f'firewall-cmd --zone={zone} --permanent --add-rich-rule=\''
            rich += f'rule family="ipv4"'
            if rule.src_ip:
                rich += f' source address="{rule.src_ip}"'
            if rule.dst_ip:
                rich += f' destination address="{rule.dst_ip}"'
            if rule.port and proto in ("tcp", "udp"):
                rich += f' port port="{_port_iptables(rule.port)}" protocol="{proto}"'
            if proto == "icmp":
                rich += ' icmp-block-inversion'
            action_word = "drop" if rule.action == "DROP" else "reject"
            rich += f' {action_word}\''
            lines.append(rich)
        elif rule.action == "LOG":
            rich = f'firewall-cmd --zone={zone} --permanent --add-rich-rule=\''
            rich += f'rule family="ipv4"'
            if rule.src_ip:
                rich += f' source address="{rule.src_ip}"'
            if rule.port and proto in ("tcp", "udp"):
                rich += f' port port="{_port_iptables(rule.port)}" protocol="{proto}"'
            prefix = rule.log_prefix or "FW-LOG"
            rich += f' log prefix="{prefix}" level="info"\''
            lines.append(rich)
        elif rule.action == "ACCEPT" and not rule.port:
            rich = f'firewall-cmd --zone={zone} --permanent --add-rich-rule=\''
            rich += f'rule family="ipv4"'
            if rule.src_ip:
                rich += f' source address="{rule.src_ip}"'
            if proto not in ("any",):
                rich += f' protocol value="{proto}"'
            rich += ' accept\''
            lines.append(rich)

    lines.append("firewall-cmd --reload")
    return "\n".join(l for l in lines if l)


# ─── nftables ─────────────────────────────────────────────────

def gen_nftables(rule: FwRule) -> str:
    lines = []
    lines.append("# nftables — iptables 的现代替代 (Debian 10+, RHEL 8+)")
    lines.append(f"# {rule.comment}" if rule.comment else "")

    if rule.action == "REDIRECT":
        return _gen_nftables_redirect(rule)

    is_nat = rule.chain in ("PREROUTING", "POSTROUTING")
    table = "nat" if is_nat else "filter"
    chain = rule.chain.lower()
    hook = chain
    nft_action = {
        "ACCEPT": "accept", "DROP": "drop",
        "REJECT": "reject", "LOG": "log",
    }.get(rule.action, "drop")

    lines.append(f"# 先确保表和链存在:")
    if is_nat:
        lines.append(f"nft add table ip nat")
        lines.append(f"nft add chain ip nat {chain} "
                      f"{{ type nat hook {hook} priority 0 \\; }}")
    else:
        lines.append(f"nft add table ip filter")
        lines.append(f"nft add chain ip filter {chain} "
                      f"{{ type filter hook {hook} priority 0 \\; }}")
    lines.append("")
    lines.append("# 添加规则:")

    for proto in _protocols(rule):
        parts = [f"nft add rule ip {table} {chain}"]

        if proto not in ("any",):
            parts.append(f"ip protocol {proto}")

        if rule.src_ip:
            parts.append(f"ip saddr {rule.src_ip}")
        if rule.dst_ip:
            parts.append(f"ip daddr {rule.dst_ip}")

        if rule.interface_in:
            parts.append(f'iifname "{rule.interface_in}"')
        if rule.interface_out:
            parts.append(f'oifname "{rule.interface_out}"')

        if rule.src_port and proto in ("tcp", "udp"):
            parts.append(f"{proto} sport {_port_nft(rule.src_port)}")
        if rule.port and proto in ("tcp", "udp"):
            parts.append(f"{proto} dport {_port_nft(rule.port)}")

        if rule.chain == "PREROUTING" and rule.nat_dst:
            parts.append(f"dnat to {rule.nat_dst}")
        elif rule.chain == "POSTROUTING" and rule.nat_src:
            parts.append(f"snat to {rule.nat_src}")
        elif rule.chain == "POSTROUTING":
            parts.append("masquerade")
        elif rule.action == "LOG":
            prefix = rule.log_prefix or "FW-LOG"
            parts.append(f'log prefix "{prefix} "')
        else:
            parts.append(nft_action)

        if rule.comment:
            parts.append(f'comment "{rule.comment}"')

        lines.append(" ".join(parts))

    return "\n".join(l for l in lines if l)


def _gen_nftables_redirect(rule: FwRule) -> str:
    """nftables 透明代理"""
    proxy_port = rule.proxy_port or "7893"
    chain = rule.chain.lower()
    hook = chain
    lines = []
    lines.append("# nftables — 透明代理")
    lines.append(f"# {rule.comment}" if rule.comment else "")
    lines.append("")
    lines.append("nft add table ip transparent_proxy")
    lines.append(
        f"nft add chain ip transparent_proxy {chain} "
        f"{{ type nat hook {hook} priority -100 \\; }}")
    lines.append("")

    if rule.skip_private:
        lines.append("# 跳过局域网/保留地址")
        for cidr in PRIVATE_CIDRS:
            lines.append(
                f"nft add rule ip transparent_proxy {chain} "
                f"ip daddr {cidr} return")
        lines.append("")

    lines.append("# 重定向到代理端口")
    for proto in _protocols(rule):
        if proto not in ("tcp", "udp"):
            continue
        r = f"nft add rule ip transparent_proxy {chain} ip protocol {proto}"
        if rule.src_ip:
            r += f" ip saddr {rule.src_ip}"
        if rule.port:
            r += f" {proto} dport {_port_nft(rule.port)}"
        r += f" redirect to :{proxy_port}"
        lines.append(r)

    lines.append("")
    lines.append("# 清理命令:")
    lines.append("# nft delete table ip transparent_proxy")
    return "\n".join(lines)


# ─── Windows netsh ────────────────────────────────────────────

def gen_netsh(rule: FwRule) -> str:
    lines = []
    lines.append("# netsh advfirewall — Windows 防火墙")
    lines.append(f"# {rule.comment}" if rule.comment else "")

    if rule.action == "REDIRECT":
        proxy_port = rule.proxy_port or "7893"
        lines.append("")
        lines.append("# Windows 不支持 iptables 式的 REDIRECT")
        lines.append("# 以下是 Windows 上实现透明代理的替代方案：")
        lines.append("")
        lines.append("# 方案 1: netsh portproxy (仅 TCP，简单场景)")
        for proto in _protocols(rule):
            if proto != "tcp":
                continue
            port = rule.port or "0"
            lines.append(
                f"netsh interface portproxy add v4tov4 "
                f"listenport={port} listenaddress=0.0.0.0 "
                f"connectport={proxy_port} connectaddress=127.0.0.1")
        lines.append("")
        lines.append("# 查看已设置的转发:")
        lines.append("netsh interface portproxy show all")
        lines.append("")
        lines.append("# 删除转发:")
        if rule.port:
            lines.append(
                f"# netsh interface portproxy delete v4tov4 "
                f"listenport={rule.port} listenaddress=0.0.0.0")
        lines.append("")
        lines.append("# 方案 2: 推荐使用专用工具")
        lines.append("#   - Clash for Windows (TUN 模式)")
        lines.append("#   - Netch (进程代理/TUN)")
        lines.append("#   - Proxifier (全局进程代理)")
        lines.append("#   - tun2socks (TUN 虚拟网卡)")
        return "\n".join(l for l in lines if l)

    if rule.chain in ("PREROUTING", "POSTROUTING", "FORWARD"):
        lines.append(f"# 注意: Windows 防火墙不支持 {rule.chain}，")
        lines.append("#   需使用 RRAS (路由和远程访问) 或第三方工具实现 NAT/转发")
        return "\n".join(l for l in lines if l)

    direction = "in" if rule.chain == "INPUT" else "out"
    action = "allow" if rule.action == "ACCEPT" else "block"
    name = rule.comment or f"Rule-{rule.chain}-{rule.port or 'all'}"

    for proto in _protocols(rule):
        if proto == "any":
            proto = "any"
        cmd = (f'netsh advfirewall firewall add rule '
               f'name="{name}" '
               f'dir={direction} '
               f'action={action}')

        if proto != "any":
            cmd += f" protocol={proto}"
        else:
            cmd += " protocol=any"

        if rule.port:
            cmd += f" localport={rule.port.replace(':', '-')}"
        if rule.src_port:
            cmd += f" remoteport={rule.src_port.replace(':', '-')}"
        if rule.src_ip and direction == "in":
            cmd += f" remoteip={rule.src_ip}"
        if rule.dst_ip and direction == "out":
            cmd += f" remoteip={rule.dst_ip}"

        if rule.interface_in or rule.interface_out:
            iface = rule.interface_in or rule.interface_out
            cmd += f' interfacetype=any'

        cmd += " enable=yes"
        lines.append(cmd)

    if rule.action == "LOG":
        lines.append("")
        lines.append("# Windows 防火墙启用日志:")
        lines.append('netsh advfirewall set allprofiles logging '
                      'droppedconnections enable')
        lines.append('netsh advfirewall set allprofiles logging '
                      'allowedconnections enable')

    return "\n".join(l for l in lines if l)


# ═══════════════════════════════════════════════════════════════
#  统一入口
# ═══════════════════════════════════════════════════════════════

GENERATORS = {
    "iptables":     ("Linux iptables",              gen_iptables),
    "ip6tables":    ("Linux ip6tables (IPv6)",      gen_ip6tables),
    "ufw":          ("Ubuntu/Debian ufw",           gen_ufw),
    "firewalld":    ("CentOS/RHEL firewall-cmd",    gen_firewalld),
    "nftables":     ("Linux nftables (现代)",        gen_nftables),
    "netsh":        ("Windows netsh advfirewall",   gen_netsh),
}


def generate_all(rule: FwRule) -> str:
    """生成所有防火墙格式的规则，返回格式化文本"""
    sections = []

    # 链信息
    chain_info = CHAINS.get(rule.chain, {})
    header = []
    header.append("=" * 60)
    header.append(f"  防火墙规则生成结果")
    header.append("=" * 60)
    header.append(f"  链:     {rule.chain} — {chain_info.get('desc', '')}")
    header.append(f"  场景:   {chain_info.get('scene', '')}")
    header.append(f"  动作:   {rule.action} — {ACTIONS.get(rule.action, '')}")
    header.append(f"  协议:   {rule.protocol}")
    if rule.src_ip:
        header.append(f"  源 IP:  {rule.src_ip}")
    if rule.dst_ip:
        header.append(f"  目标 IP: {rule.dst_ip}")
    if rule.port:
        header.append(f"  目标端口: {rule.port}")
    if rule.src_port:
        header.append(f"  源端口: {rule.src_port}")
    if rule.interface_in:
        header.append(f"  入站网卡: {rule.interface_in}")
    if rule.interface_out:
        header.append(f"  出站网卡: {rule.interface_out}")
    if rule.proxy_port:
        header.append(f"  代理端口: {rule.proxy_port}")
    if rule.skip_private:
        header.append(f"  跳过私有地址: 是")
    if rule.comment:
        header.append(f"  备注:   {rule.comment}")
    header.append("=" * 60)
    sections.append("\n".join(header))

    for key, (label, gen_func) in GENERATORS.items():
        sections.append("")
        sections.append(f"{'─' * 60}")
        sections.append(f"  {label}")
        sections.append(f"{'─' * 60}")
        sections.append(gen_func(rule))

    return "\n".join(sections)


def generate_one(rule: FwRule, fw_type: str) -> str:
    """生成指定防火墙类型的规则"""
    if fw_type in GENERATORS:
        return GENERATORS[fw_type][1](rule)
    return ""
