# -*- coding: utf-8 -*-
from .base import BaseGenerator, ParsedRequest
import json


class PowerShellGenerator(BaseGenerator):
    name = "PowerShell"
    language = "powershell"

    def generate(self, req: ParsedRequest) -> str:
        method = req.effective_method
        lines = []

        if req.headers:
            lines.append("$headers = @{")
            for k, v in req.headers.items():
                lines.append(f'    "{k}" = "{self._escape(v)}"')
            lines.append("}")
            lines.append("")

        if req.data:
            lines.append(f"$body = '{self._escape(req.data, chr(39))}'")
            lines.append("")

        params = []
        params.append(f'-Uri "{req.url}"')
        params.append(f"-Method {method}")

        if req.headers:
            params.append("-Headers $headers")

        if req.data:
            params.append("-Body $body")
            ct = req.headers.get("Content-Type", "")
            if ct:
                params.append(f'-ContentType "{ct}"')

        if req.auth:
            lines.append(f'$secPass = ConvertTo-SecureString "{self._escape(req.auth[1])}" -AsPlainText -Force')
            lines.append(f'$cred = New-Object System.Management.Automation.PSCredential("{req.auth[0]}", $secPass)')
            lines.append("")
            params.append("-Credential $cred")

        if not req.verify_ssl:
            params.append("-SkipCertificateCheck")

        if req.proxy:
            params.append(f'-Proxy "{req.proxy}"')

        if req.timeout is not None:
            params.append(f"-TimeoutSec {int(req.timeout)}")

        if req.follow_redirects:
            params.append("-MaximumRedirection 5")

        if req.output_file:
            params.append(f'-OutFile "{req.output_file}"')

        call = "Invoke-WebRequest `\n    " + " `\n    ".join(params)
        lines.append("$response = " + call)
        lines.append("")
        lines.append("Write-Output $response.StatusCode")
        lines.append("Write-Output $response.Content")
        return "\n".join(lines)
