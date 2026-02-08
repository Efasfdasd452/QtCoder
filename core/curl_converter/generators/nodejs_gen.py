# -*- coding: utf-8 -*-
from .base import BaseGenerator, ParsedRequest
import json


class NodeAxiosGenerator(BaseGenerator):
    name = "Node.js (axios)"
    language = "javascript"

    def generate(self, req: ParsedRequest) -> str:
        method = req.effective_method.lower()
        lines = [
            'const axios = require("axios");',
            "",
            "axios({",
            f'  method: "{method}",',
            f'  url: "{req.url}",',
        ]

        if req.headers:
            lines.append("  headers: {")
            for k, v in req.headers.items():
                lines.append(f'    "{k}": "{self._escape(v)}",')
            lines.append("  },")

        if req.json_data is not None:
            lines.append(f"  data: {json.dumps(req.json_data, indent=4, ensure_ascii=False)},")
        elif req.data:
            lines.append(f"  data: {json.dumps(req.data)},")

        if req.auth:
            lines.append("  auth: {")
            lines.append(f'    username: "{req.auth[0]}",')
            lines.append(f'    password: "{self._escape(req.auth[1])}",')
            lines.append("  },")

        if req.proxy:
            lines.append(f'  proxy: {{ host: "{req.proxy}" }},')

        if req.timeout is not None:
            lines.append(f"  timeout: {int(req.timeout * 1000)},")

        if not req.verify_ssl:
            lines.append("  httpsAgent: new (require('https').Agent)({ rejectUnauthorized: false }),")

        if req.follow_redirects:
            lines.append("  maxRedirects: 5,")

        lines.append("})")
        lines.append(".then(response => console.log(response.data))")
        lines.append(".catch(error => console.error(error));")
        return "\n".join(lines)
