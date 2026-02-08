# -*- coding: utf-8 -*-
"""代码生成器基类"""

from abc import ABC, abstractmethod
from ..parser import ParsedRequest


class BaseGenerator(ABC):
    """所有语言生成器的基类"""
    name: str = ""
    language: str = ""

    @abstractmethod
    def generate(self, req: ParsedRequest) -> str:
        """将 ParsedRequest 转换为目标语言代码字符串"""
        ...

    @staticmethod
    def _escape(s: str, quote='"') -> str:
        """转义字符串中的特殊字符"""
        s = s.replace('\\', '\\\\')
        s = s.replace(quote, f'\\{quote}')
        return s
