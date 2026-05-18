from app import db
from datetime import datetime
from sqlalchemy import CheckConstraint, Index, text
from sqlalchemy.orm import validates
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class Categoria(db.Model):
    __tablename__ = 'categorias'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    
    produtos = db.relationship('Produto', backref='categoria', lazy=True)

class Loja(db.Model):
    __tablename__ = 'lojas'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cnpj = db.Column(db.String(14), nullable=False, unique=True)
    
    estoques = db.relationship('Estoque', backref='loja', lazy=True)
    movimentacoes = db.relationship('Movimentacao', backref='loja', lazy=True)
    consignacoes = db.relationship('Consignacao', backref='loja', lazy=True)
    usuarios = db.relationship('Usuario', backref='loja', lazy=True)

class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='Vendedor') # 'Admin', 'Gerente' ou 'Vendedor'
    loja_id = db.Column(db.Integer, db.ForeignKey('lojas.id', ondelete='RESTRICT'), nullable=False)
    nome = db.Column(db.String(150), nullable=True)
    telefone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(150), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Produto(db.Model):
    __tablename__ = 'produtos'
    id = db.Column(db.Integer, primary_key=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias.id', ondelete='RESTRICT'))
    sku = db.Column(db.String(50), nullable=False, unique=True)
    nome = db.Column(db.String(200), nullable=False)
    preco = db.Column(db.Numeric(10, 2), nullable=False)
    nf_compra = db.Column(db.String(100), nullable=True)
    
    estoques = db.relationship('Estoque', backref='produto', lazy=True)
    movimentacoes = db.relationship('Movimentacao', backref='produto', lazy=True)
    consignacoes = db.relationship('Consignacao', backref='produto', lazy=True)

    __table_args__ = (
        CheckConstraint('preco >= 0', name='chk_preco_positivo'),
        Index('idx_produtos_sku', 'sku'),
    )

class Cliente(db.Model):
    __tablename__ = 'clientes'
    id = db.Column(db.Integer, primary_key=True)
    tipo_pessoa = db.Column(db.String(2), nullable=False, default='PF') # PF ou PJ
    nome = db.Column(db.String(150), nullable=False)
    cpf_cnpj = db.Column(db.String(18), unique=True)
    inscricao_estadual = db.Column(db.String(50))
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(150))
    rua = db.Column(db.String(150))
    bairro = db.Column(db.String(100))
    cidade = db.Column(db.String(100))
    estado = db.Column(db.String(2))
    cep = db.Column(db.String(10))
    inadimplente = db.Column(db.Boolean, default=False)
    
    consignacoes = db.relationship('Consignacao', backref='cliente', lazy=True)
    movimentacoes = db.relationship('Movimentacao', backref='cliente', lazy=True)

class Estoque(db.Model):
    __tablename__ = 'estoque'
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produtos.id', ondelete='RESTRICT'), nullable=False)
    loja_id = db.Column(db.Integer, db.ForeignKey('lojas.id', ondelete='RESTRICT'), nullable=False)
    
    quantidade_fisica = db.Column(db.Integer, nullable=False, default=0)
    quantidade_reservada = db.Column(db.Integer, nullable=False, default=0)
    
    # Coluna gerada de forma dinâmica no banco de dados (Suportado no PostgreSQL 12+ via SQLAlchemy 2.0+)
    saldo_disponivel = db.Column(
        db.Integer, 
        db.Computed('quantidade_fisica - quantidade_reservada', persisted=True)
    )

    @validates('quantidade_fisica', 'quantidade_reservada')
    def validate_quantidades(self, key, value):
        if value < 0:
            raise ValueError(f"Operação Inválida: A {key} nunca pode ser inferior a zero (Tentativa: {value}).")
        return value

    __table_args__ = (
        db.UniqueConstraint('produto_id', 'loja_id', name='uq_estoque_produto_loja'),
        CheckConstraint('quantidade_fisica >= 0', name='chk_qtd_fisica_positiva'),
        CheckConstraint('quantidade_reservada >= 0', name='chk_qtd_reserv_positiva'),
        CheckConstraint('quantidade_fisica - quantidade_reservada >= 0', name='chk_saldo_valido'),
        Index('idx_estoque_loja_produto', 'loja_id', 'produto_id'),
    )

class Movimentacao(db.Model):
    __tablename__ = 'movimentacoes'
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produtos.id', ondelete='RESTRICT'), nullable=False)
    loja_id = db.Column(db.Integer, db.ForeignKey('lojas.id', ondelete='RESTRICT'), nullable=False)
    tipo = db.Column(db.String(50), nullable=False) # ENTRADA, SAIDA_VENDA, TRANSFERENCIA, SAIDA_CONSIGNACAO, RETORNO_CONSIGNACAO
    quantidade = db.Column(db.Integer, nullable=False)
    data_movimentacao = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    observacao = db.Column(db.Text)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id', ondelete='SET NULL'), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('ENTRADA', 'SAIDA_VENDA', 'TRANSFERENCIA', 'SAIDA_CONSIGNACAO', 'RETORNO_CONSIGNACAO')",
            name='chk_tipo_movimentacao'
        ),
        Index('idx_movimentacoes_data_loja', 'loja_id', 'data_movimentacao'),
    )

class Consignacao(db.Model):
    __tablename__ = 'consignacoes'
    id = db.Column(db.Integer, primary_key=True)
    loja_id = db.Column(db.Integer, db.ForeignKey('lojas.id', ondelete='RESTRICT'), nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey('produtos.id', ondelete='RESTRICT'), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='ABERTO') # ABERTO, FINALIZADO, DEVOLVIDO
    data_saida = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    data_limite = db.Column(db.DateTime, nullable=True)
    data_retorno = db.Column(db.DateTime)

    __table_args__ = (
        CheckConstraint('quantidade > 0', name='chk_consignacao_qtd_positiva'),
        CheckConstraint("status IN ('ABERTO', 'FINALIZADO', 'DEVOLVIDO')", name='chk_status_consignacao'),
        # Índice parcial para otimizar a busca por consignações ainda abertas
        Index('idx_consignacoes_status', 'status', postgresql_where=text("status = 'ABERTO'")),
    )
