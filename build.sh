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
        print('Lojas base criadas.')
        
    # Garante que existe pelo menos uma categoria para os produtos
    if not Categoria.query.first():
        cat_default = Categoria(nome='Geral')
        db.session.add(cat_default)
        db.session.commit()
        print('Categoria base criada.')
        
    loja_matriz = Loja.query.first()
    
    # O usuário admin master deve ser sempre verificado e criado independentemente das Lojas
    if loja_matriz:
        master_admin = Usuario.query.filter_by(username='admin').first()
        if not master_admin:
            master_admin = Usuario(username='admin', role='Admin', loja_id=loja_matriz.id)
            master_admin.set_password('admin')
            db.session.add(master_admin)
        else:
            master_admin.role = 'Admin'
            master_admin.set_password('admin')
            
        db.session.commit()
        print('Usuário admin garantido.')
"
