from typing import TypedDict

TAMANHO_JANELA = 5  # pares de mensagens (user + assistant) mantidos na janela


class Mensagem(TypedDict):
    papel: str    # "user" | "assistant"
    conteudo: str


def formatar_historico(historico: list[Mensagem]) -> str:
    """Formata o histórico como bloco de texto para injeção no prompt do LLM."""
    if not historico:
        return ""
    linhas = ["## Histórico da conversa"]
    for msg in historico:
        papel = msg.get("papel", "") if isinstance(msg, dict) else getattr(msg, "papel", "")
        conteudo = msg.get("conteudo", "") if isinstance(msg, dict) else getattr(msg, "conteudo", "")
        prefixo = "Usuário" if papel == "user" else "Assistente"
        linhas.append(f"{prefixo}: {conteudo}")
    return "\n".join(linhas) + "\n\n"


def aplicar_janela(
    historico: list[Mensagem],
    pergunta: str,
    resposta: str,
) -> list[Mensagem]:
    """Adiciona a nova troca ao histórico e mantém apenas os últimos TAMANHO_JANELA."""
    atualizado = historico + [
        {"papel": "user", "conteudo": pergunta},
        {"papel": "assistant", "conteudo": resposta},
    ]
    return atualizado[-TAMANHO_JANELA * 2:]
