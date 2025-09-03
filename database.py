import sqlite3
from flask import g

DATABASE = 'automacao.db'

def get_db():
    """Abre uma nova conexão com o banco de dados se não houver uma."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    """Inicializa o banco de dados e cria/atualiza a tabela de clientes."""
    db = get_db()
    cursor = db.cursor()
    print("Verificando e inicializando o banco de dados...")

    cursor.execute("PRAGMA table_info(clients)")
    existing_columns = [row['name'] for row in cursor.fetchall()]

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, logo_url TEXT,
        rss_url TEXT, json_url TEXT, bg_color_primary TEXT DEFAULT '#d90429',
        bg_color_secondary TEXT DEFAULT '#0d1b2a', text_color TEXT DEFAULT '#FFFFFF',
        footer_text TEXT, hashtags TEXT, meta_api_token TEXT, instagram_id TEXT,
        facebook_page_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Dicionário de colunas a serem adicionadas/verificadas
    all_columns = {
        "wp_url": "TEXT", "wp_user": "TEXT", "wp_password": "TEXT",
        "caption_template": "TEXT", "font_size_title": "INTEGER DEFAULT 50",
        "font_size_footer": "INTEGER DEFAULT 30",
        "cloudinary_cloud_name": "TEXT",
        "cloudinary_api_key": "TEXT",
        "cloudinary_api_secret": "TEXT",
        # Nova coluna para rastreamento do RSS
        "last_posted_guid": "TEXT"
    }

    for col, col_type in all_columns.items():
        if col not in existing_columns:
            print(f"Adicionando coluna '{col}'...")
            cursor.execute(f"ALTER TABLE clients ADD COLUMN {col} {col_type}")

    db.commit()
    print("Banco de dados pronto.")

if __name__ == '__main__':
    with sqlite3.connect(DATABASE) as conn:
        g._database = conn
        init_db()

