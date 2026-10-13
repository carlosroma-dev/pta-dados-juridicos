"""
Funções de transformação reutilizáveis pras planilhas.

Cada função recebe uma pd.Series (uma coluna) e retorna a Series 
transformada. Em caso de valor inválido em uma célula, vira NaN/NaT/None
silenciosamente — quem chamou tem o contexto (qual planilha, qual coluna)
e é responsável por contar/logar.

Baseado nas transformações originais dos notebooks de exploração.
"""

import re
import unicodedata

import numpy as np
import pandas as pd


# Mapas de tradução

# Meses em português pra número. Usado pra normalizar datas por extenso
# ("18 de julho de 2025" → "18 07 2025") antes de parsear.
MAPA_MES_EXTENSO = {
    "janeiro": "01",
    "fevereiro": "02",
    "março": "03",
    "marco": "03",
    "abril": "04",
    "maio": "05",
    "junho": "06",
    "julho": "07",
    "agosto": "08",
    "setembro": "09",
    "outubro": "10",
    "novembro": "11",
    "dezembro": "12",
}

# Status do processo: pt-br e en misturados na origem → enum técnico canônico.
# Resultado final: minúsculo + underscore (conforme nossa decisão).
# Chaves em lowercase pra match case-insensitive.
MAPA_STATUS = {
    "ativo": "ativo",
    "active": "ativo",
    "encerrado": "encerrado",
    "closed": "encerrado",
    "em recurso": "em_recurso",
    "em_recurso": "em_recurso",
    "appeal": "em_recurso",
    "suspenso": "suspenso",
    "suspended": "suspenso",
    "acordo": "acordo",
    "settlement": "acordo",
}

# Tipos de processo. Lowercase como chave, lowercase canônico como valor.
MAPA_TIPO_PROCESSO = {
    "civil": "civel",
    "cível": "civel",
    "civel": "civel",
    "trabalhista": "trabalhista",
    "criminal": "criminal",
    "penal": "criminal",
}

# Advogados do escritório — chaves em lowercase + sem ponto pra match tolerante.
# Inclui as 4 variações reais que aparecem nas planilhas (incluindo Dr. Barros
# que tinha sido esquecido nos notebooks).
MAPA_ADVOGADOS = {
    "dr barros": "Dr. Barros",
    "dra cavalcante": "Dra. Cavalcante",
    "dr melo": "Dr. Melo",
    "dra fontes": "Dra. Fontes",
}

MAPA_ADVOGADOS_ID = {
    "Dr. Barros": 1,
    "Dra. Cavalcante": 2,
    "Dr. Melo": 3,
    "Dra. Fontes": 4,
}

# Formas de pagamento → enum técnico canônico (minúsculo).
MAPA_FORMA_PAGAMENTO = {
    "pix": "pix",
    "boleto": "boleto",
    "ted": "ted",
    "transferência": "transferencia",
    "transferencia": "transferencia",
    "dinheiro": "dinheiro",
    "cartao": "cartao",
    "cartão": "cartao",
}

# Status de pagamento → enum técnico canônico (minúsculo + underscore).
MAPA_STATUS_PAGAMENTO = {
    "quitado": "quitado",
    "em dia": "em_dia",
    "em_dia": "em_dia",
    "atrasado": "atrasado",
}

# Valores que representam True e False (case-insensitive, sem acento).
VALORES_TRUE = {"sim", "s", "1", "true", "verdadeiro"}
VALORES_FALSE = {"nao", "n", "0", "false", "falso"}


# Helpers internos

def _remover_acentos(texto: str) -> str:
    #Tira acentos: 'audiência' → 'audiencia'.
    if not isinstance(texto, str):
        return texto
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# Padronização de datas

def padronizar_data_serie(serie: pd.Series) -> pd.Series:

    # Garante string em lowercase pra processar.
    s = serie.astype(str).str.lower().str.strip()

    # Remove a parte de hora dos timestamps ISO ("2024-02-20 00:00:00" → "2024-02-20")
    s = s.str.replace(r"\s+\d{1,2}:\d{2}:\d{2}.*$", "", regex=True)

    # Substitui "janeiro" → "01", "fevereiro" → "02", etc.
    s = s.replace(MAPA_MES_EXTENSO, regex=True)

    # Remove "de" (do formato extenso "18 de 07 de 2025")
    s = s.str.replace(r"\s+de\s+", " ", regex=True)

    # Substitui qualquer não-dígito por hífen, e colapsa hífens duplicados.
    s = s.str.replace(r"[^\d]+", "-", regex=True)
    s = s.str.strip("-").str.replace(r"-+", "-", regex=True)

    # temos dois formatos possíveis:
    #    - "YYYY-MM-DD"  (do ISO original)
    #    - "DD-MM-YYYY"  (do extenso)
    # Detecta qual é cada um pelo tamanho do primeiro grupo.
    # Se começa com 4 dígitos seguidos de hífen → ISO (year first).
    eh_iso = s.str.match(r"^\d{4}-")

    # Parseia cada formato separadamente.
    resultado = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")

    # Formato ISO (YYYY-MM-DD)
    iso_parsed = pd.to_datetime(
        s.where(eh_iso), format="%Y-%m-%d", errors="coerce"
    )
    resultado = resultado.where(~eh_iso, iso_parsed)

    # Formato extenso (DD-MM-YYYY)
    extenso_parsed = pd.to_datetime(
        s.where(~eh_iso), format="%d-%m-%Y", errors="coerce"
    )
    resultado = resultado.where(eh_iso, extenso_parsed)

    return resultado



def padronizar_valor_monetario_serie(serie: pd.Series) -> pd.Series:

    s = serie.astype(str).str.strip()

    # Detecta corrupção: padrão de data ISO em coluna de valor.
    mascara_corrompido = s.str.contains(r"\d{4}-\d{2}-\d{2}", regex=True, na=False)
    s = s.where(~mascara_corrompido, np.nan)

    # Detecta presença de "R$" ANTES de removê-lo. Importante porque
    #    "R$" é sinal forte de formato BR (mesmo sem vírgula).
    tem_rs = s.astype(str).str.contains(r"R\$", regex=True, flags=re.IGNORECASE, na=False)

    # Remove prefixo "R$" e espaços.
    s = s.astype(str).str.replace(r"R\$\s*", "", regex=True, flags=re.IGNORECASE).str.strip()

    # Tem "R$" é BR. Ponto = milhar, vírgula = decimal.
    s_a = s.where(tem_rs).str.replace(".", "", regex=False).str.replace(",", ".", regex=False)

    # Não tem "R$" mas tem vírgula: BR sem prefixo. Vírgula = decimal.
    tem_virgula = s.astype(str).str.contains(",", regex=False, na=False)
    caso_b = (~tem_rs) & tem_virgula
    s_b = s.where(caso_b).str.replace(",", ".", regex=False)

    # Não tem "R$" e não tem vírgula: formato US/float. Ponto = decimal.

    #  Aplica as transformações nos seus respectivos subconjuntos.
    s = s.where(~tem_rs, s_a)
    s = s.where(~caso_b, s_b)

    # Tenta converter pra float.
    return pd.to_numeric(s, errors="coerce")


# Padronização de strings

def normalizar_enum_serie(serie: pd.Series) -> pd.Series:

    return (
        serie.astype(str)
        .str.strip()
        .str.lower()
        .apply(_remover_acentos)
        .str.replace(r"\s+", "_", regex=True)
        .replace({"nan": np.nan, "none": np.nan, "": np.nan})  # preserva nulos
    )


# Padronização de strings — nomes próprios

def normalizar_nome_proprio_serie(serie: pd.Series) -> pd.Series:
    return (
        serie.astype(str)
        .str.strip()
        .str.title()
        .replace({"Nan": np.nan, "None": np.nan, "": np.nan})  # preserva nulos
    )


# Padronização de booleanos
def normalizar_boolean_serie(serie: pd.Series) -> pd.Series:

    # Normaliza pra string limpa pra match.
    s = serie.astype(str).str.strip().str.lower()
    s = s.apply(_remover_acentos)

    # Mapeia conjuntos pra True/False.
    resultado = pd.Series([pd.NA] * len(s), index=s.index, dtype="boolean")
    resultado[s.isin(VALORES_TRUE)] = True
    resultado[s.isin(VALORES_FALSE)] = False

    return resultado



# Padronização via mapa (status, advogado, forma de pagamento, etc.)

def aplicar_mapa(serie: pd.Series, mapa: dict[str, str]) -> pd.Series:

    chave = (
        serie.astype(str)
        .str.strip()
        .str.lower()
        .replace({"nan": np.nan, "none": np.nan, "": np.nan})
    )
    return chave.map(mapa)


def normalizar_advogado_serie(serie: pd.Series) -> pd.Series:

    chave = (
        serie.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(".", "", regex=False)  # remove pontos pra match tolerante
        .str.replace(r"\s+", " ", regex=True)  # colapsa espaços múltiplos
        .replace({"nan": np.nan, "none": np.nan, "": np.nan})
    )
    return chave.map(MAPA_ADVOGADOS)


# ──────────────────────────────────────────────────────────────────────────────
# Padronização de percentual decimal
# ──────────────────────────────────────────────────────────────────────────────

def normalizar_percentual_decimal_serie(serie: pd.Series) -> pd.Series:

    s = pd.to_numeric(serie, errors="coerce")

    # Caso "porcentagem" (1 < x <= 100): divide por 100
    eh_porcentagem = (s > 1) & (s <= 100)

    # Caso "fora do range" (< 0 ou > 100): vira NaN
    fora_range = (s < 0) | (s > 100)

    # Aplica transformações
    resultado = s.where(~eh_porcentagem, s / 100)
    resultado = resultado.where(~fora_range, np.nan)

    return resultado

# Bloco de testes

if __name__ == "__main__":
    print('-----------------')
    print("Testes manuais de transformacoes.py")
    print('-----------------')

    print("\n--- padronizar_data_serie ---")
    s = pd.Series([
        "2024-02-20 00:00:00",
        "18 de julho de 2025",
        "3 de julho de 2021",
        None,
        "blablabla",
    ])
    print(padronizar_data_serie(s).tolist())

    print("\n--- padronizar_valor_monetario_serie ---")
    s = pd.Series([
        "34627.03",
        "R$ 178.093",
        "R$ 8.141,30",
        "6490,90",
        "8812-04-01 00:00:00",  # corrompido
        None,
        "abc",
    ])
    print(padronizar_valor_monetario_serie(s).tolist())

    print("\n--- normalizar_enum_serie ---")
    s = pd.Series(["ATIVO", "ativo", "Em Recurso", "  PIX  ", "Audiência", None])
    print(normalizar_enum_serie(s).tolist())

    print("\n--- normalizar_nome_proprio_serie ---")
    s = pd.Series(["RECIFE", "recife", "  olinda  ", "petrolândia", None])
    print(normalizar_nome_proprio_serie(s).tolist())

    print("\n--- normalizar_boolean_serie ---")
    s = pd.Series(["sim", "Não", "S", "N", "1", "0", None, "talvez"])
    print(normalizar_boolean_serie(s).tolist())

    print("\n--- aplicar_mapa (status) ---")
    s = pd.Series(["ATIVO", "active", "settlement", "em recurso", "xyz", None])
    print(aplicar_mapa(s, MAPA_STATUS).tolist())

    print("\n--- normalizar_advogado_serie ---")
    s = pd.Series([
        "DRA. CAVALCANTE", "dra fontes", "Dr Barros",
        "Dra. Cavalcante", "Dr. Melo", "dr ninguem", None,
    ])
    print(normalizar_advogado_serie(s).tolist())