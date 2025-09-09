# ==============================================================================
# BLOCO 1: IMPORTAÇÕES E CONFIGURAÇÃO
# ==============================================================================
import os
import requests
import time
import textwrap
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from base64 import b64encode
from PIL import Image, ImageDraw, ImageFont

# Carrega variáveis do .env
load_dotenv()
app = Flask(__name__)

print("🚀 INICIANDO APLICAÇÃO DE AUTOMAÇÃO v3.2 (Boca no Trombone)")

# --- Configs do WordPress ---
WP_URL = os.getenv('WP_URL')
WP_USER = os.getenv('WP_USER')
WP_PASSWORD = os.getenv('WP_PASSWORD')
HEADERS_WP = {}
if all([WP_URL, WP_USER, WP_PASSWORD]):
    credentials = f"{WP_USER}:{WP_PASSWORD}"
    token_wp = b64encode(credentials.encode())
    HEADERS_WP = {'Authorization': f'Basic {token_wp.decode("utf-8")}'}
    print("✅ [CONFIG] WordPress carregado.")
else:
    print("❌ [ERRO] Faltando variáveis do WordPress.")

# --- Configs do Boca no Trombone ---
BOCA_META_API_TOKEN = os.getenv('META_API_TOKEN')
BOCA_INSTAGRAM_ID = os.getenv('INSTAGRAM_ID')
BOCA_FACEBOOK_PAGE_ID = os.getenv('FACEBOOK_PAGE_ID')
GRAPH_API_VERSION = 'v19.0'

print("-" * 30)
print("DIAGNÓSTICO DAS VARIÁVEIS:")
print(f"  - Instagram ID: {'OK' if BOCA_INSTAGRAM_ID else 'FALHANDO'}")
print(f"  - Facebook Page ID: {'OK' if BOCA_FACEBOOK_PAGE_ID else 'FALHANDO'}")
print(f"  - Meta API Token: {'OK' if BOCA_META_API_TOKEN else 'FALHANDO'}")
print("-" * 30)

# ==============================================================================
# BLOCO 2: FUNÇÕES
# ==============================================================================

def criar_imagem_post(titulo_post, url_imagem_destaque):
    """Cria imagem quadrada com título centralizado na faixa cinza"""
    try:
        print("🎨 Criando imagem do post...")

        # Baixa imagem de destaque
        response = requests.get(url_imagem_destaque, timeout=30)
        response.raise_for_status()
        with open("temp.jpg", "wb") as f:
            f.write(response.content)

        img = Image.open("temp.jpg").convert("RGB")
        img = img.resize((1080, 1080))

        draw = ImageDraw.Draw(img)

        # faixa cinza
        draw.rectangle([(0, 650), (1080, 950)], fill=(40, 40, 40, 200))

        # fonte
        fonte_titulo = ImageFont.truetype("arial.ttf", 48)

        # quebra o título
        linhas_texto = textwrap.wrap(titulo_post.upper(), width=32)
        texto = "\n".join(linhas_texto)

        # calcula altura do texto
        bbox = draw.multiline_textbbox((0, 0), texto, font=fonte_titulo, align="center")
        altura_texto = bbox[3] - bbox[1]

        # centraliza verticalmente na faixa cinza (650–950)
        y_centro = 800
        y_texto = y_centro - altura_texto // 2

        # escreve
        draw.multiline_text(
            (540, y_texto),
            texto,
            font=fonte_titulo,
            fill="white",
            anchor="mm",
            align="center"
        )

        img.save("output_post.jpg", "JPEG")
        print("✅ Imagem criada com sucesso!")
        return "output_post.jpg"
    except Exception as e:
        print(f"❌ ERRO ao criar imagem: {e}")
        return None


def upload_para_wordpress(caminho_arquivo, nome_arquivo):
    print(f"⬆️ Upload para WordPress...")
    try:
        with open(caminho_arquivo, 'rb') as img_file:
            url_wp_media = f"{WP_URL}/wp-json/wp/v2/media"
            headers_upload = HEADERS_WP.copy()
            headers_upload['Content-Disposition'] = f'attachment; filename={nome_arquivo}'
            headers_upload['Content-Type'] = 'image/jpeg'
            response_wp = requests.post(url_wp_media, headers=headers_upload, data=img_file)
            response_wp.raise_for_status()
            link_imagem_publica = response_wp.json()['source_url']
            print(f"✅ Imagem salva no WordPress: {link_imagem_publica}")
            return link_imagem_publica
    except Exception as e:
        print(f"❌ ERRO no upload WordPress: {e}")
        return None


def publicar_reel_no_instagram(url_imagem, legenda):
    print("📤 Publicando no Instagram...")
    if not all([BOCA_META_API_TOKEN, BOCA_INSTAGRAM_ID]):
        print("⚠️ PULADO: Variáveis faltando.")
        return False
    try:
        url_container = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{BOCA_INSTAGRAM_ID}/media"
        params_container = {
            'image_url': url_imagem,
            'caption': legenda,
            'access_token': BOCA_META_API_TOKEN
        }
        r_container = requests.post(url_container, params=params_container, timeout=30)
        r_container.raise_for_status()
        id_criacao = r_container.json()['id']

        url_publicacao = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{BOCA_INSTAGRAM_ID}/media_publish"
        params_publicacao = {'creation_id': id_criacao, 'access_token': BOCA_META_API_TOKEN}
        r_publish = requests.post(url_publicacao, params=params_publicacao, timeout=30)
        r_publish.raise_for_status()

        print("✅ Post publicado no Instagram!")
        return True
    except Exception as e:
        print(f"❌ ERRO no Instagram: {e}")
        return False


def publicar_no_facebook(url_imagem, legenda):
    print("📤 Publicando no Facebook...")
    if not all([BOCA_META_API_TOKEN, BOCA_FACEBOOK_PAGE_ID]):
        print("⚠️ PULADO: Variáveis faltando.")
        return False
    try:
        url_post = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{BOCA_FACEBOOK_PAGE_ID}/photos"
        params = {'url': url_imagem, 'caption': legenda, 'access_token': BOCA_META_API_TOKEN}
        r = requests.post(url_post, params=params, timeout=90)
        r.raise_for_status()
        print("✅ Imagem publicada no Facebook!")
        return True
    except Exception as e:
        print(f"❌ ERRO no Facebook: {e}")
        return False


# ==============================================================================
# BLOCO 3: WEBHOOK
# ==============================================================================
@app.route('/webhook-boca', methods=['POST'])
def webhook_boca():
    print("\n" + "="*50)
    print("🔔 Webhook recebido!")

    try:
        dados = request.json
        post_id = dados.get('post_id')
        if not post_id:
            raise ValueError("Webhook não enviou 'post_id'.")

        url_api_post = f"{WP_URL}/wp-json/wp/v2/posts/{post_id}"
        response_post = requests.get(url_api_post, headers=HEADERS_WP, timeout=15)
        response_post.raise_for_status()
        post_data = response_post.json()

        titulo = BeautifulSoup(post_data.get('title', {}).get('rendered', ''), 'html.parser').get_text()
        resumo = BeautifulSoup(post_data.get('excerpt', {}).get('rendered', ''), 'html.parser').get_text(strip=True)
        id_img = post_data.get('featured_media')

        if not id_img:
            print("⚠️ Ignorado: sem imagem de destaque.")
            return jsonify({"status": "ignorado_sem_imagem"}), 200

        url_api_media = f"{WP_URL}/wp-json/wp/v2/media/{id_img}"
        response_media = requests.get(url_api_media, headers=HEADERS_WP, timeout=15)
        response_media.raise_for_status()
        url_img = response_media.json().get('source_url')

    except Exception as e:
        print(f"❌ ERRO no processamento webhook: {e}")
        return jsonify({"status": "erro_processamento_webhook"}), 500

    print("\n🚀 Iniciando publicação...")
    caminho_img = criar_imagem_post(titulo, url_img)
    if not caminho_img:
        return jsonify({"status": "erro_criar_imagem"}), 500

    nome_arquivo = f"boca_post_{post_id}.jpg"
    link_wp_img = upload_para_wordpress(caminho_img, nome_arquivo)
    if not link_wp_img:
        return jsonify({"status": "erro_upload_wp"}), 500

    legenda = f"{titulo}\n\n{resumo}\n\nLeia mais no nosso site!"
    sucesso_ig = publicar_reel_no_instagram(link_wp_img, legenda)
    sucesso_fb = publicar_no_facebook(link_wp_img, legenda)

    if sucesso_ig or sucesso_fb:
        print("🎉 Sucesso! Publicação concluída.")
        return jsonify({"status": "sucesso_publicacao"}), 200
    else:
        print("😭 Falha geral!")
        return jsonify({"status": "erro_publicacao"}), 500


# ==============================================================================
# BLOCO 4: INICIALIZAÇÃO
# ==============================================================================
@app.route('/')
def health_check():
    return "Serviço BOCA NO TROMBONE v3.2 está rodando!", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
