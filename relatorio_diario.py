"""
Automação completa de cobrança - roda para TODOS os condomínios do dia de hoje.

Baseado no dia da semana, escolhe a lista certa de condomínios, entra em cada
um, lê as unidades com cota atrasada, aplica as regras de negócio (30 dias +
honorário dobrado), e gera um relatório .txt separado por condomínio.
"""

import os
import time
from datetime import datetime
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config_condominios import CONDOMINIOS_POR_DIA

load_dotenv()

USUARIO = os.getenv("LELLO_USUARIO")
SENHA = os.getenv("LELLO_SENHA")

URL_LOGIN = "https://portal.lellocondominios.com.br/menuPortal2/"
DIAS_MINIMOS_PARA_COBRANCA = 30


def texto_para_valor(texto):
    """Converte texto de dinheiro brasileiro ('1.234,56') para número (1234.56)."""
    texto_limpo = texto.strip().replace(".", "").replace(",", ".")
    return float(texto_limpo)


def novo_driver_logado():
    """Abre um novo navegador e já faz login. Usado tanto no início quanto
    para se recuperar caso o navegador caia no meio do processo."""
    opcoes = webdriver.ChromeOptions()
    opcoes.add_experimental_option("detach", True)
    driver = webdriver.Chrome(options=opcoes)
    espera = WebDriverWait(driver, 10)
    fazer_login(driver, espera)
    return driver, espera


def sessao_esta_viva(driver):
    """Testa se o navegador ainda está respondendo (não caiu/fechou)."""
    try:
        _ = driver.current_url
        return True
    except Exception:
        return False


def esta_deslogado(driver):
    """Detecta se a sessão do SITE caiu (voltou pra tela de login), mesmo
    com o navegador ainda funcionando normalmente."""
    try:
        driver.switch_to.default_content()
        return len(driver.find_elements(By.ID, "username")) > 0
    except Exception:
        return False


def fazer_login(driver, espera):
    driver.get(URL_LOGIN)
    campo_usuario = espera.until(EC.presence_of_element_located((By.ID, "username")))
    campo_senha = driver.find_element(By.ID, "id_password")
    campo_usuario.send_keys(USUARIO)
    campo_senha.send_keys(SENHA)
    campo_senha.send_keys(Keys.RETURN)
    print("Login enviado.")
    # Espera a página principal carregar antes de seguir.
    espera.until(EC.presence_of_element_located((By.CSS_SELECTOR, "button.btn-black.dropdown-toggle")))


def encontrar_campo_busca(driver):
    """Procura o campo de busca de condomínio no documento principal ou em qualquer iframe."""
    seletor = 'input[placeholder="Digite o código ou nome do condomínio"]'
    driver.switch_to.default_content()
    elementos = driver.find_elements(By.CSS_SELECTOR, seletor)
    if elementos:
        return elementos[0]
    for iframe in driver.find_elements(By.TAG_NAME, "iframe"):
        driver.switch_to.default_content()
        try:
            driver.switch_to.frame(iframe)
        except Exception:
            continue
        elementos = driver.find_elements(By.CSS_SELECTOR, seletor)
        if elementos:
            return elementos[0]
    driver.switch_to.default_content()
    return None


def selecionar_condominio(driver, espera, codigo_condominio):
    """Abre o dropdown, busca pelo CÓDIGO (único, evita confundir nomes repetidos) e seleciona."""
    driver.switch_to.default_content()

    # Só voltamos pra página principal se detectarmos que NÃO estamos nela
    # (ex: presos numa página de detalhe de outra unidade). Se o botão do
    # condomínio já está visível, não precisa recarregar - isso evita recarregar
    # logo após o login, quando a sessão pode ainda não ter "assentado" direito.
    if not driver.find_elements(By.CSS_SELECTOR, "button.btn-black.dropdown-toggle"):
        driver.get(URL_LOGIN)
        driver.switch_to.default_content()

    botao_condominio = espera.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-black.dropdown-toggle"))
    )
    driver.execute_script("arguments[0].click();", botao_condominio)
    time.sleep(1)

    campo_busca = None
    for _ in range(10):
        campo_busca = encontrar_campo_busca(driver)
        if campo_busca is not None:
            break
        time.sleep(1)
    if campo_busca is None:
        raise RuntimeError(f"Não encontrei o campo de busca para o condomínio {codigo_condominio}.")

    driver.execute_script(
        """
        arguments[0].value = arguments[1];
        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
        """,
        campo_busca,
        codigo_condominio,
    )
    time.sleep(1)

    botao_buscar = driver.find_element(By.XPATH, "//button[contains(text(), 'Buscar')]")
    driver.execute_script(
        """
        var botao = arguments[0];
        var formulario = botao.closest('form');
        if (formulario) {
            formulario.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
        } else {
            botao.click();
        }
        """,
        botao_buscar,
    )
    time.sleep(1.5)

    link_condominio = espera.until(
        EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, codigo_condominio))
    )
    link_condominio.click()

    # Refresh para evitar estado "bagunçado" do Angular depois da troca.
    driver.refresh()
    espera.until(EC.presence_of_element_located((By.LINK_TEXT, "Recebimentos")))
    time.sleep(1)


def ir_para_cotas_atrasadas(driver, espera):
    link_recebimentos = espera.until(EC.element_to_be_clickable((By.LINK_TEXT, "Recebimentos")))
    link_recebimentos.click()

    link_cotas_atrasadas = espera.until(EC.element_to_be_clickable((By.LINK_TEXT, "Cotas Atrasadas")))
    link_cotas_atrasadas.click()
    time.sleep(3)

    # O conteúdo real fica dentro do iframe "innerframe".
    driver.switch_to.default_content()
    espera.until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "innerframe")))

    espera_longa = WebDriverWait(driver, 15)
    try:
        espera_longa.until(
            EC.presence_of_element_located(
                (By.XPATH, "//th[contains(text(), 'Unidade') or contains(text(), 'Lote')]")
            )
        )
    except Exception:
        # Não achou a tabela - provavelmente esse condomínio não tem NENHUMA
        # unidade com cota atrasada no momento (não é erro, é um resultado válido).
        print("  (Nenhuma tabela de unidades apareceu - provavelmente 0 unidades com cota atrasada.)")


def coletar_unidades(driver):
    """Rola a página aos poucos até a lista de unidades parar de crescer, e extrai
    (codigo, nome, quantidade_parcelas, url)."""
    quantidade_anterior = -1
    for _ in range(40):
        linhas_atuais = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        quantidade_atual = len(linhas_atuais)
        if quantidade_atual == quantidade_anterior:
            break
        quantidade_anterior = quantidade_atual
        driver.execute_script("window.scrollBy(0, 800);")
        time.sleep(0.7)

    linhas_da_lista = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
    unidades = []
    for linha in linhas_da_lista:
        celulas = linha.find_elements(By.TAG_NAME, "td")
        if len(celulas) < 4:
            continue  # linha muito curta pra ser uma linha de dados válida

        # O link (código/nome da unidade) pode estar na 1ª coluna (formato "Lote",
        # ex: Jardim das Oliveiras) ou na 2ª coluna (formato "Unidade", com nome
        # separado). Em vez de assumir a posição, procuramos o link na própria
        # linha, onde quer que ele esteja.
        try:
            link_elemento = linha.find_element(By.TAG_NAME, "a")
        except Exception:
            continue  # linha sem link nenhum, ignora

        codigo_unidade = celulas[0].text.strip()
        nome = link_elemento.text.strip()
        url_detalhe = link_elemento.get_attribute("href")

        # As 3 últimas colunas são SEMPRE Qtde, Valor Principal Total e Total
        # c/Multa, independente de ter ou não uma coluna de Nome separada antes
        # delas - por isso contamos a partir do FIM da linha, não do início.
        try:
            quantidade_parcelas = int(celulas[-3].text.strip())
        except (ValueError, IndexError):
            quantidade_parcelas = 0

        try:
            valor_aproximado = texto_para_valor(celulas[-1].text.strip())
        except (ValueError, IndexError):
            valor_aproximado = 0.0

        unidades.append((codigo_unidade, nome, quantidade_parcelas, valor_aproximado, url_detalhe))
    return unidades


def calcular_valor_devido(driver, espera, url_detalhe):
    """Entra na página de detalhe da unidade e calcula o valor real (com honorário dobrado)."""
    driver.get(url_detalhe)
    espera.until(EC.presence_of_element_located((By.XPATH, "//th[contains(text(), 'Vencimento')]")))

    linhas_detalhe = driver.find_elements(By.CSS_SELECTOR, "table.table tbody tr")
    hoje = datetime.now().date()
    total_devido_real = 0.0

    for linha in linhas_detalhe:
        celulas = linha.find_elements(By.TAG_NAME, "td")
        if len(celulas) < 6:
            continue  # linha muito curta pra ser uma parcela válida

        # Em vez de assumir uma posição fixa pra "Vencimento" (que varia conforme
        # a tabela tem ou não uma coluna de Nome), procuramos qual célula
        # realmente contém uma data válida - isso funciona em qualquer formato.
        indice_vencimento = None
        vencimento_data = None
        for i in range(0, min(3, len(celulas))):
            try:
                vencimento_data = datetime.strptime(celulas[i].text.strip(), "%d/%m/%Y").date()
                indice_vencimento = i
                break
            except ValueError:
                continue

        if indice_vencimento is None:
            continue  # nenhuma data válida nessa linha (ex: "Total de débitos"), ignora

        # A partir do Vencimento, a ordem é sempre: Valor, Multa, Correção, Juros,
        # e depois Honorários+Total (se a coluna existir) ou só Total.
        indice_juros = indice_vencimento + 4
        colunas_apos_juros = len(celulas) - (indice_juros + 1)

        if colunas_apos_juros == 2:
            honorarios_texto = celulas[indice_juros + 1].text.strip()
            total_texto = celulas[indice_juros + 2].text.strip()
        elif colunas_apos_juros == 1:
            honorarios_texto = "0,00"
            total_texto = celulas[indice_juros + 1].text.strip()
        else:
            continue  # formato não reconhecido, ignora com segurança

        dias_em_atraso = (hoje - vencimento_data).days
        if dias_em_atraso < DIAS_MINIMOS_PARA_COBRANCA:
            continue

        honorario_sistema = texto_para_valor(honorarios_texto)
        total_sistema = texto_para_valor(total_texto)
        total_devido_real += total_sistema + honorario_sistema  # dobra o honorário

    return total_devido_real


def ir_para_acordos(driver, espera):
    """A partir da tela de Cotas Atrasadas, clica no link que leva pros acordos
    em andamento. Retorna False se o condomínio não tiver esse link (sem acordos)."""
    try:
        link_acordos = espera.until(
            EC.element_to_be_clickable(
                (By.LINK_TEXT, "Clique aqui para visualizar os acordos em andamento")
            )
        )
    except Exception:
        return False

    link_acordos.click()
    time.sleep(1)

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//th[contains(text(), 'Status')]"))
        )
    except Exception:
        pass  # segue mesmo assim - coletar_lista_acordos vai simplesmente achar 0 linhas
    return True


def coletar_lista_acordos(driver):
    """Lê a lista resumida de acordos (rola a página até parar de crescer,
    igual fizemos com a lista de unidades)."""
    quantidade_anterior = -1
    for _ in range(40):
        linhas_atuais = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        quantidade_atual = len(linhas_atuais)
        if quantidade_atual == quantidade_anterior:
            break
        quantidade_anterior = quantidade_atual
        driver.execute_script("window.scrollBy(0, 800);")
        time.sleep(0.5)

    linhas = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
    acordos = []
    for linha in linhas:
        celulas = linha.find_elements(By.TAG_NAME, "td")
        if len(celulas) < 9:
            continue
        try:
            link_tipo = linha.find_element(By.TAG_NAME, "a")
        except Exception:
            continue

        acordos.append({
            "unidade_nome": celulas[0].text.strip(),
            "data_efetivacao": celulas[1].text.strip(),
            "tipo": link_tipo.text.strip(),
            "status": celulas[3].text.strip(),
            "valor_acordo": celulas[4].text.strip(),
            "parcelas_pagas": celulas[5].text.strip(),
            "valor_pago": celulas[6].text.strip(),
            "parcelas_abertas": celulas[7].text.strip(),
            "valor_aberto": celulas[8].text.strip(),
            "proximo_vencto": celulas[9].text.strip() if len(celulas) > 9 else "",
            "url_detalhe": link_tipo.get_attribute("href"),
            "parcelas_detalhadas": [],
            "cotas_originais": [],
        })
    return acordos


def ler_parcelas_acordo(driver, espera):
    """Na página de detalhe de um acordo, lê a tabela de parcelas e os totais
    (Valor Total / Valor Pago / Valor Em Aberto)."""
    try:
        espera.until(EC.presence_of_element_located((By.XPATH, "//th[contains(text(), 'Vencimento')]")))
    except Exception:
        return []

    linhas = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
    parcelas = []
    for linha in linhas:
        celulas = linha.find_elements(By.TAG_NAME, "td")
        textos = [c.text.strip() for c in celulas]
        if len(textos) < 5:
            continue
        try:
            datetime.strptime(textos[0], "%d/%m/%Y")
        except ValueError:
            continue  # linha sem data válida na 1ª coluna, ignora
        parcelas.append({
            "vencimento": textos[0],
            "tipo": textos[1],
            "status": textos[3],
            "valor": textos[4],
        })
    return parcelas


def ler_cotas_do_acordo(driver, espera):
    """Clica em 'visualizar as cotas que compõem o acordo' e lê essa tabela."""
    try:
        link_cotas = espera.until(
            EC.element_to_be_clickable(
                (By.LINK_TEXT, "Clique aqui para visualizar as cotas que compõem o acordo")
            )
        )
    except Exception:
        return []

    link_cotas.click()
    time.sleep(1)

    try:
        espera.until(EC.presence_of_element_located((By.XPATH, "//th[contains(text(), 'Recibo')]")))
    except Exception:
        return []

    linhas = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
    cotas = []
    for linha in linhas:
        celulas = linha.find_elements(By.TAG_NAME, "td")
        if len(celulas) < 5:
            continue
        cotas.append({
            "recibo": celulas[0].text.strip(),
            "vencimento_original": celulas[1].text.strip(),
            "valor_original": celulas[2].text.strip(),
            "historico": celulas[3].text.strip(),
            "status": celulas[4].text.strip(),
        })
    return cotas


def gerar_relatorio_acordos(nome_condominio, codigo_condominio, acordos):
    hoje = datetime.now().date()
    nome_arquivo = f"acordos_{nome_condominio.replace(' ', '_')}.txt"
    with open(nome_arquivo, "w", encoding="utf-8") as arquivo:
        arquivo.write(f"RELATORIO DE ACORDOS - {codigo_condominio} - {nome_condominio}\n")
        arquivo.write(f"Gerado em {hoje.strftime('%d/%m/%Y')}\n")
        arquivo.write("=" * 50 + "\n\n")

        if not acordos:
            arquivo.write("Nenhum acordo em andamento no momento.\n")

        for acordo in acordos:
            arquivo.write(f"Unidade: {acordo['unidade_nome']}\n")
            arquivo.write(f"  Tipo: {acordo['tipo']} | Status: {acordo['status']}\n")
            arquivo.write(f"  Data de efetivacao: {acordo['data_efetivacao']}\n")
            arquivo.write(
                f"  Valor do acordo: R$ {acordo['valor_acordo']} | "
                f"Pago: R$ {acordo['valor_pago']} | Em aberto: R$ {acordo['valor_aberto']}\n"
            )
            arquivo.write(
                f"  Parcelas pagas: {acordo['parcelas_pagas']} | "
                f"Parcelas em aberto: {acordo['parcelas_abertas']} | "
                f"Proximo vencimento: {acordo['proximo_vencto']}\n"
            )
            if acordo["parcelas_detalhadas"]:
                arquivo.write("  Parcelas detalhadas:\n")
                for p in acordo["parcelas_detalhadas"]:
                    arquivo.write(
                        f"    {p['vencimento']} - {p['tipo']} - Status: {p['status']} - R$ {p['valor']}\n"
                    )
            if acordo["cotas_originais"]:
                arquivo.write("  Cotas que compoem o acordo:\n")
                for c in acordo["cotas_originais"]:
                    arquivo.write(
                        f"    Recibo {c['recibo']} - venc. original {c['vencimento_original']} - "
                        f"R$ {c['valor_original']} - {c['historico']} ({c['status']})\n"
                    )
            arquivo.write("\n")

    print(f"  Relatorio de acordos salvo em '{nome_arquivo}'.")


def processar_condominio(driver, espera, nome_condominio, codigo_condominio):
    print(f"\n=== Processando {codigo_condominio} - {nome_condominio} ===")
    selecionar_condominio(driver, espera, codigo_condominio)
    ir_para_cotas_atrasadas(driver, espera)

    unidades = coletar_unidades(driver)
    print(f"  {len(unidades)} unidade(s) com cota atrasada.")

    LIMITE_PARCELAS_JUDICIAL = 10
    LIMITE_VALOR_CONFERENCIA_MANUAL = 1000.0

    resultados = []  # cada item: (codigo, nome, valor, nota_ou_None)
    unidades_puladas_judicial = 0
    for codigo_unidade, nome_morador, quantidade_parcelas, valor_aproximado, url_detalhe in unidades:
        if quantidade_parcelas > LIMITE_PARCELAS_JUDICIAL:
            # Mais de 10 parcelas pendentes geralmente indica processo judicial em
            # andamento - não é cobrável pelo processo normal, então nem entramos
            # na página de detalhe (economiza bastante tempo).
            unidades_puladas_judicial += 1
            continue

        # No Vida Plena (condomínio muito grande), unidades com valor aproximado
        # acima de R$1.000 não têm o cálculo fino feito automaticamente - só
        # aparecem no relatório com um aviso pra conferência manual. Isso
        # acelera bastante o processamento sem deixar nenhuma unidade de fora.
        if nome_condominio == "Vida Plena" and valor_aproximado > LIMITE_VALOR_CONFERENCIA_MANUAL:
            resultados.append((codigo_unidade, nome_morador, valor_aproximado, "VALOR ALTO - conferir manualmente"))
            print(f"    {codigo_unidade} - {nome_morador}: R$ {valor_aproximado:.2f} (valor alto, marcado pra conferência manual)")
            continue

        valor = calcular_valor_devido(driver, espera, url_detalhe)
        if valor > 0:
            resultados.append((codigo_unidade, nome_morador, valor, None))
            print(f"    {codigo_unidade} - {nome_morador}: R$ {valor:.2f}")

    if unidades_puladas_judicial > 0:
        print(f"  {unidades_puladas_judicial} unidade(s) pulada(s) por ter mais de {LIMITE_PARCELAS_JUDICIAL} parcelas pendentes (provável processo judicial).")

    hoje = datetime.now().date()
    nome_arquivo = f"relatorio_{nome_condominio.replace(' ', '_')}.txt"
    with open(nome_arquivo, "w", encoding="utf-8") as arquivo:
        arquivo.write(f"RELATORIO DE COBRANCA - {codigo_condominio} - {nome_condominio}\n")
        arquivo.write(f"Gerado em {hoje.strftime('%d/%m/%Y')}\n")
        arquivo.write("=" * 50 + "\n\n")
        if not resultados:
            arquivo.write("Nenhuma unidade com valor a cobrar no momento.\n")
        for codigo_unidade, nome_morador, valor, nota in resultados:
            if nota:
                arquivo.write(f"Unidade {codigo_unidade} - {nome_morador}: R$ {valor:.2f} [{nota}]\n")
            else:
                arquivo.write(f"Unidade {codigo_unidade} - {nome_morador}: R$ {valor:.2f}\n")

    print(f"  Relatório salvo em '{nome_arquivo}'.")

    if ir_para_acordos(driver, espera):
        lista_acordos = coletar_lista_acordos(driver)
        print(f"  {len(lista_acordos)} acordo(s) encontrado(s).")
        for acordo in lista_acordos:
            driver.get(acordo["url_detalhe"])
            acordo["parcelas_detalhadas"] = ler_parcelas_acordo(driver, espera)
            acordo["cotas_originais"] = ler_cotas_do_acordo(driver, espera)
        gerar_relatorio_acordos(nome_condominio, codigo_condominio, lista_acordos)
    else:
        print("  Nenhum link de acordos em andamento encontrado.")


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

# Para TESTAR em qualquer dia da semana, escreva o nome do dia aqui
# (ex: "segunda"). Para uso normal do dia a dia, deixe como None -
# assim ele usa o dia real automaticamente.
DIA_PARA_TESTE = None

dias_da_semana = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
nome_do_dia = DIA_PARA_TESTE if DIA_PARA_TESTE else dias_da_semana[datetime.now().weekday()]
condominios_de_hoje = CONDOMINIOS_POR_DIA[nome_do_dia]

print(f"Hoje é {nome_do_dia}. Condomínios a processar: {len(condominios_de_hoje)}")

if len(condominios_de_hoje) == 0:
    print("Nenhum condomínio pra cobrar hoje!")
else:
    driver, espera = novo_driver_logado()

    for nome_condominio, codigo_condominio in condominios_de_hoje:
        sucesso = False
        for tentativa in range(6):  # tenta até 6 vezes - a sessão do site cai com frequência
            try:
                if not sessao_esta_viva(driver):
                    print("  O navegador caiu/fechou - abrindo um novo e fazendo login de novo...")
                    driver, espera = novo_driver_logado()
                elif esta_deslogado(driver):
                    print("  A sessão do site caiu (voltou pra tela de login) - logando de novo...")
                    fazer_login(driver, espera)

                processar_condominio(driver, espera, nome_condominio, codigo_condominio)
                sucesso = True
                break
            except Exception as erro:
                if tentativa < 5:
                    print(f"  Falhou na tentativa {tentativa + 1} ({erro}). Tentando de novo em 2s...")
                    time.sleep(2)
                else:
                    print(f"  ERRO ao processar {codigo_condominio} - {nome_condominio} (6 tentativas falharam): {erro}")
                    print("  Pulando para o próximo condomínio...")

    print("\nTodos os condomínios de hoje foram processados!")