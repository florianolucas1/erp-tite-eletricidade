import os
from fpdf import FPDF
from datetime import datetime

def gerar_pdf_consignacao(cliente_dict, itens, data_saida, data_limite):
    pdf = FPDF()
    pdf.add_page()
    
    # Cabeçalho
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, 'TITE ELETRICIDADE - TERMO DE CONSIGNAÇÃO', 0, 1, 'C')
    pdf.ln(5)
    
    # Dados do Cliente
    pdf.set_font("Arial", 'B', 10)
    
    nome = cliente_dict.get('nome', 'N/A')
    cpf_cnpj = cliente_dict.get('cpf_cnpj', 'N/A')
    telefone = cliente_dict.get('telefone', 'N/A')
    endereco = f"{cliente_dict.get('rua', '')}, {cliente_dict.get('bairro', '')} - {cliente_dict.get('cidade', '')}/{cliente_dict.get('estado', '')}"
    
    doc_label = "CPF"
    if cpf_cnpj and len("".join(filter(str.isdigit, str(cpf_cnpj)))) > 11:
        doc_label = "CNPJ"
            
    pdf.cell(0, 6, f"Cliente: {nome} | {doc_label}: {cpf_cnpj}", 0, 1)
    pdf.cell(0, 6, f"Contato: {telefone} | Endereco: {endereco}", 0, 1)
    
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, f"Data de Retirada: {data_saida.strftime('%d/%m/%Y %H:%M')}", 0, 1)
    
    pdf.set_font("Arial", 'B', 11)
    prazo_str = data_limite.strftime('%d/%m/%Y') if data_limite else 'Sem Prazo'
    
    # Destaca a data de vencimento com cor mais escura
    pdf.set_text_color(200, 0, 0)
    pdf.cell(0, 8, f"Data Limite de Devolução/Faturamento: {prazo_str}", 0, 1)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)
    
    # Tabela de Itens (Cabeçalho)
    pdf.set_font("Arial", 'B', 10)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(30, 10, 'SKU', 1, 0, 'C', fill=True)
    pdf.cell(90, 10, 'Produto', 1, 0, 'C', fill=True)
    pdf.cell(30, 10, 'Qtd', 1, 0, 'C', fill=True)
    pdf.cell(40, 10, 'Valor Unit (R$)', 1, 1, 'C', fill=True)
    
    # Conteúdo da Tabela
    pdf.set_font("Arial", '', 10)
    total_valor = 0
    for item in itens:
        pdf.cell(30, 10, str(item['sku']), 1)
        pdf.cell(90, 10, str(item['nome'])[:40], 1)
        pdf.cell(30, 10, str(item['quantidade']), 1, 0, 'C')
        pdf.cell(40, 10, f"{item['preco']:.2f}", 1, 1, 'R')
        total_valor += (item['quantidade'] * item['preco'])
        
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(150)
    pdf.cell(40, 10, f"Total: R$ {total_valor:.2f}", 0, 1, 'R')
    
    # Termos e Assinatura
    pdf.ln(20)
    pdf.set_font("Arial", 'I', 9)
    termo = ("Declaro ter recebido os materiais acima listados em perfeito estado. "
             "Comprometo-me a devolve-los ou efetuar o pagamento integral ate a data limite estipulada. "
             "O nao cumprimento do prazo implicara no faturamento automatico dos itens.")
    pdf.multi_cell(0, 5, termo)
    
    pdf.ln(35)
    pdf.cell(0, 10, "_______________________________________________________", 0, 1, 'C')
    pdf.cell(0, 5, "Assinatura do Cliente", 0, 1, 'C')
    
    # Gera o nome do ficheiro e grava na pasta static
    filename = f"consignacao_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    
    # Usa caminhos absolutos baseados no diretorio principal
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'views', 'static', 'pdfs'))
    os.makedirs(base_dir, exist_ok=True)
    
    filepath = os.path.join(base_dir, filename)
    pdf.output(filepath)
    
    return filename

def gerar_pdf_venda_direta(cliente_dict, itens, data_venda):
    pdf = FPDF()
    pdf.add_page()
    
    # Cabeçalho
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, 'TITE ELETRICIDADE - COMPROVANTE DE VENDA', 0, 1, 'C')
    pdf.ln(5)
    
    # Dados do Cliente (Opcional na Venda Direta)
    pdf.set_font("Arial", 'B', 10)
    if cliente_dict:
        nome = cliente_dict.get('nome', 'Consumidor Final')
        cpf_cnpj = cliente_dict.get('cpf_cnpj', 'N/A')
        telefone = cliente_dict.get('telefone', 'N/A')
        endereco = f"{cliente_dict.get('rua', '')}, {cliente_dict.get('bairro', '')} - {cliente_dict.get('cidade', '')}/{cliente_dict.get('estado', '')}"
        
        doc_label = "CPF"
        if cpf_cnpj and len("".join(filter(str.isdigit, str(cpf_cnpj)))) > 11:
            doc_label = "CNPJ"
                
        pdf.cell(0, 6, f"Cliente: {nome} | {doc_label}: {cpf_cnpj}", 0, 1)
        pdf.cell(0, 6, f"Contato: {telefone} | Endereco: {endereco}", 0, 1)
    else:
        pdf.cell(0, 6, "Cliente: Consumidor Final (Nao Cadastrado)", 0, 1)
    
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, f"Data da Venda: {data_venda.strftime('%d/%m/%Y %H:%M')}", 0, 1)
    pdf.ln(10)
    
    # Tabela de Itens (Cabeçalho)
    pdf.set_font("Arial", 'B', 10)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(30, 10, 'SKU', 1, 0, 'C', fill=True)
    pdf.cell(90, 10, 'Produto', 1, 0, 'C', fill=True)
    pdf.cell(30, 10, 'Qtd', 1, 0, 'C', fill=True)
    pdf.cell(40, 10, 'Valor Unit (R$)', 1, 1, 'C', fill=True)
    
    # Conteúdo da Tabela
    pdf.set_font("Arial", '', 10)
    total_valor = 0
    for item in itens:
        pdf.cell(30, 10, str(item['sku']), 1)
        pdf.cell(90, 10, str(item['nome'])[:40], 1)
        pdf.cell(30, 10, str(item['quantidade']), 1, 0, 'C')
        pdf.cell(40, 10, f"{item['preco']:.2f}", 1, 1, 'R')
        total_valor += (item['quantidade'] * item['preco'])
        
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(150)
    pdf.cell(40, 10, f"Total Pago: R$ {total_valor:.2f}", 0, 1, 'R')
    
    pdf.ln(35)
    pdf.set_font("Arial", 'I', 9)
    pdf.cell(0, 10, "_______________________________________________________", 0, 1, 'C')
    pdf.cell(0, 5, "Assinatura do Vendedor / Responsavel", 0, 1, 'C')
    
    # Gera o nome do ficheiro e grava na pasta static
    filename = f"venda_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'views', 'static', 'pdfs'))
    os.makedirs(base_dir, exist_ok=True)
    filepath = os.path.join(base_dir, filename)
    pdf.output(filepath)
    
    return filename
