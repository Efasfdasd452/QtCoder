# -*- coding: utf-8 -*-
"""代码生成器注册表"""

from ..parser import ParsedRequest
from .python_gen import PythonRequestsGenerator
from .javascript_gen import JavaScriptFetchGenerator
from .nodejs_gen import NodeAxiosGenerator
from .go_gen import GoGenerator
from .php_gen import PHPCurlGenerator
from .java_gen import JavaGenerator
from .csharp_gen import CSharpGenerator
from .ruby_gen import RubyGenerator
from .rust_gen import RustGenerator
from .wget_gen import WgetGenerator
from .httpie_gen import HTTPieGenerator
from .powershell_gen import PowerShellGenerator

# 有序注册表: {显示名: 生成器实例}
GENERATORS = {
    "Python (requests)":         PythonRequestsGenerator(),
    "JavaScript (fetch)":        JavaScriptFetchGenerator(),
    "Node.js (axios)":           NodeAxiosGenerator(),
    "Go (net/http)":             GoGenerator(),
    "PHP (cURL)":                PHPCurlGenerator(),
    "Java (HttpURLConnection)":  JavaGenerator(),
    "C# (HttpClient)":           CSharpGenerator(),
    "Ruby (net/http)":           RubyGenerator(),
    "Rust (reqwest)":            RustGenerator(),
    "Wget":                      WgetGenerator(),
    "HTTPie":                    HTTPieGenerator(),
    "PowerShell":                PowerShellGenerator(),
}


def generate_code(language: str, req: ParsedRequest) -> str:
    """根据语言名生成代码"""
    gen = GENERATORS.get(language)
    if gen is None:
        raise ValueError(f"不支持的目标语言: {language}")
    return gen.generate(req)
