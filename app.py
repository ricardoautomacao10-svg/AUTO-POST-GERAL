<<<<<<< HEAD
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings

# Ignora o aviso sobre usar o parser de HTML para XML, pois vamos tratar isso
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# BLOCO 1: IMPORTAÇÕES E CONFIGURAÇÃO INICIAL
# ==============================================================================
import os
import io
import requests
import textwrap
import secrets
import cloudinary
import cloudinary.uploader
import feedparser
from flask import Flask, request, jsonify, render_template, flash, redirect, url_for, g
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from database import init_db, get_db

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)

with app.app_context():
    init_db()

print("🚀 INICIANDO APLICAÇÃO DE AUTOMAÇÃO v4.3 (Automação por RSS)")

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# ==============================================================================
# BLOCO 2: FUNÇÕES DE LÓGICA DE NEGÓCIO
# ==============================================================================

def criar_imagem_post(url_imagem_noticia, titulo_post, config_cliente):
    print(f"🎨 Criando imagem para: {config_cliente['name']} - {titulo_post[:30]}...")
    try:
        response_img = requests.get(url_imagem_noticia, stream=True, timeout=15); response_img.raise_for_status()
        imagem_noticia = Image.open(io.BytesIO(response_img.content)).convert("RGBA")
        response_logo = requests.get(config_cliente['logo_url'], stream=True, timeout=15); response_logo.raise_for_status()
        logo = Image.open(io.BytesIO(response_logo.content)).convert("RGBA")
        fonte_titulo = ImageFont.truetype("Anton-Regular.ttf", int(config_cliente.get('font_size_title', 50)))
        fonte_rodape = ImageFont.truetype("Anton-Regular.ttf", int(config_cliente.get('font_size_footer', 30)))
        imagem_final = Image.new('RGBA', (1080, 1080), (255, 255, 255, 255))
        draw = ImageDraw.Draw(imagem_final)
        imagem_noticia_resized = imagem_noticia.resize((980, 551))
        imagem_final.paste(imagem_noticia_resized, (50, 50))
        draw.rounded_rectangle([(40, 610), (1040, 1040)], radius=40, fill=config_cliente['bg_color_primary'])
        draw.rounded_rectangle([(50, 620), (1030, 1030)], radius=40, fill=config_cliente['bg_color_secondary'])
        logo.thumbnail((220, 220))
        imagem_final.paste(logo, ((1080 - logo.width) // 2, 620 - (logo.height // 2)), logo)
        linhas_texto = textwrap.wrap(titulo_post.upper(), width=32)
        draw.text((540, 800), "\n".join(linhas_texto), font=fonte_titulo, fill=config_cliente['text_color'], anchor="mm", align="center")
        draw.text((540, 980), config_cliente['footer_text'], font=fonte_rodape, fill=config_cliente['text_color'], anchor="ms", align="center")
        buffer_saida = io.BytesIO()
        imagem_final.convert('RGB').save(buffer_saida, format='JPEG', quality=95)
        return buffer_saida.getvalue()
    except Exception as e:
        print(f"❌ Erro na criação da imagem: {e}")
        return None

def upload_para_cloudinary(bytes_imagem, nome_arquivo, config_cliente):
    creds = {'cloud_name': config_cliente.get('cloudinary_cloud_name'),'api_key': config_cliente.get('cloudinary_api_key'),'api_secret': config_cliente.get('cloudinary_api_secret')}
    if not all(creds.values()): return None, "Credenciais do Cloudinary incompletas."
    try:
        cloudinary.config(**creds)
        response = cloudinary.uploader.upload(io.BytesIO(bytes_imagem), public_id=nome_arquivo, folder=f"automacao_posts/{config_cliente['id']}", overwrite=True)
        return response.get('secure_url'), "Upload para Cloudinary OK."
    except Exception as e: return None, f"Erro no upload para Cloudinary: {e}"

def publicar_no_instagram(url_imagem, legenda, config_cliente):
    token, insta_id = config_cliente.get('meta_api_token'), config_cliente.get('instagram_id')
    if not all([token, insta_id]): return False, "Credenciais do Instagram incompletas."
    try:
        url_container = f"https://graph.facebook.com/v19.0/{insta_id}/media"
        params_container = {'image_url': url_imagem, 'caption': legenda, 'access_token': token}
        r_container = requests.post(url_container, params=params_container, timeout=20); r_container.raise_for_status()
        id_criacao = r_container.json()['id']
        url_publicacao = f"https://graph.facebook.com/v19.0/{insta_id}/media_publish"
        params_publicacao = {'creation_id': id_criacao, 'access_token': token}
        requests.post(url_publicacao, params=params_publicacao, timeout=20).raise_for_status()
        return True, "Publicado no Instagram com sucesso!"
    except Exception as e: return False, f"Falha no Instagram: {e}"

def publicar_no_facebook(url_imagem, legenda, config_cliente):
    token, page_id = config_cliente.get('meta_api_token'), config_cliente.get('facebook_page_id')
    if not all([token, page_id]): return False, "Credenciais do Facebook incompletas."
    try:
        url_post_foto = f"https://graph.facebook.com/v19.0/{page_id}/photos"
        params = {'url': url_imagem, 'message': legenda, 'access_token': token}
        requests.post(url_post_foto, params=params, timeout=20).raise_for_status()
        return True, "Publicado no Facebook com sucesso!"
    except Exception as e: return False, f"Falha no Facebook: {e}"

def extrair_dados_noticia(url):
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        titulo = (soup.find('meta', property='og:title') or soup.find('h1')).get('content', soup.find('h1').text)
        resumo = (soup.find('meta', property='og:description') or soup.find('p')).get('content', soup.find('p').text)
        imagem = (soup.find('meta', property='og:image')).get('content')
        return {"titulo": titulo.strip(), "resumo": resumo.strip(), "url_imagem": imagem}
    except Exception as e: return None

# CRUD Routes
@app.route('/')
def admin_panel():
    db = get_db()
    clients = db.execute('SELECT * FROM clients ORDER BY name').fetchall()
    return render_template('admin.html', clients=clients)

@app.route('/client/add', methods=['POST'])
def add_client():
    try:
        db = get_db()
        db.execute("""
            INSERT INTO clients (name, logo_url, wp_url, wp_user, wp_password, rss_url, json_url, 
            bg_color_primary, bg_color_secondary, text_color, font_size_title, font_size_footer, 
            footer_text, hashtags, caption_template, meta_api_token, instagram_id, facebook_page_id,
            cloudinary_cloud_name, cloudinary_api_key, cloudinary_api_secret) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (request.form['name'], request.form['logo_url'], request.form['wp_url'], request.form['wp_user'], 
            request.form['wp_password'], request.form['rss_url'], request.form['json_url'], request.form['bg_color_primary'],
            request.form['bg_color_secondary'], request.form['text_color'], request.form['font_size_title'], 
            request.form['font_size_footer'], request.form['footer_text'], request.form['hashtags'], 
            request.form['caption_template'], request.form['meta_api_token'], request.form['instagram_id'], 
            request.form['facebook_page_id'], request.form['cloudinary_cloud_name'], 
            request.form['cloudinary_api_key'], request.form['cloudinary_api_secret']))
        db.commit()
        flash('Cliente adicionado com sucesso!', 'success')
    except Exception as e: flash(f'Erro ao adicionar cliente: {e}', 'danger')
    return redirect(url_for('admin_panel'))

@app.route('/client/edit/<int:client_id>', methods=['GET', 'POST'])
def edit_client(client_id):
    db = get_db()
    if request.method == 'POST':
        try:
            query = "UPDATE clients SET name=?, logo_url=?, wp_url=?, rss_url=?, json_url=?, bg_color_primary=?, bg_color_secondary=?, text_color=?, font_size_title=?, font_size_footer=?, footer_text=?, hashtags=?, caption_template=?, instagram_id=?, facebook_page_id=?, cloudinary_cloud_name=?, cloudinary_api_key=? "
            params = [request.form[k] for k in ['name', 'logo_url', 'wp_url', 'rss_url', 'json_url', 'bg_color_primary', 'bg_color_secondary', 'text_color', 'font_size_title', 'font_size_footer', 'footer_text', 'hashtags', 'caption_template', 'instagram_id', 'facebook_page_id', 'cloudinary_cloud_name', 'cloudinary_api_key']]
            if request.form.get('wp_password'): query += ", wp_password = ?"; params.append(request.form['wp_password'])
            if request.form.get('meta_api_token'): query += ", meta_api_token = ?"; params.append(request.form['meta_api_token'])
            if request.form.get('cloudinary_api_secret'): query += ", cloudinary_api_secret = ?"; params.append(request.form['cloudinary_api_secret'])
            query += " WHERE id = ?"; params.append(client_id)
            db.execute(query, tuple(params)); db.commit()
            flash('Cliente atualizado com sucesso!', 'success')
            return redirect(url_for('admin_panel'))
        except Exception as e: flash(f'Erro ao atualizar cliente: {e}', 'danger')
    client = db.execute('SELECT * FROM clients WHERE id = ?', (client_id,)).fetchone()
    if not client: flash('Cliente não encontrado.', 'danger'); return redirect(url_for('admin_panel'))
    return render_template('edit_client.html', client=client)

@app.route('/client/delete/<int:client_id>', methods=['POST'])
def delete_client(client_id):
    try:
        db = get_db(); db.execute('DELETE FROM clients WHERE id = ?', (client_id,)); db.commit()
        flash('Cliente removido com sucesso!', 'success')
    except Exception as e: flash(f'Erro ao remover cliente: {e}', 'danger')
def get_article_details(url):
    """Busca os detalhes de um artigo (título, resumo, imagem) a partir de uma URL."""
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        title = soup.find('meta', property='og:title')
        excerpt = soup.find('meta', property='og:description')
        image_url = soup.find('meta', property='og:image')

        return {
            "title": title['content'] if title else soup.title.string,
            "excerpt": excerpt['content'] if excerpt else "Resumo não encontrado.",
            "image_url": image_url['content'] if image_url else None
        }
    except Exception as e:
        print(f"❌ [ERRO] Falha ao extrair detalhes da URL {url}: {e}")
        return None

def fetch_rss_feed(feed_url):
    """Busca e analisa um feed RSS, retornando as notícias."""
    print(f"📰 Buscando feed RSS de: {feed_url}")
    try:
        # Usa o parser lxml-xml para maior confiabilidade com feeds
        feed = feedparser.parse(feed_url)
        if feed.bozo:
            # Bozo flag é 1 (True) se o feed estiver malformado
            raise Exception(f"Feed malformado - {feed.bozo_exception}")
        return feed.entries
    except Exception as e:
        print(f"❌ [ERRO] Não foi possível buscar ou analisar o feed RSS {feed_url}: {e}")
        return []

@app.route('/run_automation', methods=['POST'])
def run_automation():
    db = get_db()
    clients = db.execute('SELECT * FROM clients WHERE rss_url IS NOT NULL AND rss_url != ""').fetchall()
    if not clients:
        flash("Nenhum cliente com Feed RSS configurado foi encontrado.", "warning")
        return redirect(url_for('admin_panel'))
    
    total_posts_made = 0
    for client in clients:
        print(f"Verificando feed para {client['name']}...")
        try:
            feed = feedparser.parse(client['rss_url'])
            if feed.bozo: raise Exception(f"Feed RSS mal formatado: {feed.bozo_exception}")
            last_guid = client['last_posted_guid']
            guids = [entry.get('id', entry.link) for entry in feed.entries]
            if last_guid in guids: new_entries = feed.entries[:guids.index(last_guid)]
            else: new_entries = feed.entries[:5] # Limite para primeira execução ou feed antigo
            
            if not new_entries: continue
            new_entries.reverse() # Publicar do mais antigo para o mais novo
            
            for entry in new_entries[:10]: # Limite de 10 por execução para segurança
                guid = entry.get('id', entry.link)
                image_url = find_image_in_entry(entry)
                if not image_url: continue
                
                imagem_bytes = criar_imagem_post(image_url, entry.title, client)
                if not imagem_bytes: continue
                
                public_url, _ = upload_para_cloudinary(imagem_bytes, f"post_rss_{client['id']}_{secrets.token_hex(4)}", client)
                if not public_url: continue
                
                summary = BeautifulSoup(entry.summary, 'html.parser').get_text(separator=' ', strip=True)
                resumo_curto = textwrap.shorten(summary, width=200, placeholder="...")
                caption_template = client.get('caption_template') or "{title}\n\n{excerpt}\n\n{hashtags}"
                legenda_final = caption_template.format(title=entry.title, excerpt=resumo_curto, hashtags=client.get('hashtags', ''))
                
                publicar_no_instagram(public_url, legenda_final, client)
                publicar_no_facebook(public_url, legenda_final, client)
                
                db.execute("UPDATE clients SET last_posted_guid = ? WHERE id = ?", (guid, client['id'])); db.commit()
                total_posts_made += 1
        except Exception as e:
            flash(f"Erro ao processar o feed para '{client['name']}': {e}", "danger")
    
    if total_posts_made == 0: flash("Verificação concluída. Nenhuma novidade para publicar.", "info")
    else: flash(f"Automação concluída! Total de {total_posts_made} posts publicados.", "success")
    return redirect(url_for('admin_panel'))

# ==============================================================================
# BLOCO 4: INICIALIZAÇÃO
# ==============================================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)


=======
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings

# Ignora o aviso sobre usar o parser de HTML para XML, pois vamos tratar isso
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# BLOCO 1: IMPORTAÇÕES E CONFIGURAÇÃO INICIAL
# ==============================================================================
import os
import io
import requests
import textwrap
import secrets
import cloudinary
import cloudinary.uploader
import feedparser
from flask import Flask, request, jsonify, render_template, flash, redirect, url_for, g
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from database import init_db, get_db

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)

with app.app_context():
    init_db()

print("🚀 INICIANDO APLICAÇÃO DE AUTOMAÇÃO v4.3 (Automação por RSS)")

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# ==============================================================================
# BLOCO 2: FUNÇÕES DE LÓGICA DE NEGÓCIO
# ==============================================================================

def criar_imagem_post(url_imagem_noticia, titulo_post, config_cliente):
    print(f"🎨 Criando imagem para: {config_cliente['name']} - {titulo_post[:30]}...")
    try:
        response_img = requests.get(url_imagem_noticia, stream=True, timeout=15); response_img.raise_for_status()
        imagem_noticia = Image.open(io.BytesIO(response_img.content)).convert("RGBA")
        response_logo = requests.get(config_cliente['logo_url'], stream=True, timeout=15); response_logo.raise_for_status()
        logo = Image.open(io.BytesIO(response_logo.content)).convert("RGBA")
        fonte_titulo = ImageFont.truetype("Anton-Regular.ttf", int(config_cliente.get('font_size_title', 50)))
        fonte_rodape = ImageFont.truetype("Anton-Regular.ttf", int(config_cliente.get('font_size_footer', 30)))
        imagem_final = Image.new('RGBA', (1080, 1080), (255, 255, 255, 255))
        draw = ImageDraw.Draw(imagem_final)
        imagem_noticia_resized = imagem_noticia.resize((980, 551))
        imagem_final.paste(imagem_noticia_resized, (50, 50))
        draw.rounded_rectangle([(40, 610), (1040, 1040)], radius=40, fill=config_cliente['bg_color_primary'])
        draw.rounded_rectangle([(50, 620), (1030, 1030)], radius=40, fill=config_cliente['bg_color_secondary'])
        logo.thumbnail((220, 220))
        imagem_final.paste(logo, ((1080 - logo.width) // 2, 620 - (logo.height // 2)), logo)
        linhas_texto = textwrap.wrap(titulo_post.upper(), width=40)
        draw.text((540, 800), "\n".join(linhas_texto), font=fonte_titulo, fill=config_cliente['text_color'], anchor="mm", align="center")
        draw.text((540, 980), config_cliente['footer_text'], font=fonte_rodape, fill=config_cliente['text_color'], anchor="ms", align="center")
        buffer_saida = io.BytesIO()
        imagem_final.convert('RGB').save(buffer_saida, format='JPEG', quality=95)
        return buffer_saida.getvalue()
    except Exception as e:
        print(f"❌ Erro na criação da imagem: {e}")
        return None

def upload_para_cloudinary(bytes_imagem, nome_arquivo, config_cliente):
    creds = {'cloud_name': config_cliente.get('cloudinary_cloud_name'),'api_key': config_cliente.get('cloudinary_api_key'),'api_secret': config_cliente.get('cloudinary_api_secret')}
    if not all(creds.values()): return None, "Credenciais do Cloudinary incompletas."
    try:
        cloudinary.config(**creds)
        response = cloudinary.uploader.upload(io.BytesIO(bytes_imagem), public_id=nome_arquivo, folder=f"automacao_posts/{config_cliente['id']}", overwrite=True)
        return response.get('secure_url'), "Upload para Cloudinary OK."
    except Exception as e: return None, f"Erro no upload para Cloudinary: {e}"

def publicar_no_instagram(url_imagem, legenda, config_cliente):
    token, insta_id = config_cliente.get('meta_api_token'), config_cliente.get('instagram_id')
    if not all([token, insta_id]): return False, "Credenciais do Instagram incompletas."
    try:
        url_container = f"https://graph.facebook.com/v19.0/{insta_id}/media"
        params_container = {'image_url': url_imagem, 'caption': legenda, 'access_token': token}
        r_container = requests.post(url_container, params=params_container, timeout=20); r_container.raise_for_status()
        id_criacao = r_container.json()['id']
        url_publicacao = f"https://graph.facebook.com/v19.0/{insta_id}/media_publish"
        params_publicacao = {'creation_id': id_criacao, 'access_token': token}
        requests.post(url_publicacao, params=params_publicacao, timeout=20).raise_for_status()
        return True, "Publicado no Instagram com sucesso!"
    except Exception as e: return False, f"Falha no Instagram: {e}"

def publicar_no_facebook(url_imagem, legenda, config_cliente):
    token, page_id = config_cliente.get('meta_api_token'), config_cliente.get('facebook_page_id')
    if not all([token, page_id]): return False, "Credenciais do Facebook incompletas."
    try:
        url_post_foto = f"https://graph.facebook.com/v19.0/{page_id}/photos"
        params = {'url': url_imagem, 'message': legenda, 'access_token': token}
        requests.post(url_post_foto, params=params, timeout=20).raise_for_status()
        return True, "Publicado no Facebook com sucesso!"
    except Exception as e: return False, f"Falha no Facebook: {e}"

def extrair_dados_noticia(url):
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        titulo = (soup.find('meta', property='og:title') or soup.find('h1')).get('content', soup.find('h1').text)
        resumo = (soup.find('meta', property='og:description') or soup.find('p')).get('content', soup.find('p').text)
        imagem = (soup.find('meta', property='og:image')).get('content')
        return {"titulo": titulo.strip(), "resumo": resumo.strip(), "url_imagem": imagem}
    except Exception as e: return None

# CRUD Routes
@app.route('/')
def admin_panel():
    db = get_db()
    clients = db.execute('SELECT * FROM clients ORDER BY name').fetchall()
    return render_template('admin.html', clients=clients)

@app.route('/client/add', methods=['POST'])
def add_client():
    try:
        db = get_db()
        db.execute("""
            INSERT INTO clients (name, logo_url, wp_url, wp_user, wp_password, rss_url, json_url, 
            bg_color_primary, bg_color_secondary, text_color, font_size_title, font_size_footer, 
            footer_text, hashtags, caption_template, meta_api_token, instagram_id, facebook_page_id,
            cloudinary_cloud_name, cloudinary_api_key, cloudinary_api_secret) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (request.form['name'], request.form['logo_url'], request.form['wp_url'], request.form['wp_user'], 
            request.form['wp_password'], request.form['rss_url'], request.form['json_url'], request.form['bg_color_primary'],
            request.form['bg_color_secondary'], request.form['text_color'], request.form['font_size_title'], 
            request.form['font_size_footer'], request.form['footer_text'], request.form['hashtags'], 
            request.form['caption_template'], request.form['meta_api_token'], request.form['instagram_id'], 
            request.form['facebook_page_id'], request.form['cloudinary_cloud_name'], 
            request.form['cloudinary_api_key'], request.form['cloudinary_api_secret']))
        db.commit()
        flash('Cliente adicionado com sucesso!', 'success')
    except Exception as e: flash(f'Erro ao adicionar cliente: {e}', 'danger')
    return redirect(url_for('admin_panel'))

@app.route('/client/edit/<int:client_id>', methods=['GET', 'POST'])
def edit_client(client_id):
    db = get_db()
    if request.method == 'POST':
        try:
            query = "UPDATE clients SET name=?, logo_url=?, wp_url=?, rss_url=?, json_url=?, bg_color_primary=?, bg_color_secondary=?, text_color=?, font_size_title=?, font_size_footer=?, footer_text=?, hashtags=?, caption_template=?, instagram_id=?, facebook_page_id=?, cloudinary_cloud_name=?, cloudinary_api_key=? "
            params = [request.form[k] for k in ['name', 'logo_url', 'wp_url', 'rss_url', 'json_url', 'bg_color_primary', 'bg_color_secondary', 'text_color', 'font_size_title', 'font_size_footer', 'footer_text', 'hashtags', 'caption_template', 'instagram_id', 'facebook_page_id', 'cloudinary_cloud_name', 'cloudinary_api_key']]
            if request.form.get('wp_password'): query += ", wp_password = ?"; params.append(request.form['wp_password'])
            if request.form.get('meta_api_token'): query += ", meta_api_token = ?"; params.append(request.form['meta_api_token'])
            if request.form.get('cloudinary_api_secret'): query += ", cloudinary_api_secret = ?"; params.append(request.form['cloudinary_api_secret'])
            query += " WHERE id = ?"; params.append(client_id)
            db.execute(query, tuple(params)); db.commit()
            flash('Cliente atualizado com sucesso!', 'success')
            return redirect(url_for('admin_panel'))
        except Exception as e: flash(f'Erro ao atualizar cliente: {e}', 'danger')
    client = db.execute('SELECT * FROM clients WHERE id = ?', (client_id,)).fetchone()
    if not client: flash('Cliente não encontrado.', 'danger'); return redirect(url_for('admin_panel'))
    return render_template('edit_client.html', client=client)

@app.route('/client/delete/<int:client_id>', methods=['POST'])
def delete_client(client_id):
    try:
        db = get_db(); db.execute('DELETE FROM clients WHERE id = ?', (client_id,)); db.commit()
        flash('Cliente removido com sucesso!', 'success')
    except Exception as e: flash(f'Erro ao remover cliente: {e}', 'danger')
def get_article_details(url):
    """Busca os detalhes de um artigo (título, resumo, imagem) a partir de uma URL."""
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        title = soup.find('meta', property='og:title')
        excerpt = soup.find('meta', property='og:description')
        image_url = soup.find('meta', property='og:image')

        return {
            "title": title['content'] if title else soup.title.string,
            "excerpt": excerpt['content'] if excerpt else "Resumo não encontrado.",
            "image_url": image_url['content'] if image_url else None
        }
    except Exception as e:
        print(f"❌ [ERRO] Falha ao extrair detalhes da URL {url}: {e}")
        return None

def fetch_rss_feed(feed_url):
    """Busca e analisa um feed RSS, retornando as notícias."""
    print(f"📰 Buscando feed RSS de: {feed_url}")
    try:
        # Usa o parser lxml-xml para maior confiabilidade com feeds
        feed = feedparser.parse(feed_url)
        if feed.bozo:
            # Bozo flag é 1 (True) se o feed estiver malformado
            raise Exception(f"Feed malformado - {feed.bozo_exception}")
        return feed.entries
    except Exception as e:
        print(f"❌ [ERRO] Não foi possível buscar ou analisar o feed RSS {feed_url}: {e}")
        return []

@app.route('/run_automation', methods=['POST'])
def run_automation():
    db = get_db()
    clients = db.execute('SELECT * FROM clients WHERE rss_url IS NOT NULL AND rss_url != ""').fetchall()
    if not clients:
        flash("Nenhum cliente com Feed RSS configurado foi encontrado.", "warning")
        return redirect(url_for('admin_panel'))
    
    total_posts_made = 0
    for client in clients:
        print(f"Verificando feed para {client['name']}...")
        try:
            feed = feedparser.parse(client['rss_url'])
            if feed.bozo: raise Exception(f"Feed RSS mal formatado: {feed.bozo_exception}")
            last_guid = client['last_posted_guid']
            guids = [entry.get('id', entry.link) for entry in feed.entries]
            if last_guid in guids: new_entries = feed.entries[:guids.index(last_guid)]
            else: new_entries = feed.entries[:5] # Limite para primeira execução ou feed antigo
            
            if not new_entries: continue
            new_entries.reverse() # Publicar do mais antigo para o mais novo
            
            for entry in new_entries[:10]: # Limite de 10 por execução para segurança
                guid = entry.get('id', entry.link)
                image_url = find_image_in_entry(entry)
                if not image_url: continue
                
                imagem_bytes = criar_imagem_post(image_url, entry.title, client)
                if not imagem_bytes: continue
                
                public_url, _ = upload_para_cloudinary(imagem_bytes, f"post_rss_{client['id']}_{secrets.token_hex(4)}", client)
                if not public_url: continue
                
                summary = BeautifulSoup(entry.summary, 'html.parser').get_text(separator=' ', strip=True)
                resumo_curto = textwrap.shorten(summary, width=200, placeholder="...")
                caption_template = client.get('caption_template') or "{title}\n\n{excerpt}\n\n{hashtags}"
                legenda_final = caption_template.format(title=entry.title, excerpt=resumo_curto, hashtags=client.get('hashtags', ''))
                
                publicar_no_instagram(public_url, legenda_final, client)
                publicar_no_facebook(public_url, legenda_final, client)
                
                db.execute("UPDATE clients SET last_posted_guid = ? WHERE id = ?", (guid, client['id'])); db.commit()
                total_posts_made += 1
        except Exception as e:
            flash(f"Erro ao processar o feed para '{client['name']}': {e}", "danger")
    
    if total_posts_made == 0: flash("Verificação concluída. Nenhuma novidade para publicar.", "info")
    else: flash(f"Automação concluída! Total de {total_posts_made} posts publicados.", "success")
    return redirect(url_for('admin_panel'))

# ==============================================================================
# BLOCO 4: INICIALIZAÇÃO
# ==============================================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)


>>>>>>> 48d2c29e23d2649983469009aa790868af8841ab

