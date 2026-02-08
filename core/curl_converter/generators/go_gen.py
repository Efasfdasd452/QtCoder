# -*- coding: utf-8 -*-
from .base import BaseGenerator, ParsedRequest


class GoGenerator(BaseGenerator):
    name = "Go (net/http)"
    language = "go"

    def generate(self, req: ParsedRequest) -> str:
        method = req.effective_method
        has_body = req.data or req.json_data
        imports = ['"fmt"', '"io"', '"net/http"']
        if has_body:
            imports.append('"strings"')
        if not req.verify_ssl:
            imports.append('"crypto/tls"')

        lines = ["package main", "", "import ("]
        for imp in sorted(set(imports)):
            lines.append(f"\t{imp}")
        lines.append(")")
        lines.append("")
        lines.append("func main() {")

        if has_body:
            body = req.data or ""
            lines.append(f'\tpayload := strings.NewReader(`{body}`)')
            lines.append(f'\treq, err := http.NewRequest("{method}", "{req.url}", payload)')
        else:
            lines.append(f'\treq, err := http.NewRequest("{method}", "{req.url}", nil)')

        lines.append("\tif err != nil {")
        lines.append("\t\tpanic(err)")
        lines.append("\t}")

        for k, v in req.headers.items():
            lines.append(f'\treq.Header.Set("{k}", "{self._escape(v)}")')

        if req.auth:
            lines.append(f'\treq.SetBasicAuth("{req.auth[0]}", "{self._escape(req.auth[1])}")')

        if req.cookies:
            for k, v in req.cookies.items():
                lines.append(f'\treq.AddCookie(&http.Cookie{{Name: "{k}", Value: "{v}"}})')

        lines.append("")

        if not req.verify_ssl:
            lines.append("\tclient := &http.Client{")
            lines.append("\t\tTransport: &http.Transport{")
            lines.append("\t\t\tTLSClientConfig: &tls.Config{InsecureSkipVerify: true},")
            lines.append("\t\t},")
            lines.append("\t}")
        else:
            lines.append("\tclient := &http.Client{}")

        lines.append("\tresp, err := client.Do(req)")
        lines.append("\tif err != nil {")
        lines.append("\t\tpanic(err)")
        lines.append("\t}")
        lines.append("\tdefer resp.Body.Close()")
        lines.append("")
        lines.append("\tbody, _ := io.ReadAll(resp.Body)")
        lines.append("\tfmt.Println(string(body))")
        lines.append("}")
        return "\n".join(lines)
