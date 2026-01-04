from __future__ import annotations
from dataclasses import dataclass

@dataclass
class FindingV3:
    severidade: str            # ERRO / ALERTA
    campo: str                 # NCM / CFOP / CST / CSOSN / etc
    problema: str              # descrição curta
    causa: str                 # causa provável
    valor_atual: str           # valor observado
    correcao_sugerida: str     # valor sugerido (ou orientação)
    base_legal: str = ""       # referência à tabela/lei (quando aplicável)
    correcao_automatica: bool = False  # se é seguro aplicar automaticamente
    aplicado: bool = False     # se foi aplicado no DF/XML
