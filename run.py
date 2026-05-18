from app import create_app, db
from app.models.inventory import Loja, Produto, Estoque, Categoria, Usuario

app = create_app()

def popular_banco_dados():
    """Função auxiliar para criar as tabelas e injetar dados fictícios de teste."""
    with app.app_context():
        # Cria as tabelas baseadas nos models
        db.create_all()
        
        # Se não houver lojas, insere o seed inicial
        if not Loja.query.first():
            print("Populando o banco de dados com dados iniciais...")
            
            # Lojas
            loja1 = Loja(nome="Loja 1 (Matriz)", cnpj="00000000000100")
            loja2 = Loja(nome="Loja 2 (Filial)", cnpj="00000000000200")
            db.session.add_all([loja1, loja2])
            db.session.commit()
            
            # Usuários
            gerente = Usuario(username="admin", role="Gerente", loja_id=loja1.id)
            gerente.set_password("admin123")
            vendedor = Usuario(username="vendedor", role="Vendedor", loja_id=loja1.id)
            vendedor.set_password("vend123")
            db.session.add_all([gerente, vendedor])
            db.session.commit()
            
            # Categorias
            cat1 = Categoria(nome="Cabos")
            cat2 = Categoria(nome="Disjuntores")
            cat3 = Categoria(nome="Iluminação")
            cat4 = Categoria(nome="Acessórios e Materiais")
            db.session.add_all([cat1, cat2, cat3, cat4])
            db.session.commit()
            
            # 10 Produtos elétricos variados
            p1 = Produto(nome="Cabo Flexível 2.5mm Rolo 100m", sku="CAB001", preco=145.90, categoria_id=cat1.id)
            p2 = Produto(nome="Cabo Flexível 4.0mm Rolo 100m", sku="CAB002", preco=210.50, categoria_id=cat1.id)
            p3 = Produto(nome="Cabo Flexível 6.0mm Rolo 100m", sku="CAB003", preco=320.00, categoria_id=cat1.id)
            p4 = Produto(nome="Disjuntor DIN Bipolar 40A", sku="DIS040", preco=38.50, categoria_id=cat2.id)
            p5 = Produto(nome="Disjuntor DIN Monopolar 20A", sku="DIS020", preco=12.90, categoria_id=cat2.id)
            p6 = Produto(nome="Disjuntor DR Tetrapolar 63A", sku="DISDR63", preco=185.00, categoria_id=cat2.id)
            p7 = Produto(nome="Lâmpada LED 12W Branca Fria", sku="LMP012-B", preco=9.90, categoria_id=cat3.id)
            p8 = Produto(nome="Lâmpada LED 9W Amarela Quente", sku="LMP009-A", preco=8.50, categoria_id=cat3.id)
            p9 = Produto(nome="Placa 4x2 com 2 Tomadas 10A", sku="TOM4X2", preco=18.90, categoria_id=cat4.id)
            p10 = Produto(nome="Fita Isolante 3M 20m", sku="FIT020", preco=7.50, categoria_id=cat4.id)
            db.session.add_all([p1, p2, p3, p4, p5, p6, p7, p8, p9, p10])
            db.session.commit()
            
            # Distribuindo estoques variados com quantidades físicas e reservas
            estoques = [
                # Cabos
                Estoque(produto_id=p1.id, loja_id=loja1.id, quantidade_fisica=50, quantidade_reservada=10),
                Estoque(produto_id=p1.id, loja_id=loja2.id, quantidade_fisica=20, quantidade_reservada=0),
                Estoque(produto_id=p2.id, loja_id=loja1.id, quantidade_fisica=30, quantidade_reservada=5),
                Estoque(produto_id=p2.id, loja_id=loja2.id, quantidade_fisica=10, quantidade_reservada=0),
                Estoque(produto_id=p3.id, loja_id=loja1.id, quantidade_fisica=15, quantidade_reservada=0),
                Estoque(produto_id=p3.id, loja_id=loja2.id, quantidade_fisica=5,  quantidade_reservada=0),
                
                # Disjuntores
                Estoque(produto_id=p4.id, loja_id=loja1.id, quantidade_fisica=20, quantidade_reservada=10),
                Estoque(produto_id=p4.id, loja_id=loja2.id, quantidade_fisica=30, quantidade_reservada=5),
                Estoque(produto_id=p5.id, loja_id=loja1.id, quantidade_fisica=100, quantidade_reservada=20),
                Estoque(produto_id=p5.id, loja_id=loja2.id, quantidade_fisica=50, quantidade_reservada=0),
                
                # Disjuntor DR - Teste de Gargalo: Tem físico, mas tudo reservado na Loja 1
                Estoque(produto_id=p6.id, loja_id=loja1.id, quantidade_fisica=5,  quantidade_reservada=5),
                Estoque(produto_id=p6.id, loja_id=loja2.id, quantidade_fisica=0,  quantidade_reservada=0),
                
                # Iluminação
                Estoque(produto_id=p7.id, loja_id=loja1.id, quantidade_fisica=200, quantidade_reservada=50),
                Estoque(produto_id=p7.id, loja_id=loja2.id, quantidade_fisica=150, quantidade_reservada=0),
                Estoque(produto_id=p8.id, loja_id=loja1.id, quantidade_fisica=50,  quantidade_reservada=0),
                Estoque(produto_id=p8.id, loja_id=loja2.id, quantidade_fisica=80,  quantidade_reservada=10),
                
                # Acessórios
                Estoque(produto_id=p9.id, loja_id=loja1.id, quantidade_fisica=80,  quantidade_reservada=5),
                Estoque(produto_id=p9.id, loja_id=loja2.id, quantidade_fisica=40,  quantidade_reservada=0),
                Estoque(produto_id=p10.id, loja_id=loja1.id, quantidade_fisica=300, quantidade_reservada=0),
                Estoque(produto_id=p10.id, loja_id=loja2.id, quantidade_fisica=200, quantidade_reservada=20)
            ]
            db.session.add_all(estoques)
            db.session.commit()
            print("Banco populado com sucesso!")

if __name__ == '__main__':
    # Em um ambiente real, você rodaria a migração via Flask-Migrate (ex: flask db upgrade)
    # Aqui, para facilitar o MVP local, inicializamos e populamos os dados se estiver vazio:
    popular_banco_dados()
    
    # Roda a aplicação
    app.run(host='0.0.0.0', port=5000, debug=True)
