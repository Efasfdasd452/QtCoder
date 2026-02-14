# -*- coding: utf-8 -*-
"""UUID 生成引擎 — 纯函数，无 UI 依赖"""

import uuid

NAMESPACE_MAP = {
    'DNS':  uuid.NAMESPACE_DNS,
    'URL':  uuid.NAMESPACE_URL,
    'OID':  uuid.NAMESPACE_OID,
    'X500': uuid.NAMESPACE_X500,
}


def generate_uuid(version=4, namespace='DNS', name='',
                  uppercase=False, count=1):
    """批量生成 UUID，返回换行分隔的字符串"""
    results = []
    for _ in range(count):
        if version == 1:
            u = uuid.uuid1()
        elif version == 3:
            if not name:
                raise ValueError("UUID v3 需要提供 name 参数")
            ns = NAMESPACE_MAP.get(namespace, uuid.NAMESPACE_DNS)
            u = uuid.uuid3(ns, name)
        elif version == 4:
            u = uuid.uuid4()
        elif version == 5:
            if not name:
                raise ValueError("UUID v5 需要提供 name 参数")
            ns = NAMESPACE_MAP.get(namespace, uuid.NAMESPACE_DNS)
            u = uuid.uuid5(ns, name)
        else:
            raise ValueError(f"不支持的 UUID 版本: {version}")

        s = str(u)
        if uppercase:
            s = s.upper()
        results.append(s)

    return '\n'.join(results)
