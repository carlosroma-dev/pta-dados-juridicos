"""Armazenamento dos PDFs enviados pela interface.

Salva o arquivo em `data/pdfs/` (mesma pasta do pipeline em lote — um único
repositório local de PDFs). Resolve colisão de nome com sufixo de timestamp:
se `peticao.pdf` já existe, salva `peticao_20260601-143022.pdf`. O nome original
é devolvido à parte para exibição amigável; nada é sobrescrito.

Sanitiza o nome recebido para o basename (evita path traversal do tipo
`../../etc/algo` vindo de um upload malicioso).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
PASTA_PDFS = RAIZ_PROJETO / "data" / "pdfs"


def _nome_seguro(nome_original: str | None) -> str:
    """Reduz o nome ao basename e garante extensão .pdf."""
    nome = Path(nome_original or "").name.strip()  # tira qualquer componente de diretório
    if not nome:
        nome = "documento.pdf"
    if not nome.lower().endswith(".pdf"):
        nome = f"{nome}.pdf"
    return nome


def _nome_sem_colisao(pasta: Path, nome: str) -> str:
    """Devolve um nome que não sobrescreve nenhum arquivo existente na pasta."""
    if not (pasta / nome).exists():
        return nome
    base, ext = Path(nome).stem, Path(nome).suffix
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidato = f"{base}_{carimbo}{ext}"
    n = 1
    while (pasta / candidato).exists():  # mesmo segundo + mesmo nome: desambigua com contador
        candidato = f"{base}_{carimbo}_{n}{ext}"
        n += 1
    return candidato


def salvar_pdf(
    conteudo: bytes, nome_original: str | None, pasta: Path | None = None
) -> tuple[Path, str]:
    """Salva os bytes do PDF em disco sem sobrescrever nada.

    Devolve (caminho_salvo, nome_arquivo_salvo). O `nome_arquivo_salvo` pode
    diferir do original se houve colisão.
    """
    pasta = pasta or PASTA_PDFS
    pasta.mkdir(parents=True, exist_ok=True)

    nome = _nome_sem_colisao(pasta, _nome_seguro(nome_original))
    caminho = pasta / nome
    caminho.write_bytes(conteudo)
    return caminho, nome