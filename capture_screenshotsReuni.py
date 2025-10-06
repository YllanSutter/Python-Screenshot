#!/usr/bin/env python3
"""capture_screenshotsReuni.py

Version propre et autonome : interface en customtkinter pour lancer
`capture_screenshots_small.py` et `capture_screenshotsFull.py` (scripts
externes). Gère l'affichage de logs, la vérification des fichiers attendus
et la relance des captures manquantes.

Exigences:
- Python 3
- package customtkinter (pip install customtkinter)
- Pillow (pip install pillow) pour validation d'images optionnelle
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import threading
import os
import sys
import time
import re
from typing import List, Tuple

try:
    import customtkinter as ctk
except Exception:
    raise SystemExit("Le package 'customtkinter' est requis. Installez-le avec 'pip install customtkinter'.")

from PIL import Image
import io

# Selenium / screenshot utilities (utilisées par les fonctions locales)
try:
    from Screenshot import Screenshot
except Exception:
    Screenshot = None

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import NoSuchElementException, TimeoutException
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except Exception:
    webdriver = None
    Options = None


# CSS par défaut plus complet (extrait de l'ancien script)
CSS_DEFAULT = """
transition: all 0s!important;
html, body {
    overflow-x: hidden !important;
    width: 100% !important;
    max-width: 100% !important;
}

#wrappersite {
    overflow: hidden!important;
}

.sectionsbloc img,body .vegas-container,#content img {
    transform: initial!important;
}

#tarteaucitronAlertSmall, #tarteaucitronAlertBig,.fixedParent,.fixed-header,.animationDirection::before,.to-top,#popup,#banner,#ckbp_popup,#ckbp_banner,
#loader-wrapper,.loader,#ckbp_popup,#ckbp_banner,#AVcontentBox,#AVoverlay,#event_animation_container {
    display: none!important;
}

.fixe-bg,.baseBefore::before,#reassurances,#prestations {
    background-attachment: initial!important;
}

.animClass, .animClassChild, .animClassToogle, .animClassChildToogle {
    overflow: inherit!important;
}

.animClass, .animClassChild>*, .animClassToogle, .animClassChildToogle>* {
    transform: translate(0,0)!important;
    opacity: 1!important;
}
"""


# --- UI globals (référencés depuis handlers) ---
url_entry = None
status_text = None
script1_var = None
script2_var = None
headless_var = None
time_entry = None
css_entry = None
relance_btn = None


def append_status(text: str):
    """Ajoute du texte dans la zone de statut (thread-safe)."""
    def _append():
        try:
            status_text.insert("end", text + "\n")
            status_text.see("end")
        except Exception:
            print(text)

    try:
        status_text.after(0, _append)
    except Exception:
        print(text)


def run_script_for_url(script_path: str, url: str, headless: bool, time_value: int) -> Tuple[bool, str]:
    """Lance un script externe et retourne (succès, log).
    Utilise sys.executable pour appeler l'interpréteur courant.
    """
    cmd = [sys.executable, script_path, url]
    if headless:
        cmd.append("--headless")
    cmd.extend(["--time", str(time_value)])
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        out = f"[{os.path.basename(script_path)}] {url} -> exit {res.returncode}"
        if res.stdout:
            out += "\n" + res.stdout.strip()
        if res.stderr:
            out += "\nERR: " + res.stderr.strip()
        return (res.returncode == 0), out
    except Exception as e:
        return False, f"Erreur lancement {script_path} pour {url}: {e}"


def get_filename_from_url(url: str) -> str:
    u = re.sub(r"^https?://", "", url)
    u = re.sub(r"^www\.", "", u)
    domain = u.split('/')[0]
    return re.sub(r"\..*$", "", domain)


def capture_screenshot_small(url: str, headless: bool, time_value: int, css: str) -> Tuple[bool, str]:
    """Capture version mobile (similaire à capture_screenshot_small dans l'ancien script)."""
    if webdriver is None:
        return False, "selenium non disponible - installez selenium et chromedriver"
    mobile_emulation = {
        "deviceMetrics": {"width": 360, "height": 640, "pixelRatio": 3.0},
        "userAgent": "Mozilla/5.0 (Linux; Android 4.2.1; en-us; Nexus 5 Build/JOP40D) AppleWebKit/535.19 (KHTML, like Gecko) Chrome/18.0.1025.166 Mobile Safari/535.19"
    }
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
    try:
        chrome_options.add_experimental_option("mobileEmulation", mobile_emulation)
    except Exception:
        pass
    driver = webdriver.Chrome(options=chrome_options)
    filename = get_filename_from_url(url)
    try:
        driver.get(url + "/?force")
        try:
            driver.execute_script('var style = document.createElement("style"); style.type = "text/css"; style.innerHTML = arguments[0]; document.head.appendChild(style);', css or CSS_DEFAULT)
        except Exception:
            pass
        time.sleep(time_value)
        try:
            WebDriverWait(driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
        except Exception:
            pass
        driver.set_window_size(360, 640)
        png_data = driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(png_data))
        rgb_img = img.convert('RGB')
        jpg_filename = f"{filename}-mobile.jpg"
        rgb_img.save(jpg_filename, 'JPEG', quality=85)
        return True, f"OK: Capture mobile sauvegardée : {jpg_filename}"
    except Exception as e:
        return False, f"ECHEC mobile {url} : {e}"
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def capture_screenshot_full(url: str, headless: bool, time_value: int, css: str) -> Tuple[bool, str]:
    """Capture full-page en scrollant et en assemblant des captures viewport par viewport.
    Algorithm:
    - ouvrir la page, injecter le CSS
    - scroller jusqu'en bas (répété) pour forcer le chargement lazy
    - remonter en haut
    - capturer par étapes (viewport) en sauvegardant des parts PNG nommées de façon unique
    - assembler verticalement les parts en une image finale JPG
    - supprimer les parts temporaires
    """
    if webdriver is None:
        return False, "selenium non disponible - installez selenium et chromedriver"
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(options=chrome_options)
    filename = get_filename_from_url(url)
    log_prefix = f"[FULL][{url}] "
    prefix = f"{filename}_full_{int(time.time())}"
    try:
        driver.get(url + "/?force")
        try:
            driver.execute_script('var style = document.createElement("style"); style.type = "text/css"; style.innerHTML = arguments[0]; document.head.appendChild(style);', css or CSS_DEFAULT)
        except Exception:
            pass

        # Forcer la taille du viewport demandée
        try:
            driver.set_window_size(1920, 1080)
        except Exception:
            pass

        # Scroll to bottom repeatedly until page height stabilizes (load lazy content)
        max_wait = 15
        waited = 0.0
        stable_count = 0
        last_h = -1
        while waited < max_wait:
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                pass
            time.sleep(0.5)
            try:
                h = driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);")
            except Exception:
                h = last_h
            if h == last_h:
                stable_count += 1
            else:
                stable_count = 0
            last_h = h
            if stable_count >= 3:
                break
            waited += 0.5

        # Remonter en haut avant de capturer
        try:
            driver.execute_script("window.scrollTo(0,0);")
        except Exception:
            pass
        time.sleep(0.5)

        # Déterminer viewport et hauteur totale
        try:
            viewport_h = int(driver.execute_script("return window.innerHeight"))
        except Exception:
            viewport_h = 1080
        try:
            total_h = int(driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"))
        except Exception:
            total_h = viewport_h

        # Captures étapes
        step = max(viewport_h - 80, int(viewport_h * 0.8))
        parts = []
        y = 0
        idx = 0
        while y < total_h:
            try:
                driver.execute_script(f"window.scrollTo(0, {y});")
            except Exception:
                pass
            time.sleep(0.35 + (time_value * 0.1))
            try:
                png = driver.get_screenshot_as_png()
            except Exception as e:
                return False, log_prefix + f"Erreur lors de la capture partielle: {e}"
            part_name = f"{prefix}_part_{idx}.png"
            try:
                with open(part_name, 'wb') as f:
                    f.write(png)
            except Exception:
                pass
            parts.append((y, part_name))
            idx += 1
            y += step

        # Assemblage vertical
        try:
            images = [Image.open(p) for _, p in parts]
            widths = [im.width for im in images]
            total_width = max(widths) if widths else 1920
            final = Image.new('RGB', (total_width, total_h), (255, 255, 255))
            for (ypos, p), im in zip(parts, images):
                try:
                    final.paste(im.convert('RGB'), (0, int(ypos)))
                except Exception:
                    # fallback: paste at current cumulative height
                    final.paste(im.convert('RGB'), (0, 0))
            jpg_filename = f"{filename}.jpg"
            final.save(jpg_filename, 'JPEG', quality=85)
        except Exception as e:
            return False, log_prefix + f"ECHEC assemblage: {e}"

        # Cleanup parts
        for _, p in parts:
            try:
                os.remove(p)
            except Exception:
                pass

        return True, log_prefix + f"OK : Capture full sauvegardée : {jpg_filename}"
    except Exception as e:
        return False, log_prefix + f"ECHEC full {url} : {e}"
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def get_expected_filenames_for_url(url: str, want_mobile: bool, want_full: bool) -> List[str]:
    """Calcule des noms attendus simples à partir du domaine de l'URL.
    Ex: 'https://www.example.com/...' -> base 'example' -> 'example-mobile.jpg' & 'example.jpg'
    """
    u = re.sub(r"^https?://", "", url)
    u = re.sub(r"^www\.", "", u)
    domain = u.split('/')[0]
    base = re.sub(r"\..*$", "", domain)
    out = []
    if want_mobile:
        out.append(f"{base}-mobile.jpg")
    if want_full:
        out.append(f"{base}.jpg")
    return out


def verify_image_exists_and_valid(path: str) -> bool:
    """Vérifie que le fichier existe et qu'il est ouvrable en tant qu'image."""
    if not os.path.exists(path):
        return False
    try:
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


def execute_scripts(urls: List[str], script1_checked: bool, script2_checked: bool, headless: bool, time_value: int, css: str) -> List[Tuple[str, str, str]]:
    """Lance les captures locales en parallèle et retourne la liste des manquants (url, type, filename)."""
    tasks = []
    expected = []  # tuples (url, type, filename)
    max_workers = min(4, max(1, len(urls)))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for url in urls:
            u = url.strip()
            if not u:
                continue
            if script1_checked:
                tasks.append(ex.submit(capture_screenshot_small, u, headless, time_value, css))
                for f in get_expected_filenames_for_url(u, want_mobile=True, want_full=False):
                    expected.append((u, 'mobile', f))
            if script2_checked:
                tasks.append(ex.submit(capture_screenshot_full, u, headless, time_value, css))
                for f in get_expected_filenames_for_url(u, want_mobile=False, want_full=True):
                    expected.append((u, 'full', f))

        # récupérer les résultats/logs
        for fut in as_completed(tasks):
            try:
                ok, log = fut.result()
                append_status(log)
            except Exception as e:
                append_status(f"Erreur thread: {e}")

    # vérifier les fichiers attendus
    manquants = []
    for url, typ, fname in expected:
        if not verify_image_exists_and_valid(fname):
            manquants.append((url, typ, fname))
    return manquants


def on_execute_clicked():
    global relance_btn
    txt = url_entry.get("0.0", "end").strip()
    urls = [l for l in txt.splitlines() if l.strip()]
    if not urls:
        append_status("Aucune URL fournie.")
        return
    s1 = script1_var.get()
    s2 = script2_var.get()
    head = headless_var.get()
    try:
        t = int(time_entry.get())
    except Exception:
        t = 3
    css = css_entry.get("0.0", "end").strip()

    append_status(f"Démarrage: mobile={s1} full={s2} headless={head} time={t}s")

    def _bg():
        manquants = execute_scripts(urls, s1, s2, head, t, css)
        if manquants:
            append_status("Fichiers manquants après exécution:")
            for u, typ, f in manquants:
                append_status(f" - {typ} : {u} => {f}")
            # activer le bouton relance et mémoriser
            try:
                relance_btn.configure(state="normal")
                relance_btn.manquants = manquants
            except Exception:
                pass
        else:
            append_status("Toutes les captures attendues ont été créées.")

    threading.Thread(target=_bg, daemon=True).start()


def on_relance_clicked():
    manquants = getattr(relance_btn, "manquants", None)
    if not manquants:
        append_status("Aucun manquant à relancer.")
        return
    try:
        t = int(time_entry.get())
    except Exception:
        t = 3
    head = headless_var.get()
    css = css_entry.get("0.0", "end").strip()

    def _bg():
        append_status("Relance des manquants...")
        for url, typ, fname in manquants:
            if typ == 'mobile':
                ok, log = capture_screenshot_small(url, head, t, css)
            else:
                ok, log = capture_screenshot_full(url, head, t, css)
            append_status(log)
            if ok and verify_image_exists_and_valid(fname):
                append_status(f"OK: {fname} créé pour {url}")
            else:
                append_status(f"Toujours manquant: {fname} pour {url}")
        append_status("Relance terminée.")

    threading.Thread(target=_bg, daemon=True).start()


def build_ui():
    global url_entry, status_text, script1_var, script2_var, headless_var, time_entry, css_entry, relance_btn
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("Capture de sites web - Screenshots Automatisés")
    root.geometry("900x700")

    header = ctk.CTkLabel(root, text="Outil de capture de sites web", font=("Segoe UI", 20, "bold"))
    header.pack(pady=(12, 6))

    frame_urls = ctk.CTkFrame(root)
    frame_urls.pack(fill="x", padx=12, pady=(0, 8))
    lbl = ctk.CTkLabel(frame_urls, text="URLs à capturer (une par ligne):")
    lbl.pack(anchor="w")
    url_entry = ctk.CTkTextbox(frame_urls, height=140)
    url_entry.pack(fill="x", pady=(6, 4))

    frame_opts = ctk.CTkFrame(root)
    frame_opts.pack(fill="x", padx=12, pady=(0, 8))
    script1_var = ctk.BooleanVar(value=True)
    script2_var = ctk.BooleanVar(value=True)
    headless_var = ctk.BooleanVar(value=True)
    cb1 = ctk.CTkCheckBox(frame_opts, text="Version mobile", variable=script1_var)
    cb2 = ctk.CTkCheckBox(frame_opts, text="Version Full", variable=script2_var)
    cb3 = ctk.CTkCheckBox(frame_opts, text="Mode headless", variable=headless_var)
    cb1.grid(row=0, column=0, padx=6, pady=6, sticky="w")
    cb2.grid(row=0, column=1, padx=6, pady=6, sticky="w")
    cb3.grid(row=0, column=2, padx=6, pady=6, sticky="w")
    time_entry = ctk.CTkEntry(frame_opts, width=70)
    time_entry.insert(0, "3")
    lblt = ctk.CTkLabel(frame_opts, text="Temps (s):")
    lblt.grid(row=0, column=3, padx=(12, 4))
    time_entry.grid(row=0, column=4, padx=(0, 6))

    btn_run = ctk.CTkButton(root, text="Exécuter les captures", command=on_execute_clicked)
    btn_run.pack(pady=(4, 8))

    status_text = ctk.CTkTextbox(root, height=200)
    status_text.pack(fill="both", expand=True, padx=12, pady=(6, 8))

    frame_css = ctk.CTkFrame(root)
    frame_css.pack(fill="x", padx=12, pady=(0, 8))
    css_label = ctk.CTkLabel(frame_css, text="CSS à injecter (modifiable):")
    css_label.pack(anchor="w")
    css_entry = ctk.CTkTextbox(frame_css, height=120)
    # Pré-remplir l'éditeur avec le bloc CSS complet utilisé par l'assemblage full
    css_entry.insert("0.0", CSS_DEFAULT)
    css_entry.pack(fill="x", pady=(6, 4))

    relance_btn = ctk.CTkButton(root, text="Relancer les captures manquantes", command=on_relance_clicked, state="disabled")
    relance_btn.pack(pady=(6, 12))

    root.mainloop()


if __name__ == '__main__':
    build_ui()

