#!/usr/bin/env bash
# Script de Build (Render)

# 1. Instalar dependências
pip install -r requirements.txt

# 2. Inicializar / Migrar Banco de Dados
python -c "
from app import create_app, db
from app.models.inventory import Loja, Usuario, Categoria, Produto, Estoque
app = create_app()
with app.app_context():
    db.create_all()
    # Verifica se precisa popular as lojas base
    if not Loja.query.first():
        loja1 = Loja(nome='Loja 1 (Matriz)', cnpj='00000000000100')
        loja2 = Loja(nome='Loja 2 (Filial)', cnpj='00000000000200')
        db.session.add_all([loja1, loja2])
        db.session.commit()
        
        # O usuário admin master será criado automaticamente pelo auto_migrate
"
