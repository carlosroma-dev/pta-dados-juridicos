from enum import Enum


class StatusProcesso(str, Enum):
    ativo = "ativo"
    suspenso = "suspenso"
    encerrado = "encerrado"
    em_recurso = "em_recurso"
    acordo = "acordo"


class StatusPagamento(str, Enum):
    quitado = "quitado"
    em_dia = "em_dia"
    atrasado = "atrasado"
