# Robô do MEUS LEILÕES: lê a agenda do site, baixa os banners e acha o catálogo de cada leilão.
import re, json, os, sys, time, datetime
from io import BytesIO
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
from PIL import Image

BASE = "https://programaleiloes.com"
H = {"User-Agent": "Mozilla/5.0 (compatible; MeusLeiloesBot/1.0)"}
MESES = {m: i + 1 for i, m in enumerate("JAN FEV MAR ABR MAI JUN JUL AGO SET OUT NOV DEZ".split())}
CATS = {"Nelore": "/agenda/categoria/4-nelore", "Leite": "/agenda/categoria/2-leite",
        "Gado de Corte": "/agenda/categoria/3-gado-de-corte", "Equinos": "/agenda/categoria/7-equinos",
        "Maquinários": "/agenda/categoria/9-maquinarios"}
RACAS = ["Puro Sangue Árabe", "Nelore Pintado", "Gado de Corte", "Quarto de Milha", "Gir Leiteiro", "Raças Europeias",
         "Nelore PO", "Girolando", "Holandês", "Tabapuã", "Crioulo", "Longhorn", "Senepol", "Brangus", "Angus",
         "Muares", "Nelore", "Sindi", "OUTROS", "Gir"]
agora = datetime.datetime.now(ZoneInfo("America/Sao_Paulo"))


def get(url):
    r = requests.get(url, headers=H, timeout=40)
    r.raise_for_status()
    return r.text


def links_leiloes(html):
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for a in soup.find_all("a", href=True):
        m = re.search(r"/agenda/leilao/(\d+-[^/?#]+)", a["href"])
        if m:
            txt = " ".join(a.get_text(" ").split())
            if m.group(1) not in out or len(txt) > len(out[m.group(1)]):
                out[m.group(1)] = txt
    return out


def limpar_local(resto, titulo):
    if titulo and resto.lower().startswith(titulo.lower()):
        resto = resto[len(titulo):].strip(" -.;")
    else:
        m = re.search(r"((?:[^\s-]+\s){0,4}[^\s-]+)\s-\s([A-Z]{2})$", resto)
        resto = (m.group(1) + " - " + m.group(2)) if m else resto
    mudou = True
    while mudou:
        mudou = False
        for r in RACAS:
            if resto.lower().startswith(r.lower() + " "):
                resto = resto[len(r):].strip(); mudou = True
    return resto


def pagina_leilao(slug):
    html = get(f"{BASE}/agenda/leilao/{slug}")
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    titulo = " ".join(h1.get_text(" ").split()) if h1 else ""
    banner = ""
    og = soup.find("meta", property="og:image")
    if og and og.get("content") and "programa-leiloes.jpg" not in og["content"]:
        banner = og["content"]
    if not banner:
        for im in soup.find_all("img", src=True):
            if "/files/" in im["src"] and "/banners/" not in im["src"]:
                banner = im["src"]; break
    if banner.startswith("/"):
        banner = BASE + banner
    catalogo = ""
    for a in soup.find_all("a", href=True):
        m = re.search(r"/leilao/download/([^?#]*catalogo[^?#]*)", a["href"])
        if m:
            catalogo = m.group(1); break
    return titulo, banner, catalogo


def baixar_banner(url, destino):
    if os.path.exists(destino):
        return True
    try:
        r = requests.get(url, headers=H, timeout=40); r.raise_for_status()
        im = Image.open(BytesIO(r.content)).convert("RGB")
        im.thumbnail((560, 1000))
        im.save(destino, "JPEG", quality=80, optimize=True)
        return True
    except Exception as e:
        print("  banner falhou:", e); return False


def main():
    os.makedirs("banners", exist_ok=True)
    todos = links_leiloes(get(BASE + "/agenda"))
    print("Leilões encontrados na agenda:", len(todos))
    if not todos:
        print("ERRO: não achei nenhum leilão; mantendo os dados antigos."); sys.exit(1)
    categoria = {}
    for nome, caminho in CATS.items():
        try:
            for slug in links_leiloes(get(BASE + caminho)):
                categoria.setdefault(slug, nome)
        except Exception as e:
            print("categoria falhou", nome, e)
    L, usados = [], set()
    for slug, txt in todos.items():
        try:
            md = re.search(r"(\d{1,2})\s+(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)\b", txt)
            hora = re.search(r"Hor[áa]rio\s+(\d{1,2}:\d{2})", txt)
            if not md:
                print("sem data:", slug); continue
            dia, mes = int(md.group(1)), MESES[md.group(2)]
            ano = agora.year
            if datetime.date(ano, mes, dia) < agora.date() - datetime.timedelta(days=60):
                ano += 1
            resto = txt.split("Transmissão", 1)[1].strip() if "Transmissão" in txt else txt
            titulo, banner, catalogo = pagina_leilao(slug)
            time.sleep(0.4)
            if not titulo:
                titulo = re.sub(r"^\d+-", "", slug).replace("-", " ").title()
            local = limpar_local(resto, titulo)
            arq = ""
            if banner:
                destino = f"banners/{slug.split('-')[0]}.jpg"
                if baixar_banner(banner, destino):
                    arq = destino; usados.add(destino)
            L.append([f"{ano}-{mes:02d}-{dia:02d}", hora.group(1) if hora else "", titulo,
                      categoria.get(slug, "Outros"), local, slug, catalogo, arq])
        except Exception as e:
            print("falhou", slug, e)
    if not L:
        print("ERRO: nenhum leilão processado; mantendo os dados antigos."); sys.exit(1)
    L.sort(key=lambda x: (x[0], x[1]))
    for f in os.listdir("banners"):  # apaga banners de leilões que já saíram da agenda
        if "banners/" + f not in usados:
            os.remove("banners/" + f)
    with open("data.json", "w", encoding="utf8") as f:
        json.dump({"atualizado": agora.strftime("%d/%m/%Y %H:%M"), "L": L}, f, ensure_ascii=False, indent=1)
    print("OK:", len(L), "leilões,", sum(1 for x in L if x[7]), "com banner,", sum(1 for x in L if x[6]), "com catálogo")


main()
