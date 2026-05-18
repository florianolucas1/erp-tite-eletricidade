from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

# Inicialização do banco de dados (ORM) e Login
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Por favor, faça login para aceder a esta página.'
login_manager.login_message_category = 'warning'

def create_app():
    """Factory function para criar a instância da aplicação Flask."""
    app = Flask(__name__, template_folder='views/templates', static_folder='views/static')
    app.config.from_object(Config)

    # Vincula o banco de dados e o login_manager à aplicação
    db.init_app(app)
    login_manager.init_app(app)

    # Carregador de Usuário para o Flask-Login
    from app.models.inventory import Usuario
    @login_manager.user_loader
    def load_user(user_id):
        return Usuario.query.get(int(user_id))

    # Registro de Controllers (Blueprints)
    from app.controllers.auth_controller import auth_bp
    from app.controllers.inventory_controller import inventory_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(inventory_bp)

    # Tratamento Global de Erros de Banco de Dados e Validação (Impede o temido erro 500)
    from sqlalchemy.exc import SQLAlchemyError

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(e):
        db.session.rollback()
        return jsonify({
            "erro": "Ação negada pelas regras de integridade do Banco de Dados.",
            "detalhes": "Não é possível concluir a transação (ex: Estoque físico/reservado insuficiente ou dados duplicados)."
        }), 409
        
    @app.errorhandler(ValueError)
    def handle_value_error(e):
        # Trata erros lançados pelo @validates do SQLAlchemy e outras lógicas
        return jsonify({
            "erro": "Erro de Validação.",
            "detalhes": str(e)
        }), 400

    return app
