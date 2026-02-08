# -*- coding: utf-8 -*-
from .base import BaseGenerator, ParsedRequest
import json


class CSharpGenerator(BaseGenerator):
    name = "C# (HttpClient)"
    language = "csharp"

    # Content-Type 等需要通过 Content 设置的 header
    _CONTENT_HEADERS = {"content-type", "content-length", "content-encoding"}

    def generate(self, req: ParsedRequest) -> str:
        method = req.effective_method
        method_cls = {"GET": "Get", "POST": "Post", "PUT": "Put",
                      "DELETE": "Delete", "PATCH": "Patch", "HEAD": "Head"
                      }.get(method, method)

        lines = [
            "using System;",
            "using System.Net.Http;",
            "using System.Text;",
            "using System.Threading.Tasks;",
            "",
            "class Program",
            "{",
            "    static async Task Main()",
            "    {",
        ]

        if not req.verify_ssl:
            lines.append("        var handler = new HttpClientHandler")
            lines.append("        {")
            lines.append("            ServerCertificateCustomValidationCallback = (msg, cert, chain, errors) => true")
            lines.append("        };")
            lines.append("        using var client = new HttpClient(handler);")
        else:
            lines.append("        using var client = new HttpClient();")

        lines.append(f'        var request = new HttpRequestMessage(HttpMethod.{method_cls}, "{req.url}");')

        for k, v in req.headers.items():
            if k.lower() not in self._CONTENT_HEADERS:
                lines.append(f'        request.Headers.Add("{k}", "{self._escape(v)}");')

        if req.auth:
            lines.append(f'        var authBytes = Encoding.UTF8.GetBytes("{req.auth[0]}:{req.auth[1]}");')
            lines.append('        request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Basic", Convert.ToBase64String(authBytes));')

        if req.data:
            ct = req.headers.get("Content-Type", "application/x-www-form-urlencoded")
            lines.append(f'        request.Content = new StringContent(@"{self._escape(req.data)}", Encoding.UTF8, "{ct}");')

        if req.timeout is not None:
            lines.append(f"        client.Timeout = TimeSpan.FromSeconds({req.timeout});")

        lines.append("")
        lines.append("        var response = await client.SendAsync(request);")
        lines.append("        var body = await response.Content.ReadAsStringAsync();")
        lines.append('        Console.WriteLine($"Status: {response.StatusCode}");')
        lines.append("        Console.WriteLine(body);")
        lines.append("    }")
        lines.append("}")
        return "\n".join(lines)
