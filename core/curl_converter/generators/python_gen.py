# -*- coding: utf-8 -*-
from .base import BaseGenerator, ParsedRequest
import json


class PythonRequestsGenerator(BaseGenerator):
    name = "Python (requests)"
    language = "python"

    def generate(self, req: ParsedRequest) -> str:
        lines = ["import requests", ""]
        method = req.effective_method.lower()
        lines.append(f'url = "{req.url}"')

        if req.headers:
            lines.append("headers = {")
            for k, v in req.headers.items():
                lines.append(f'    "{k}": "{self._escape(v)}",')
            lines.append("}")

        if req.cookies:
            lines.append("cookies = {")
            for k, v in req.cookies.items():
                lines.append(f'    "{k}": "{self._escape(v)}",')
            lines.append("}")

        if req.json_data is not None:
            lines.append(f"json_data = {json.dumps(req.json_data, indent=4, ensure_ascii=False)}")
        elif req.data:
            if req.data_type == 'form':
                pairs = self._parse_form(req.data)
                lines.append("data = {")
                for k, v in pairs:
                    lines.append(f'    "{k}": "{self._escape(v)}",')
                lines.append("}")
            else:
                lines.append(f'data = {repr(req.data)}')

        if req.form_data:
            lines.append("files = {")
            for f in req.form_data:
                k, _, v = f.partition('=')
                if v.startswith('@'):
                    lines.append(f'    "{k}": open("{self._escape(v[1:])}", "rb"),')
                else:
                    lines.append(f'    "{k}": (None, "{self._escape(v)}"),')
            lines.append("}")

        lines.append("")

        # 构建调用参数
        args = ["url"]
        if req.headers:
            args.append("headers=headers")
        if req.cookies:
            args.append("cookies=cookies")
        if req.json_data is not None:
            args.append("json=json_data")
        elif req.data and req.data_type != 'multipart':
            args.append("data=data")
        if req.form_data:
            args.append("files=files")
        if req.auth:
            args.append(f'auth=("{req.auth[0]}", "{self._escape(req.auth[1])}")')
        if not req.verify_ssl:
            args.append("verify=False")
        if req.proxy:
            args.append(f'proxies={{"http": "{req.proxy}", "https": "{req.proxy}"}}')
        if req.timeout is not None:
            args.append(f"timeout={req.timeout}")
        if req.follow_redirects:
            args.append("allow_redirects=True")

        call_args = ", ".join(args)
        lines.append(f"response = requests.{method}({call_args})")
        lines.append("print(response.status_code)")
        lines.append("print(response.text)")
        return "\n".join(lines)

    @staticmethod
    def _parse_form(data: str):
        pairs = []
        for part in data.split('&'):
            if '=' in part:
                k, v = part.split('=', 1)
                pairs.append((k, v))
        return pairs
