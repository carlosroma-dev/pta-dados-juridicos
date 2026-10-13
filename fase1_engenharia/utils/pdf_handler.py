import pdfplumber

def extrair_texto_pdf(caminho_pdf):
    """
    Lê um arquivo PDF e retorna todo o texto contido nele como uma string.
    """
    texto_completo = ""

    # Abrir o PDF usando o pdfplumber
    with pdfplumber.open(caminho_pdf) as pdf:
        # Percorrer cada página do PDF
        for pagina in pdf.pages:
            #  Extrair o texto da página atual
            texto_da_pagina = pagina.extract_text()
            
            # Verificar se a página tem texto (evita erros em páginas em branco)
            if texto_da_pagina:
                texto_completo += texto_da_pagina + "\n" 
                
    return texto_completo.strip()