import os
import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from utils.pdf_handler import extrair_texto_pdf
from schemas.documents_schemas import DocumentoEstruturado
import logging



load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

#checar em que file eu to
CAMINHO_ABS = os.path.abspath(__file__)

#checar a pasta que essa minha file esta
DIRETORIO_SCRIPT = os.path.dirname(CAMINHO_ABS)

#raiz do projeto
RAIZ_PROJETO = os.path.dirname(DIRETORIO_SCRIPT)

PASTA_PDFS = os.path.join(RAIZ_PROJETO, "data", "pdfs")
PASTA_SAIDA = os.path.join(RAIZ_PROJETO, "data", "structured")
PASTA_LOGS = os.path.join(RAIZ_PROJETO, "logs")

# Configura o log para gravar num ficheiro dentro da pasta logs os erros
logging.basicConfig(
    filename=os.path.join(PASTA_LOGS, 'processamento_log.log'), 
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
# configurar o modelo
# temperature 0 para ele ser preciso e não inventar
llm = ChatOpenAI(model="gpt-5.4-mini-2026-03-17", temperature=0, api_key=api_key)

# vincular o schema ao modelo
modelo_com_schema = llm.with_structured_output(DocumentoEstruturado)



def executar_pipeline(caminho_entrada):
    # Extrair o texto
    texto_do_pdf = extrair_texto_pdf(caminho_entrada)
    
    if not texto_do_pdf:
        print("Erro: Texto vazio.")
        return

    # Preparar o Prompt
    prompt = f"Extraia as informações estruturadas deste documento jurídico:\n\n{texto_do_pdf}"

    # Chamar a IA e validar
    try:
        print("Enviando para a OpenAI e validando com Pydantic...")
        objeto_validado = modelo_com_schema.invoke(prompt)
        
        # Salvar o resultado
        #definir o nome do JSON igual ao do PDF
        nome_base = os.path.basename(caminho_entrada).replace(".pdf", ".json")
        caminho_saida = os.path.join(PASTA_SAIDA, nome_base)
        
        # Garante que a pasta structured existe
        os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)

        with open(caminho_saida, "w", encoding="utf-8") as f:
            # model_dump_json() transforma o objeto Pydantic em texto JSON
            f.write(objeto_validado.model_dump_json(indent=4))
            
        mensagem_sucesso = f"{caminho_entrada} processado e salvo com sucesso."
        print(mensagem_sucesso)
        logging.info(mensagem_sucesso)

    except Exception as e:
        # Se o Pydantic barrar o dado, ele cai aqui.
        mensagem_erro = f"Falha ao processar {caminho_entrada}: {str(e)}"

        print(f"Erro: {mensagem_erro}")

        logging.error(mensagem_erro)


if __name__ == "__main__":

    # Garante que a pasta structured existe antes de começar
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    os.makedirs(PASTA_LOGS, exist_ok=True)


    
    if not os.path.exists(PASTA_PDFS):
        print(f"Erro: Pasta {PASTA_PDFS} não encontrada.")
    else:
        # Lista todos os arquivos que terminam em .pdf na pasta
        arquivos = [f for f in os.listdir(PASTA_PDFS) if f.endswith(".pdf")]
        print(f"Encontrados {len(arquivos)} arquivos para processar.")

        for arquivo in arquivos:
            caminho_json = os.path.join(PASTA_SAIDA, arquivo.replace(".pdf", ".json"))
            if os.path.exists(caminho_json):
                print(f"[skip] {arquivo} — já processado.")
                continue
            caminho_completo = os.path.join(PASTA_PDFS, arquivo)
            executar_pipeline(caminho_completo)
    print("Concluído!")