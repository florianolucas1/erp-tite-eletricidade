from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from datetime import datetime, timedelta
from flask_login import login_required, current_user
from app.models.inventory import Produto, Loja, Estoque, Movimentacao, Consignacao, Cliente, Usuario
from app import db
from sqlalchemy import func

# Blueprint para organizar as rotas de inventário
inventory_bp = Blueprint('inventory', __name__)

@inventory_bp.before_request
def auto_migrate():
    from sqlalchemy import text
    try:
        db.session.execute(text("ALTER TABLE consignacoes ADD COLUMN data_limite DATETIME"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        # Novas colunas para Cliente
        db.session.execute(text("ALTER TABLE clientes ADD COLUMN tipo_pessoa VARCHAR(2) DEFAULT 'PF'"))
        db.session.execute(text("ALTER TABLE clientes ADD COLUMN inscricao_estadual VARCHAR(50)"))
        db.session.execute(text("ALTER TABLE clientes ADD COLUMN email VARCHAR(150)"))
        db.session.execute(text("ALTER TABLE clientes ADD COLUMN rua VARCHAR(150)"))
        db.session.execute(text("ALTER TABLE clientes ADD COLUMN bairro VARCHAR(100)"))
        db.session.execute(text("ALTER TABLE clientes ADD COLUMN cidade VARCHAR(100)"))
        db.session.execute(text("ALTER TABLE clientes ADD COLUMN estado VARCHAR(2)"))
        db.session.execute(text("ALTER TABLE clientes ADD COLUMN cep VARCHAR(10)"))
        db.session.execute(text("ALTER TABLE clientes ADD COLUMN inadimplente BOOLEAN DEFAULT 0"))
        # Nova coluna para Movimentacoes
        db.session.execute(text("ALTER TABLE movimentacoes ADD COLUMN cliente_id INTEGER REFERENCES clientes(id)"))
        db.session.commit()
    except:
        db.session.rollback()
        
    try:
        db.session.execute(text("ALTER TABLE produtos ADD COLUMN nf_compra VARCHAR(100)"))
        db.session.commit()
    except:
        db.session.rollback()
        
    try:
        db.session.execute(text("ALTER TABLE usuarios ADD COLUMN nome VARCHAR(150)"))
        db.session.execute(text("ALTER TABLE usuarios ADD COLUMN telefone VARCHAR(50)"))
        db.session.execute(text("ALTER TABLE usuarios ADD COLUMN email VARCHAR(150)"))
        db.session.commit()
    except:
        db.session.rollback()

    try:
        # Cria tabela de usuarios se não existir (sqlite bypass)
        db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(256) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'Vendedor',
            loja_id INTEGER NOT NULL,
            nome VARCHAR(150),
            telefone VARCHAR(50),
            email VARCHAR(150),
            FOREIGN KEY(loja_id) REFERENCES lojas(id)
        )
        """))
        db.session.commit()
        
        # Cria usuário default Admin master se não existir
        from app.models.inventory import Usuario, Loja
        
        loja_matriz = Loja.query.first()
        if loja_matriz:
            master_admin = Usuario.query.filter_by(username='admin').first()
            if not master_admin:
                master_admin = Usuario(username='admin', role='Admin', loja_id=loja_matriz.id)
                master_admin.set_password('admin')
                db.session.add(master_admin)
            else:
                master_admin.role = 'Admin'
                # Forçar a atualização da senha para 'admin' para caso já existisse antes com 'admin123'
                master_admin.set_password('admin')
            
            db.session.commit()
    except:
        db.session.rollback()
        
    try:
        # Auto-Sync/Self-Healing: Garante que a quantidade_reservada espelha exatamente a realidade das consignações abertas.
        # Isto corrige os dados fictícios iniciais do run.py que criaram reservas fantasmas.
        estoques = Estoque.query.all()
        for est in estoques:
            total_real = db.session.query(func.sum(Consignacao.quantidade)).filter_by(
                produto_id=est.produto_id, loja_id=est.loja_id, status='ABERTO'
            ).scalar() or 0
            
            if est.quantidade_reservada != total_real:
                est.quantidade_reservada = total_real
                
        db.session.commit()
    except:
        db.session.rollback()

@inventory_bp.route('/')
@inventory_bp.route('/dashboard')
@login_required
def dashboard():
    """
    Dashboard otimizado que funde os indicadores numéricos, o gráfico e a tabela detalhada do inventário.
    """
        
    produtos = Produto.query.all()
    lojas = Loja.query.all()
    
    total_fisico_rede = 0
    total_reservado_rede = 0
    inventario = []
    produtos_em_alerta = []
    
    for produto in produtos:
        item = {
            'sku': produto.sku,
            'nome': produto.nome,
            'preco': produto.preco,
            'estoques': {}, 
            'estoque_global': 0,
            'estoque_minimo': 15
        }
        
        fisico_total_produto = 0
        
        for loja in lojas:
            estoque = Estoque.query.filter_by(produto_id=produto.id, loja_id=loja.id).first()
            if estoque:
                qtd_disp = estoque.saldo_disponivel
                fisico = estoque.quantidade_fisica
                reservado = estoque.quantidade_reservada
                
                item['estoques'][str(loja.id)] = qtd_disp
                item['estoque_global'] += qtd_disp
                total_fisico_rede += fisico
                total_reservado_rede += reservado
                fisico_total_produto += fisico
            else:
                item['estoques'][str(loja.id)] = 0
                
        # Status Global
        if item['estoque_global'] == 0:
            item['status'] = 'Esgotado'
            item['status_class'] = 'bg-danger'
        elif item['estoque_global'] <= item['estoque_minimo']:
            item['status'] = 'Baixo Estoque'
            item['status_class'] = 'bg-warning text-dark'
        else:
            item['status'] = 'Normal'
            item['status_class'] = 'bg-success'
            
        inventario.append(item)
        
        # US06: Identificar produtos cujo estoque FÍSICO total é inferior ao limite
        if fisico_total_produto < item['estoque_minimo']:
            produtos_em_alerta.append({
                'sku': produto.sku,
                'nome': produto.nome,
                'fisico': fisico_total_produto
            })
        
    return render_template(
        'dashboard.html', 
        inventario=inventario, 
        lojas=lojas,
        total_fisico=total_fisico_rede,
        total_reservado=total_reservado_rede,
        alertas_baixo_estoque=produtos_em_alerta
    )

def verificar_saldo_global(produto_id, quantidade_desejada):
    """
    Função de Lógica de Negócio:
    Verifica o saldo de um produto em ambas as lojas simultaneamente 
    antes de permitir uma venda, garantindo a visão global da rede.
    """
    estoques = Estoque.query.filter_by(produto_id=produto_id).all()
    saldo_total_rede = sum([e.saldo_disponivel for e in estoques])
    
    return saldo_total_rede >= quantidade_desejada

@inventory_bp.route('/api/venda', methods=['POST'])
def realizar_venda():
    """Endpoint API para simular a realização de uma venda verificando estoque global."""
    dados = request.json
    
    if not dados:
        return jsonify({"erro": "Dados da venda não fornecidos."}), 400
        
    produto_id = dados.get('produto_id')
    quantidade = dados.get('quantidade')
    loja_id = dados.get('loja_id') # Loja onde a venda está sendo tentada

    if not all([produto_id, quantidade, loja_id]):
        return jsonify({"erro": "Parâmetros insuficientes."}), 400

    # Regra de negócio exigida: verificar em todas as lojas antes de vender
    if verificar_saldo_global(produto_id, quantidade):
        # A lógica completa aqui verificaria em qual loja abater o estoque,
        # ou se geraria uma 'Reserva Lógica' (status) caso o produto precise vir de outra loja.
        
        estoque_loja_atual = Estoque.query.filter_by(produto_id=produto_id, loja_id=loja_id).first()
        
        if estoque_loja_atual and estoque_loja_atual.saldo_disponivel >= quantidade:
            # Tem na própria loja: efetiva direto
            estoque_loja_atual.quantidade_fisica -= quantidade
            
            nova_mov = Movimentacao(
                produto_id=produto_id,
                loja_id=loja_id,
                quantidade=-quantidade,
                tipo='SAIDA_VENDA'
            )
            db.session.add(nova_mov)
            db.session.commit()
            
            return jsonify({"mensagem": "Venda realizada com sucesso na loja local!"}), 200
        else:
            # Não tem saldo suficiente na loja local, MAS tem na rede.
            # Aqui aplicamos a "Reserva Lógica" na loja que tem o saldo.
            return jsonify({
                "mensagem": "Saldo insuficiente na loja atual. " + 
                            "Necessário acionar transferência (Reserva Lógica) da outra unidade."
            }), 200
    else:
        return jsonify({"erro": "Saldo global insuficiente para esta venda na rede."}), 400

@inventory_bp.route('/venda/consignacao', methods=['POST'])
def realizar_consignacao():
    """
    Cria uma nova consignação: reserva o produto logicamente, mas mantém o estoque físico inalterado.
    """
    dados = request.json
    if not dados:
        return jsonify({"erro": "Corpo da requisição vazio."}), 400

    produto_id = dados.get('id_produto')
    loja_id = dados.get('id_loja')
    quantidade = dados.get('quantidade')
    cliente_id = dados.get('cliente_id', 1)  # Valor padrão 1 se não for passado no MVP

    if not all([produto_id, loja_id, quantidade]):
        return jsonify({"erro": "Os campos id_produto, id_loja e quantidade são obrigatórios."}), 400

    if quantidade <= 0:
        return jsonify({"erro": "A quantidade deve ser maior que zero."}), 400

    try:
        # Boas Práticas: Iniciar explicitamente uma transação (embora o SQLAlchemy faça isso)
        # Vamos buscar o estoque com controle de concorrência se aplicável, mas para o MVP um query simples serve.
        estoque = Estoque.query.filter_by(produto_id=produto_id, loja_id=loja_id).first()

        if not estoque:
            return jsonify({"erro": "Não existe registro de estoque para este produto nesta loja."}), 404

        # 1. Verifica se o saldo disponível é suficiente
        if estoque.saldo_disponivel >= quantidade:
            
            # 2. Incrementa a reserva
            estoque.quantidade_reservada += quantidade
            
            # Cria a rastreabilidade da Consignação
            nova_consignacao = Consignacao(
                loja_id=loja_id,
                produto_id=produto_id,
                cliente_id=cliente_id,
                quantidade=quantidade,
                status='ABERTO'
            )
            
            db.session.add(nova_consignacao)
            
            # 3. Commita a transação para o banco de forma atômica
            db.session.commit()
            
            return jsonify({
                "mensagem": "Consignação realizada com sucesso! Produto reservado.",
                "estoque_atualizado": {
                    "quantidade_fisica": estoque.quantidade_fisica,
                    "quantidade_reservada": estoque.quantidade_reservada,
                    "saldo_disponivel": estoque.saldo_disponivel
                }
            }), 201
            
        else:
            # 4. Falha: Analisa o motivo da falta de saldo
            if estoque.quantidade_fisica >= quantidade:
                # O produto existe fisicamente, mas está na posse/reserva de outros
                return jsonify({
                    "erro": "Reserva negada.",
                    "detalhes": f"O produto está fisicamente na loja ({estoque.quantidade_fisica} unidades), "
                                f"mas já está reservado/consignado para outros clientes. "
                                f"Saldo disponível real: {estoque.saldo_disponivel} unidades."
                }), 409 # 409 Conflict
            else:
                return jsonify({
                    "erro": "Reserva negada.",
                    "detalhes": f"Estoque físico insuficiente. Existe apenas {estoque.quantidade_fisica} un."
                }), 400

    except Exception as e:
        # Rollback atômico em caso de qualquer erro no banco
        db.session.rollback()
        return jsonify({"erro": "Erro interno durante a transação.", "detalhes": str(e)}), 500



@inventory_bp.route('/consignacoes')
@login_required
def tela_consignacoes():
    """
    Dashboard de Gestão de Consignações.
    """
        
    produtos = Produto.query.order_by(Produto.nome).all()
    lojas = Loja.query.all()
    clientes = Cliente.query.order_by(Cliente.nome).all()
    consignacoes_ativas = Consignacao.query.filter_by(status='ABERTO').order_by(Consignacao.data_saida.desc()).all()
    # Adiciona datetime nativo ao contexto para o template Jinja poder calcular dias
    return render_template('consignacoes.html', consignacoes_ativas=consignacoes_ativas, lojas=lojas, produtos=produtos, clientes=clientes, agora=datetime.now())

@inventory_bp.route('/api/estoque/todos', methods=['GET'])
def listar_estoque_completo():
    """
    Retorna o inventário completo (físico e disponível) da rede, usado por interfaces SPA.
    """
    produtos = Produto.query.order_by(Produto.nome).all()
    lojas = Loja.query.all()
    
    lista = []
    for produto in produtos:
        item = {
            'id': produto.id,
            'sku': produto.sku,
            'nome': produto.nome,
            'preco': float(produto.preco),
            'estoque_global': 0
        }
        for loja in lojas:
            estoque = Estoque.query.filter_by(produto_id=produto.id, loja_id=loja.id).first()
            item['estoque_global'] += estoque.saldo_disponivel if estoque else 0
        lista.append(item)
        
    return jsonify(lista), 200

@inventory_bp.route('/api/estoque/<sku>', methods=['GET'])
def consultar_situacao_global(sku):
    """
    US06: Retorna um JSON consolidado com a situação de estoque (Físico vs Disponível)
    de um produto em todas as lojas, incluindo lógica de Alerta de Reposição.
    """
    produto = Produto.query.filter_by(sku=sku).first()
    
    if not produto:
        return jsonify({"erro": f"Produto com SKU '{sku}' não encontrado na base."}), 404

    lojas = Loja.query.all()
    estoque_minimo = 15  # Parâmetro pré-definido no MVP
    
    # Estrutura base da resposta
    resposta = {
        "produto": {
            "sku": produto.sku,
            "nome": produto.nome,
            "preco": float(produto.preco)
        },
        "situacao_lojas": {},
        "total_geral": {
            "fisico": 0,
            "reservado": 0,
            "disponivel": 0
        },
        "status": "NORMAL",
        "alerta_reposicao": False
    }

    # Varre o estoque cruzando as lojas
    for loja in lojas:
        estoque = Estoque.query.filter_by(produto_id=produto.id, loja_id=loja.id).first()
        
        fisico = estoque.quantidade_fisica if estoque else 0
        reservado = estoque.quantidade_reservada if estoque else 0
        disponivel = estoque.saldo_disponivel if estoque else 0
        
        # Popula o balanço individual da loja
        resposta["situacao_lojas"][loja.nome] = {
            "fisico": fisico,
            "reservado": reservado,
            "disponivel": disponivel
        }
        
        # Consolida o somatório global
        resposta["total_geral"]["fisico"] += fisico
        resposta["total_geral"]["reservado"] += reservado
        resposta["total_geral"]["disponivel"] += disponivel

    # Regra de Negócio: Alerta de Reposição (US06)
    # A decisão de comprar mais baseia-se no que está de facto disponível (se está na carrinha, não podemos vender).
    if resposta["total_geral"]["disponivel"] == 0:
        resposta["status"] = "ESGOTADO"
        resposta["alerta_reposicao"] = True
        resposta["mensagem"] = "Ruptura de estoque confirmada. Necessário acionar fornecedor urgentemente."
    elif resposta["total_geral"]["disponivel"] <= estoque_minimo:
        resposta["status"] = "BAIXO_ESTOQUE"
        resposta["alerta_reposicao"] = True
        resposta["mensagem"] = f"Atenção: O saldo global ({resposta['total_geral']['disponivel']} un) atingiu a margem de segurança ({estoque_minimo} un). Preparar reposição."
    else:
        resposta["mensagem"] = "Estoque saudável."

    return jsonify(resposta), 200

@inventory_bp.route('/vendedor')
@login_required
def tela_vendedor():
    """
    Interface focada no Vendedor: Busca dinâmica e visão comparativa de estoque (Lado a Lado) em cards.
    """
    produtos = Produto.query.order_by(Produto.nome).all()
    # Mostra primeiro os dados da loja do usuário logado
    todas_lojas = Loja.query.all()
    lojas = sorted(todas_lojas, key=lambda l: l.id == current_user.loja_id, reverse=True)
    
    clientes = Cliente.query.all()
    
    inventario = []
    for produto in produtos:
        item = {
            'id': produto.id,
            'sku': produto.sku,
            'nome': produto.nome,
            'preco': produto.preco,
            'estoques': {}
        }
        for loja in lojas:
            estoque = Estoque.query.filter_by(produto_id=produto.id, loja_id=loja.id).first()
            item['estoques'][str(loja.id)] = estoque.saldo_disponivel if estoque else 0
            
        inventario.append(item)
        
    return render_template('vendedor.html', inventario=inventario, lojas=lojas, clientes=clientes)

@inventory_bp.route('/api/consignacao/devolver', methods=['POST'])
def devolver_consignacao():
    """
    Finaliza a consignação por devolução do material.
    O produto volta a ficar disponível (quantidade_reservada diminui),
    mas a quantidade_fisica não se altera, pois ele nunca saiu de facto do nosso património.
    """
    dados = request.json
    if not dados or not dados.get('id_consignacao'):
        return jsonify({"erro": "O campo id_consignacao é obrigatório."}), 400

    id_consignacao = dados.get('id_consignacao')

    try:
        consignacao = Consignacao.query.get(id_consignacao)
        
        if not consignacao:
            return jsonify({"erro": "Consignação não encontrada."}), 404
            
        if consignacao.status != 'ABERTO':
            return jsonify({"erro": f"Esta consignação não pode ser devolvida pois o status atual é {consignacao.status}."}), 400

        # Altera o status
        consignacao.status = 'DEVOLVIDO'

        # Busca o estoque para abater a reserva
        estoque = Estoque.query.filter_by(
            produto_id=consignacao.produto_id, 
            loja_id=consignacao.loja_id
        ).first()

        if estoque:
            # A devolução significa que a mercadoria que estava reservada voltou
            # e pode ser vendida a outro. O físico não muda.
            estoque.quantidade_reservada -= consignacao.quantidade
            # Impede que fique negativo por alguma falha
            if estoque.quantidade_reservada < 0:
                estoque.quantidade_reservada = 0

        db.session.commit()
        return jsonify({"mensagem": "Material devolvido com sucesso. Saldo disponível restaurado!"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"erro": "Falha ao processar a devolução.", "detalhes": str(e)}), 500


@inventory_bp.route('/api/consignacao/efetivar-venda', methods=['POST'])
def efetivar_venda_consignacao():
    """
    O cliente usou o material e decidiu comprá-lo.
    Temos de finalizar a consignação, dar baixa no físico E na reserva lógica.
    E registar a movimentação como SAIDA_VENDA.
    """
    dados = request.json
    if not dados or not dados.get('id_consignacao'):
        return jsonify({"erro": "O campo id_consignacao é obrigatório."}), 400

    id_consignacao = dados.get('id_consignacao')

    try:
        consignacao = Consignacao.query.get(id_consignacao)
        
        if not consignacao:
            return jsonify({"erro": "Consignação não encontrada."}), 404
            
        if consignacao.status != 'ABERTO':
            return jsonify({"erro": f"Esta consignação não pode ser efetivada pois o status atual é {consignacao.status}."}), 400

        # Atualiza status
        consignacao.status = 'FINALIZADO'

        estoque = Estoque.query.filter_by(
            produto_id=consignacao.produto_id, 
            loja_id=consignacao.loja_id
        ).first()

        if estoque:
            # Baixa no físico E na reserva
            estoque.quantidade_fisica -= consignacao.quantidade
            estoque.quantidade_reservada -= consignacao.quantidade
            
            if estoque.quantidade_reservada < 0:
                estoque.quantidade_reservada = 0
            if estoque.quantidade_fisica < 0:
                estoque.quantidade_fisica = 0

            # Regista a movimentação oficial no Livro de Inventário
            nova_movimentacao = Movimentacao(
                produto_id=consignacao.produto_id,
                loja_id=consignacao.loja_id,
                quantidade=-consignacao.quantidade,
                tipo='SAIDA_VENDA'
            )
            db.session.add(nova_movimentacao)

        db.session.commit()
        return jsonify({"mensagem": "Venda efetivada com sucesso! Baixa de estoque concluída."}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"erro": "Falha ao efetivar a venda.", "detalhes": str(e)}), 500

@inventory_bp.route('/usuarios', methods=['GET'])
@login_required
def tela_usuarios():
    if current_user.role != 'Admin':
        return redirect(url_for('inventory.tela_vendedor'))
        
    usuarios = Usuario.query.all()
    lojas = Loja.query.all()
    return render_template('usuarios.html', usuarios=usuarios, lojas=lojas)

@inventory_bp.route('/api/usuario', methods=['POST'])
@login_required
def criar_usuario():
    if current_user.role != 'Admin':
        return jsonify({"erro": "Acesso negado."}), 403
        
    dados = request.json
    username = dados.get('username')
    password = dados.get('password')
    role = dados.get('role')
    loja_id = dados.get('loja_id')
    
    if not username or not password or not role or not loja_id:
        return jsonify({"erro": "Campos obrigatórios: username, password, role, loja."}), 400
        
    if Usuario.query.filter_by(username=username).first():
        return jsonify({"erro": "Já existe um usuário com esse username."}), 409
        
    novo_user = Usuario(
        username=username, 
        role=role, 
        loja_id=loja_id,
        nome=dados.get('nome'),
        telefone=dados.get('telefone'),
        email=dados.get('email')
    )
    novo_user.set_password(password)
    
    try:
        db.session.add(novo_user)
        db.session.commit()
        return jsonify({"mensagem": "Usuário criado com sucesso!"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"erro": "Falha ao gravar usuário.", "detalhes": str(e)}), 500

@inventory_bp.route('/api/usuario/<int:user_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def gerir_usuario(user_id):
    if current_user.role != 'Admin':
        return jsonify({"erro": "Acesso negado."}), 403
        
    user = Usuario.query.get_or_404(user_id)
    
    if request.method == 'GET':
        return jsonify({
            'id': user.id,
            'username': user.username,
            'role': user.role,
            'loja_id': user.loja_id,
            'nome': user.nome or '',
            'telefone': user.telefone or '',
            'email': user.email or ''
        }), 200
        
    if request.method == 'PUT':
        dados = request.json
        username = dados.get('username')
        
        if username:
            existente = Usuario.query.filter(Usuario.username == username, Usuario.id != user_id).first()
            if existente:
                return jsonify({"erro": "Já existe outro usuário com este username."}), 409
                
        user.username = username or user.username
        user.role = dados.get('role', user.role)
        user.loja_id = dados.get('loja_id', user.loja_id)
        user.nome = dados.get('nome', user.nome)
        user.telefone = dados.get('telefone', user.telefone)
        user.email = dados.get('email', user.email)
        
        if dados.get('password'):
            user.set_password(dados.get('password'))
            
        try:
            db.session.commit()
            return jsonify({"mensagem": "Usuário atualizado com sucesso!"}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"erro": "Falha ao atualizar usuário.", "detalhes": str(e)}), 500

    if request.method == 'DELETE':
        if user.id == current_user.id:
            return jsonify({"erro": "Você não pode apagar a si próprio."}), 400
            
        try:
            db.session.delete(user)
            db.session.commit()
            return jsonify({"mensagem": "Usuário apagado com sucesso!"}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"erro": "Falha ao apagar usuário.", "detalhes": str(e)}), 500

@inventory_bp.route('/api/cliente', methods=['POST'])
def criar_cliente():
    """
    Endpoint para cadastrar um novo cliente/eletricista rapidamente pelo PDV.
    """
    dados = request.json
    nome = dados.get('nome')
    cpf_cnpj = dados.get('cpf_cnpj')
    telefone = dados.get('telefone')
    
    tipo_pessoa = dados.get('tipo_pessoa', 'PF')
    inscricao_estadual = dados.get('inscricao_estadual')
    email = dados.get('email')
    rua = dados.get('rua')
    bairro = dados.get('bairro')
    cidade = dados.get('cidade')
    estado = dados.get('estado')
    cep = dados.get('cep')
    
    if not nome:
        return jsonify({"erro": "O nome do cliente é obrigatório."}), 400
        
    # Verifica se já existe o CPF/CNPJ (apenas se fornecido)
    if cpf_cnpj:
        existente = Cliente.query.filter_by(cpf_cnpj=cpf_cnpj).first()
        if existente:
            return jsonify({"erro": f"Já existe um cliente registado com este documento: {existente.nome}."}), 409
            
    novo_cliente = Cliente(
        tipo_pessoa=tipo_pessoa,
        nome=nome, 
        cpf_cnpj=cpf_cnpj, 
        inscricao_estadual=inscricao_estadual,
        telefone=telefone,
        email=email,
        rua=rua,
        bairro=bairro,
        cidade=cidade,
        estado=estado,
        cep=cep
    )
    
    try:
        db.session.add(novo_cliente)
        db.session.commit()
        return jsonify({
            "mensagem": "Cliente criado com sucesso!",
            "cliente": {
                "id": novo_cliente.id,
                "nome": novo_cliente.nome,
                "cpf_cnpj": novo_cliente.cpf_cnpj or ""
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"erro": "Falha ao gravar cliente na base de dados.", "detalhes": str(e)}), 500

@inventory_bp.route('/api/cliente/<int:cliente_id>', methods=['GET', 'PUT'])
@login_required
def gerir_cliente(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    
    if request.method == 'GET':
        return jsonify({
            "id": cliente.id,
            "tipo_pessoa": cliente.tipo_pessoa,
            "nome": cliente.nome,
            "cpf_cnpj": cliente.cpf_cnpj or "",
            "inscricao_estadual": cliente.inscricao_estadual or "",
            "telefone": cliente.telefone or "",
            "email": cliente.email or "",
            "rua": cliente.rua or "",
            "bairro": cliente.bairro or "",
            "cidade": cliente.cidade or "",
            "estado": cliente.estado or "",
            "cep": cliente.cep or ""
        }), 200
        
    if request.method == 'PUT':
        dados = request.json
        cpf_cnpj = dados.get('cpf_cnpj')
        
        # Verifica duplicidade de documento para outros clientes
        if cpf_cnpj:
            existente = Cliente.query.filter(Cliente.cpf_cnpj == cpf_cnpj, Cliente.id != cliente_id).first()
            if existente:
                return jsonify({"erro": f"Já existe outro cliente registado com este documento: {existente.nome}."}), 409

        cliente.tipo_pessoa = dados.get('tipo_pessoa', cliente.tipo_pessoa)
        cliente.nome = dados.get('nome', cliente.nome)
        cliente.cpf_cnpj = cpf_cnpj
        cliente.inscricao_estadual = dados.get('inscricao_estadual', cliente.inscricao_estadual)
        cliente.telefone = dados.get('telefone', cliente.telefone)
        cliente.email = dados.get('email', cliente.email)
        cliente.rua = dados.get('rua', cliente.rua)
        cliente.bairro = dados.get('bairro', cliente.bairro)
        cliente.cidade = dados.get('cidade', cliente.cidade)
        cliente.estado = dados.get('estado', cliente.estado)
        cliente.cep = dados.get('cep', cliente.cep)
        
        try:
            db.session.commit()
            return jsonify({"mensagem": "Cliente atualizado com sucesso!"}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"erro": "Falha ao atualizar cliente.", "detalhes": str(e)}), 500

@inventory_bp.route('/produtos', methods=['GET'])
@login_required
def tela_produtos():
    if current_user.role not in ['Gerente', 'Admin']:
        return redirect(url_for('inventory.tela_vendedor'))
        
    produtos = Produto.query.order_by(Produto.nome).all()
    loja_id = current_user.loja_id
    
    produtos_data = []
    for p in produtos:
        # Quantidade disponível
        estoque = Estoque.query.filter_by(produto_id=p.id, loja_id=loja_id).first()
        qtd_disponivel = estoque.saldo_disponivel if estoque else 0
        qtd_fisica = estoque.quantidade_fisica if estoque else 0
        
        # Quantidade em consignação
        consignacoes_abertas = db.session.query(func.sum(Consignacao.quantidade)).filter(
            Consignacao.produto_id == p.id,
            Consignacao.status == 'ABERTO'
        ).scalar() or 0
        
        produtos_data.append({
            'id': p.id,
            'sku': p.sku,
            'nome': p.nome,
            'preco': p.preco,
            'nf_compra': p.nf_compra or '',
            'qtd_disponivel': qtd_disponivel,
            'qtd_fisica': qtd_fisica,
            'qtd_consignacao': consignacoes_abertas
        })
        
    return render_template('produtos.html', produtos=produtos_data)

@inventory_bp.route('/api/produto', methods=['POST'])
@login_required
def criar_produto():
    if current_user.role not in ['Gerente', 'Admin']:
        return jsonify({"erro": "Acesso negado."}), 403
        
    dados = request.json
    sku = dados.get('sku')
    nome = dados.get('nome')
    preco = dados.get('preco')
    nf_compra = dados.get('nf_compra')
    quantidade_inicial = int(dados.get('quantidade', 0))
    
    if not sku or not nome or preco is None:
        return jsonify({"erro": "SKU, nome e preço são obrigatórios."}), 400
        
    if Produto.query.filter_by(sku=sku).first():
        return jsonify({"erro": "Já existe um produto com esse SKU."}), 409
        
    novo_produto = Produto(sku=sku, nome=nome, preco=preco, nf_compra=nf_compra, categoria_id=1) # Categoria default
    
    try:
        db.session.add(novo_produto)
        db.session.flush() # Para gerar o ID do produto
        
        # Cria o estoque na loja do gerente
        loja_id = current_user.loja_id
        estoque = Estoque(produto_id=novo_produto.id, loja_id=loja_id, quantidade_fisica=quantidade_inicial)
        db.session.add(estoque)
        
        # Regista movimentação de entrada inicial
        if quantidade_inicial > 0:
            mov = Movimentacao(produto_id=novo_produto.id, loja_id=loja_id, tipo='ENTRADA', quantidade=quantidade_inicial, observacao="Entrada inicial via cadastro")
            db.session.add(mov)
            
        db.session.commit()
        return jsonify({"mensagem": "Produto criado com sucesso!"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"erro": "Falha ao gravar produto.", "detalhes": str(e)}), 500

@inventory_bp.route('/api/produto/<int:produto_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def gerir_produto(produto_id):
    if current_user.role not in ['Gerente', 'Admin']:
        return jsonify({"erro": "Acesso negado."}), 403
        
    produto = Produto.query.get_or_404(produto_id)
    loja_id = current_user.loja_id
    
    if request.method == 'GET':
        estoque = Estoque.query.filter_by(produto_id=produto.id, loja_id=loja_id).first()
        return jsonify({
            'id': produto.id,
            'sku': produto.sku,
            'nome': produto.nome,
            'preco': str(produto.preco),
            'nf_compra': produto.nf_compra or '',
            'quantidade': estoque.quantidade_fisica if estoque else 0
        }), 200
        
    if request.method == 'PUT':
        dados = request.json
        sku = dados.get('sku')
        
        if sku:
            existente = Produto.query.filter(Produto.sku == sku, Produto.id != produto_id).first()
            if existente:
                return jsonify({"erro": "Já existe outro produto com este SKU."}), 409
                
        produto.sku = sku or produto.sku
        produto.nome = dados.get('nome', produto.nome)
        produto.preco = dados.get('preco', produto.preco)
        produto.nf_compra = dados.get('nf_compra', produto.nf_compra)
        
        nova_qtd = dados.get('quantidade')
        if nova_qtd is not None:
            nova_qtd = int(nova_qtd)
            estoque = Estoque.query.filter_by(produto_id=produto.id, loja_id=loja_id).first()
            if not estoque:
                estoque = Estoque(produto_id=produto.id, loja_id=loja_id, quantidade_fisica=nova_qtd)
                db.session.add(estoque)
                if nova_qtd > 0:
                    mov = Movimentacao(produto_id=produto.id, loja_id=loja_id, tipo='ENTRADA', quantidade=nova_qtd, observacao="Ajuste via edição de produto")
                    db.session.add(mov)
            else:
                diferenca = nova_qtd - estoque.quantidade_fisica
                if diferenca != 0:
                    estoque.quantidade_fisica = nova_qtd
                    tipo_mov = 'ENTRADA' if diferenca > 0 else 'SAIDA_VENDA' # ou SAIDA_AJUSTE, mas o banco tem restrições
                    mov = Movimentacao(produto_id=produto.id, loja_id=loja_id, tipo=tipo_mov, quantidade=abs(diferenca), observacao="Ajuste manual de estoque na edição de produto")
                    db.session.add(mov)
        
        try:
            db.session.commit()
            return jsonify({"mensagem": "Produto atualizado com sucesso!"}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"erro": "Falha ao atualizar produto.", "detalhes": str(e)}), 500

    if request.method == 'DELETE':
        try:
            # Apaga os estoques, não se pode apagar se tiver histórico nas outras tabelas?
            # Para evitar erros de FK, se já foi vendido não apaga
            tem_movs = Movimentacao.query.filter_by(produto_id=produto.id).first()
            if tem_movs:
                 return jsonify({"erro": "Este produto não pode ser apagado pois já possui histórico de movimentações."}), 400
                 
            Estoque.query.filter_by(produto_id=produto.id).delete()
            db.session.delete(produto)
            db.session.commit()
            return jsonify({"mensagem": "Produto apagado com sucesso!"}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"erro": "Falha ao apagar produto.", "detalhes": str(e)}), 500

@inventory_bp.route('/clientes', methods=['GET'])
@login_required
def tela_clientes():
    """
    Página de Gestão de Clientes.
    """
    clientes = Cliente.query.order_by(Cliente.nome).all()
    return render_template('clientes.html', clientes=clientes)

@inventory_bp.route('/api/cliente/<int:cliente_id>/historico', methods=['GET'])
@login_required
def historico_cliente(cliente_id):
    """
    Retorna o histórico de compras, consignações em aberto e status de inadimplência.
    """
    cliente = Cliente.query.get_or_404(cliente_id)
    
    # Consignacoes
    consignacoes = Consignacao.query.filter_by(cliente_id=cliente_id).order_by(Consignacao.data_saida.desc()).all()
    consig_abertas = [c for c in consignacoes if c.status == 'ABERTO']
    
    # Compras
    movimentacoes = Movimentacao.query.filter_by(cliente_id=cliente_id, tipo='SAIDA_VENDA').order_by(Movimentacao.data_movimentacao.desc()).all()
    
    historico_compras = []
    for m in movimentacoes:
        prod = Produto.query.get(m.produto_id)
        loja = Loja.query.get(m.loja_id)
        historico_compras.append({
            "data": m.data_movimentacao.strftime("%d/%m/%Y %H:%M"),
            "produto": prod.nome if prod else "Desconhecido",
            "quantidade": abs(m.quantidade),
            "loja": loja.nome if loja else f"Loja {m.loja_id}",
            "valor_total": float(prod.preco) * abs(m.quantidade) if prod else 0
        })
        
    consignacoes_list = []
    for c in consig_abertas:
        prod = Produto.query.get(c.produto_id)
        dias_aberto = (datetime.now() - c.data_saida).days if c.data_saida else 0
        consignacoes_list.append({
            "id": c.id,
            "produto": prod.nome if prod else "Desconhecido",
            "quantidade": c.quantidade,
            "data_saida": c.data_saida.strftime("%d/%m/%Y") if c.data_saida else "N/A",
            "data_limite": c.data_limite.strftime("%d/%m/%Y") if c.data_limite else "N/A",
            "dias_aberto": dias_aberto,
            "atrasado": c.data_limite and datetime.now() > c.data_limite
        })
        
    return jsonify({
        "cliente": {
            "nome": cliente.nome,
            "documento": cliente.cpf_cnpj,
            "telefone": cliente.telefone,
            "email": cliente.email,
            "inadimplente": cliente.inadimplente
        },
        "historico_compras": historico_compras,
        "consignacoes_abertas": consignacoes_list
    }), 200

@inventory_bp.route('/api/pdv/checkout', methods=['POST'])
def pdv_checkout():
    """
    Processa um carrinho de compras completo (Múltiplos produtos).
    Pode ser finalizado como VENDA DIRETA ou CONSIGNACAO.
    Garante transação atómica: ou aprova tudo, ou dá rollback a tudo.
    """
    dados = request.json
    cliente_id = dados.get('cliente_id')
    loja_id = dados.get('loja_id')
    tipo_operacao = dados.get('tipo_operacao') # 'VENDA_DIRETA' ou 'CONSIGNACAO'
    prazo_dias = dados.get('prazo_dias') # opcional, padrão 7
    carrinho = dados.get('carrinho', [])
    
    if not carrinho or not cliente_id or not loja_id or tipo_operacao not in ['VENDA_DIRETA', 'CONSIGNACAO']:
        return jsonify({"erro": "Dados insuficientes ou operação inválida."}), 400
        
    try:
        data_limite_calc = None
        if tipo_operacao == 'CONSIGNACAO' and prazo_dias:
            try:
                data_limite_calc = datetime.now() + timedelta(days=int(prazo_dias))
            except ValueError:
                pass

        # Prepara os itens para um possível PDF e processa o estoque
        pdf_itens = []
        for item in carrinho:
            id_produto = item.get('id_produto')
            quantidade = item.get('quantidade')
            
            prod = Produto.query.get(id_produto)
            if prod:
                pdf_itens.append({
                    'sku': prod.sku,
                    'nome': prod.nome,
                    'quantidade': quantidade,
                    'preco': float(prod.preco)
                })
            
            # Validação de Estoque Físico/Disponível Global (Soma das lojas)
            if not verificar_saldo_global(id_produto, quantidade):
                db.session.rollback()
                prod = Produto.query.get(id_produto)
                return jsonify({"erro": f"Estoque insuficiente na rede para o produto: {prod.nome if prod else id_produto}."}), 400
                
            # Lógica Inteligente de Baixa/Reserva Multi-Loja (Evita Constraint Error de Estoque Negativo)
            restante = quantidade
            
            # Ordena para garantir que a loja selecionada é a primeira a ceder estoque
            estoques_produto = Estoque.query.filter_by(produto_id=id_produto).order_by(
                (Estoque.loja_id == loja_id).desc()
            ).all()
            
            for est in estoques_produto:
                if restante <= 0:
                    break
                    
                disp_nesta_loja = est.saldo_disponivel
                if disp_nesta_loja > 0:
                    a_retirar = min(restante, disp_nesta_loja)
                    
                    if tipo_operacao == 'CONSIGNACAO':
                        est.quantidade_reservada += a_retirar
                        
                        nova_consignacao = Consignacao(
                            cliente_id=cliente_id,
                            produto_id=id_produto,
                            loja_id=est.loja_id, # regista a loja exata de onde saiu
                            quantidade=a_retirar,
                            status='ABERTO',
                            data_limite=data_limite_calc
                        )
                        db.session.add(nova_consignacao)
                        
                        nova_mov = Movimentacao(
                            produto_id=id_produto,
                            loja_id=est.loja_id,
                            quantidade=a_retirar,
                            tipo='SAIDA_CONSIGNACAO',
                            cliente_id=cliente_id
                        )
                        db.session.add(nova_mov)
                        
                    elif tipo_operacao == 'VENDA_DIRETA':
                        est.quantidade_fisica -= a_retirar
                        
                        nova_mov = Movimentacao(
                            produto_id=id_produto,
                            loja_id=est.loja_id,
                            quantidade=-a_retirar,
                            tipo='SAIDA_VENDA',
                            cliente_id=cliente_id
                        )
                        db.session.add(nova_mov)
                        
                    restante -= a_retirar
                
        # Confirma TUDO de uma vez
        db.session.commit()
        
        pdf_url = None
        cliente = Cliente.query.get(cliente_id) if cliente_id else None
        
        cliente_dict = None
        if cliente:
            cliente_dict = {
                'nome': cliente.nome,
                'cpf_cnpj': cliente.cpf_cnpj,
                'telefone': cliente.telefone,
                'rua': cliente.rua,
                'bairro': cliente.bairro,
                'cidade': cliente.cidade,
                'estado': cliente.estado
            }

        if tipo_operacao == 'CONSIGNACAO':
            from app.utils.pdf_generator import gerar_pdf_consignacao
            try:
                filename = gerar_pdf_consignacao(
                    cliente_dict=cliente_dict,
                    itens=pdf_itens,
                    data_saida=datetime.now(),
                    data_limite=data_limite_calc
                )
                pdf_url = f"/static/pdfs/{filename}"
            except Exception as e:
                print(f"Erro a gerar PDF Consignação: {e}")
                
        elif tipo_operacao == 'VENDA_DIRETA':
            from app.utils.pdf_generator import gerar_pdf_venda_direta
            try:
                filename = gerar_pdf_venda_direta(
                    cliente_dict=cliente_dict,
                    itens=pdf_itens,
                    data_venda=datetime.now()
                )
                pdf_url = f"/static/pdfs/{filename}"
            except Exception as e:
                print(f"Erro a gerar PDF Venda: {e}")
                
        msg = "Produtos reservados em consignação com sucesso!" if tipo_operacao == 'CONSIGNACAO' else "Venda concluída e baixa no estoque efetuada!"
        return jsonify({"mensagem": msg, "pdf_url": pdf_url}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"erro": "Erro crítico no processamento do carrinho.", "detalhes": str(e)}), 500
@inventory_bp.route('/relatorio')
@login_required
def tela_relatorio():
    """
    Página de Relatório Gerencial (Apenas Gerentes).
    """
    if current_user.role not in ['Gerente', 'Admin']:
        return redirect(url_for('inventory.tela_vendedor'))
    return render_template('relatorio.html')

@inventory_bp.route('/api/relatorio/vendas', methods=['GET'])
@login_required
def api_relatorio_vendas():
    """
    API Analítica para o Dashboard de Relatórios.
    Retorna Faturamento, Curva ABC, Vendas por Loja e Evolução Diária.
    """
    if current_user.role not in ['Gerente', 'Admin']:
        return jsonify({"erro": "Acesso negado. Apenas gerentes podem visualizar relatórios."}), 403

    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')

    query = db.session.query(Movimentacao).filter(Movimentacao.tipo == 'SAIDA_VENDA')
    
    if data_inicio:
        try:
            start_dt = datetime.strptime(data_inicio, '%Y-%m-%d')
            query = query.filter(Movimentacao.data_movimentacao >= start_dt)
        except ValueError:
            pass
            
    if data_fim:
        try:
            end_dt = datetime.strptime(data_fim, '%Y-%m-%d') + timedelta(days=1) - timedelta(seconds=1)
            query = query.filter(Movimentacao.data_movimentacao <= end_dt)
        except ValueError:
            pass

    movimentacoes = query.all()

    total_faturamento = 0
    # Aproximação de "operações" para ticket médio agrupando por Data/Hora/Loja
    operacoes_set = set()
    vendas_por_loja = {}
    vendas_diarias = {}
    produtos_agregados = {}

    for mov in movimentacoes:
        prod = Produto.query.get(mov.produto_id)
        if not prod:
            continue
            
        qtd = abs(mov.quantidade)
        receita = qtd * float(prod.preco)
        total_faturamento += receita
        
        operacao_key = f"{mov.loja_id}-{mov.data_movimentacao.strftime('%Y-%m-%d %H:%M')}"
        operacoes_set.add(operacao_key)

        # Loja
        loja_obj = Loja.query.get(mov.loja_id)
        loja_nome = loja_obj.nome if loja_obj else f"Loja {mov.loja_id}"
        vendas_por_loja[loja_nome] = vendas_por_loja.get(loja_nome, 0) + receita

        # Vendas Diárias
        dia = mov.data_movimentacao.strftime('%Y-%m-%d')
        vendas_diarias[dia] = vendas_diarias.get(dia, 0) + receita

        # Produtos para ABC
        if prod.id not in produtos_agregados:
            produtos_agregados[prod.id] = {'sku': prod.sku, 'nome': prod.nome, 'quantidade': 0, 'receita': 0}
        
        produtos_agregados[prod.id]['quantidade'] += qtd
        produtos_agregados[prod.id]['receita'] += receita

    total_operacoes = len(operacoes_set)
    ticket_medio = total_faturamento / total_operacoes if total_operacoes > 0 else 0

    # Curva ABC
    lista_abc = list(produtos_agregados.values())
    lista_abc.sort(key=lambda x: x['receita'], reverse=True)

    receita_acumulada = 0
    qtd_a = qtd_b = qtd_c = 0
    produtos_a = []

    for item in lista_abc:
        receita_acumulada += item['receita']
        perc = (receita_acumulada / total_faturamento) * 100 if total_faturamento > 0 else 0
        
        # Algoritmo padrão Curva ABC:
        # A: ~80% do faturamento
        # B: ~15% do faturamento (até 95% do acumulado)
        # C: ~5% do faturamento (restante)
        if perc <= 80:
            item['classe'] = 'A'
            qtd_a += 1
            produtos_a.append(item)
        elif perc <= 95:
            item['classe'] = 'B'
            qtd_b += 1
        else:
            item['classe'] = 'C'
            qtd_c += 1

    # Ordenar dias
    dias_ordenados = sorted(vendas_diarias.keys())
    evolucao_diaria = {
        'labels': dias_ordenados,
        'valores': [vendas_diarias[d] for d in dias_ordenados]
    }

    return jsonify({
        'resumo': {
            'faturamento': total_faturamento,
            'ticket_medio': ticket_medio,
            'operacoes': total_operacoes
        },
        'vendas_lojas': vendas_por_loja,
        'evolucao_diaria': evolucao_diaria,
        'curva_abc_grafico': {
            'A': sum([p['receita'] for p in lista_abc if p['classe'] == 'A']),
            'B': sum([p['receita'] for p in lista_abc if p['classe'] == 'B']),
            'C': sum([p['receita'] for p in lista_abc if p['classe'] == 'C']),
            'QtdA': qtd_a,
            'QtdB': qtd_b,
            'QtdC': qtd_c
        },
        'produtos_a': produtos_a,
        'lista_completa_abc': lista_abc
    }), 200
