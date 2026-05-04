#!/usr/bin/env python3
"""capture_screenshots_v2.py

Capture full-page via Chrome DevTools Protocol (CDP).
Méthode : Page.captureScreenshot avec captureBeyondViewport=True (pas de scroll/assemblage).

Corrections v2 :
  - GSAP : kill tweens + clearProps transform/opacity avant capture
  - Images : chargement lazy complet sans casser les layouts flex/grid
  - CSS : ciblé (pas de display:block sur *div* qui brise tout)

Dépendances :
  pip install customtkinter pillow selenium
  chromedriver doit être dans le PATH
"""

import base64
import threading
import os
import re
import time
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

try:
    import customtkinter as ctk
except Exception:
    raise SystemExit("Le package 'customtkinter' est requis : pip install customtkinter")

from PIL import Image

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
except Exception:
    webdriver = None
    Options = None


# ---------------------------------------------------------------------------
# CSS injecté dans chaque page avant capture
# NOTE : on évite volontairement de toucher display/position/overflow sur *
#        car cela casse les layouts flex/grid et masque du contenu.
# ---------------------------------------------------------------------------
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

#header,#headerGrid
{
    width:100%;
}

.home #content :is(.blocthumb,.specialthumb,.tertiarythumb,.quaternarythumb,.gallery-item,.wp-block-image,.wp-block-image img)
{
    transform: initial!important;
    opacity:1!important;
}
#sections :is(.specialthumb,.blocthumb,.specialthumb img,.blocthumb img)
{
    background-attachment: inherit!important;
}
.gallery-item img
{
    opacity:1!important;
    transform: initial!important;
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

# ---------------------------------------------------------------------------
# JS : neutraliser fixed/sticky (évite les doublons en capture full-page)
# ---------------------------------------------------------------------------
_JS_NEUTRALIZE_FIXED = """
(function () {
    document.querySelectorAll('*').forEach(function (el) {
        var pos = window.getComputedStyle(el).position;
        if (pos === 'fixed' || pos === 'sticky') {
            el.style.setProperty('position', 'relative', 'important');
        }
    });
})();
"""


# ---------------------------------------------------------------------------
# JS : chargement complet des images lazy
# Gère : loading="lazy", data-src, data-srcset, picture/source, data-bg
# ---------------------------------------------------------------------------
_JS_LOAD_LAZY_IMAGES = """
(function () {
    var DATA_SRC_ATTRS = [
        'data-src', 'data-lazy-src', 'data-lazy', 'data-original',
        'data-image', 'data-url', 'data-img-src', 'data-full-src',
        'data-hi-res-src', 'data-retina-src', 'data-echo'
    ];

    function isPlaceholder(src) {
        if (!src) return true;
        if (src === window.location.href) return true;
        if (src.indexOf('data:') === 0) return true;
        if (src.indexOf('about:') === 0) return true;
        if (src.indexOf('blank') !== -1 && src.length < 60) return true;
        return false;
    }

    // 1. Native loading="lazy" → eager
    document.querySelectorAll('img[loading="lazy"]').forEach(function (img) {
        img.setAttribute('loading', 'eager');
    });

    // 2. data-src / data-lazy-src / etc.
    document.querySelectorAll('img').forEach(function (img) {
        var needSrc = isPlaceholder(img.getAttribute('src'));

        for (var i = 0; i < DATA_SRC_ATTRS.length; i++) {
            var val = img.getAttribute(DATA_SRC_ATTRS[i]);
            if (val && !isPlaceholder(val)) {
                img.setAttribute('src', val);
                needSrc = false;
                break;
            }
        }

        // data-srcset
        var dss = img.getAttribute('data-srcset');
        if (dss && !img.srcset) {
            img.setAttribute('srcset', dss);
        }

        // Si toujours pas de src : extraire depuis srcset
        if (needSrc && img.srcset) {
            var firstSrc = img.srcset.split(',')[0].trim().split(/\\s+/)[0];
            if (firstSrc && !isPlaceholder(firstSrc)) {
                img.setAttribute('src', firstSrc);
            }
        }
    });

    // 3. <picture><source data-srcset="…">
    document.querySelectorAll('picture source').forEach(function (src) {
        var dss = src.getAttribute('data-srcset');
        if (dss && !src.srcset) {
            src.setAttribute('srcset', dss);
        }
    });

    // 4. Backgrounds via data-background / data-bg / data-background-image
    var BG_ATTRS = ['data-background', 'data-bg', 'data-background-image', 'data-background-src'];
    document.querySelectorAll(BG_ATTRS.map(function(a){ return '[' + a + ']'; }).join(',')).forEach(function (el) {
        for (var i = 0; i < BG_ATTRS.length; i++) {
            var bg = el.getAttribute(BG_ATTRS[i]);
            if (bg && !isPlaceholder(bg)) {
                el.style.backgroundImage = 'url("' + bg + '")';
                break;
            }
        }
    });

    // 5. Iframes lazy
    document.querySelectorAll('iframe[loading="lazy"]').forEach(function (f) {
        f.setAttribute('loading', 'eager');
    });
})();
"""

# ---------------------------------------------------------------------------
# JS : attendre que toutes les images soient chargées (retourne bool)
# ---------------------------------------------------------------------------
_JS_ALL_IMAGES_LOADED = """
(function () {
    var imgs = Array.from(document.querySelectorAll('img'));
    if (imgs.length === 0) return true;
    return imgs.every(function (img) {
        // Ignore les images sans src ou placeholder
        var src = img.getAttribute('src') || '';
        if (!src || src.indexOf('data:') === 0) return true;
        return img.complete && img.naturalWidth > 0;
    });
})();
"""


# ---------------------------------------------------------------------------
# Globals UI
# ---------------------------------------------------------------------------
url_entry    = None
status_text  = None
script1_var  = None
script2_var  = None
headless_var = None
time_entry   = None
css_entry    = None
relance_btn  = None


# ---------------------------------------------------------------------------
# Helpers UI (thread-safe)
# ---------------------------------------------------------------------------
def append_status(text: str):
    def _do():
        try:
            status_text.insert("end", text + "\n")
            status_text.see("end")
        except Exception:
            print(text)
    try:
        status_text.after(0, _do)
    except Exception:
        print(text)


def append_status_emphasized(text: str):
    sep = "=" * 60
    def _do():
        try:
            status_text.insert("end", f"\n{sep}\n*** {text} ***\n{sep}\n")
            status_text.see("end")
        except Exception:
            print(text)
    try:
        status_text.after(0, _do)
    except Exception:
        print(text)


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------
def get_filename_from_url(url: str) -> str:
    u = re.sub(r"^https?://", "", url)
    u = re.sub(r"^www\.", "", u)
    domain = u.split('/')[0]
    return re.sub(r"\..*$", "", domain)


def get_expected_filenames_for_url(url: str, want_mobile: bool, want_full: bool) -> List[str]:
    base = get_filename_from_url(url)
    out = []
    if want_mobile:
        out.append(f"{base}-mobile.jpg")
    if want_full:
        out.append(f"{base}.jpg")
    return out


def verify_image_exists_and_valid(path: str) -> bool:
    if not os.path.exists(path):
        return False
    try:
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Driver Chrome
# ---------------------------------------------------------------------------
def _build_driver(headless: bool, mobile: bool = False) -> "webdriver.Chrome":
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--force-device-scale-factor=1")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--hide-scrollbars")
    opts.add_argument("--disable-blink-features=AutomationControlled")

    if mobile:
        mobile_emulation = {
            "deviceMetrics": {"width": 390, "height": 844, "pixelRatio": 1.0},
            "userAgent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/16.0 Mobile/15E148 Safari/604.1"
            ),
        }
        try:
            opts.add_experimental_option("mobileEmulation", mobile_emulation)
        except Exception:
            pass

    return webdriver.Chrome(options=opts)


# ---------------------------------------------------------------------------
# Étapes d'injection / préparation
# ---------------------------------------------------------------------------
def _inject_css(driver, css: str):
    """Injecte le CSS personnalisé dans un <style> en fin de <head>."""
    try:
        driver.execute_script(
            'var s = document.createElement("style");'
            's.setAttribute("id","__capture_css__");'
            's.textContent = arguments[0];'
            'document.head.appendChild(s);',
            css or CSS_DEFAULT,
        )
    except Exception:
        pass


def _neutralize_fixed_elements(driver):
    """Passe tous les éléments fixed/sticky en position relative."""
    try:
        driver.execute_script(_JS_NEUTRALIZE_FIXED)
    except Exception:
        pass




def _load_lazy_images(driver):
    """
    Déclenche le chargement de toutes les images lazy :
    - loading="lazy" → eager
    - data-src / data-lazy-src / data-original / etc.
    - picture source avec data-srcset
    - éléments avec data-background / data-bg
    """
    try:
        driver.execute_script(_JS_LOAD_LAZY_IMAGES)
    except Exception:
        pass


def _wait_images_complete(driver, timeout: float = 25.0):
    """Attend que toutes les images soient chargées (max timeout secondes)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            done = driver.execute_script(_JS_ALL_IMAGES_LOADED)
            if done:
                return
        except Exception:
            pass
        time.sleep(0.4)


def _scroll_to_trigger_observers(driver):
    """
    Scroll progressif pour déclencher les IntersectionObservers,
    puis remonte en haut. Plusieurs passes jusqu'à stabilisation.
    """
    try:
        vh = int(driver.execute_script("return window.innerHeight || 900;"))
    except Exception:
        vh = 900

    last_h = -1
    for _pass in range(4):
        try:
            total_h = int(driver.execute_script(
                "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
            ))
        except Exception:
            total_h = vh

        y = 0
        while y < total_h:
            try:
                driver.execute_script(f"window.scrollTo(0, {y});")
            except Exception:
                pass
            time.sleep(0.2)
            y += max(200, vh // 3)

        # Fin de page
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            pass
        time.sleep(0.4)

        try:
            h = int(driver.execute_script(
                "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
            ))
        except Exception:
            h = last_h

        if h == last_h:
            break
        last_h = h

    # Retour en haut
    try:
        driver.execute_script("window.scrollTo(0, 0);")
    except Exception:
        pass
    time.sleep(0.5)


# ---------------------------------------------------------------------------
# Séquence complète de préparation d'une page avant capture
# ---------------------------------------------------------------------------
def _prepare_page(driver, css: str, time_value: int):
    """
    Séquence de préparation :
    1. Attente initiale (JS d'init, fonts…)
    2. Injection CSS
    3. Neutralisation fixed/sticky
    4. Scroll pour déclencher lazy loaders
    5. Chargement images lazy (data-src, etc.)
    6. Attente images complètes
    7. Kill GSAP (transform:none, opacity:1 ciblé)
    8. Injection CSS une 2e fois (pour les éléments ajoutés dynamiquement)
    9. Retour en haut
    """
    initial_wait = max(2.0, time_value * 0.6)
    time.sleep(initial_wait)

    _inject_css(driver, css)
    # _neutralize_fixed_elements(driver)

    # Scroll + images lazy
    _scroll_to_trigger_observers(driver)
    _load_lazy_images(driver)
    time.sleep(1.5)
    _wait_images_complete(driver, timeout=20.0)

    # 2e passe CSS pour couvrir les éléments ajoutés dynamiquement
    _inject_css(driver, css)
    # _neutralize_fixed_elements(driver)
    time.sleep(0.5)

    # Re-vérifier images (parfois GSAP masquait des images)
    _load_lazy_images(driver)
    _wait_images_complete(driver, timeout=10.0)

    # Retour en haut avant capture
    try:
        driver.execute_script("window.scrollTo(0, 0);")
    except Exception:
        pass
    time.sleep(0.8)


# ---------------------------------------------------------------------------
# CDP : capture full-page
# ---------------------------------------------------------------------------
def _cdp_full_screenshot(driver, max_width: int = 1920, max_height: int = 30000) -> bytes:
    try:
        w = int(driver.execute_script(
            "return Math.max(document.body.scrollWidth, document.documentElement.scrollWidth);"
        ))
        h = int(driver.execute_script(
            "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
        ))
    except Exception:
        w, h = max_width, 1080

    w = max(1, min(w, max_width))
    h = max(1, min(h, max_height))

    result = driver.execute_cdp_cmd("Page.captureScreenshot", {
        "format": "png",
        "captureBeyondViewport": True,
        "clip": {"x": 0, "y": 0, "width": w, "height": h, "scale": 1},
    })
    return base64.b64decode(result["data"])


# ---------------------------------------------------------------------------
# Captures publiques
# ---------------------------------------------------------------------------
def capture_screenshot_full(url: str, headless: bool, time_value: int, css: str) -> Tuple[bool, str]:
    """Capture full-page desktop (1920px)."""
    if webdriver is None:
        return False, "selenium non disponible"

    filename = get_filename_from_url(url)
    prefix = f"[FULL][{url}]"
    driver = _build_driver(headless, mobile=False)
    try:
        driver.set_window_size(1920, 1080)
        driver.get(url + "/?force")

        _prepare_page(driver, css, time_value)

        png_data = _cdp_full_screenshot(driver, max_width=1920)
        img = Image.open(io.BytesIO(png_data))
        jpg_filename = f"{filename}.jpg"
        img.convert("RGB").save(jpg_filename, "JPEG", quality=85)

        return True, f"{prefix} OK → {jpg_filename}"
    except Exception as e:
        return False, f"{prefix} ECHEC : {e}"
    finally:
        try:
            driver.quit()
        except Exception:
            pass


MOBILE_WIDTH  = 390
MOBILE_HEIGHT = 844


def capture_screenshot_small(url: str, headless: bool, time_value: int, css: str) -> Tuple[bool, str]:
    """Capture viewport mobile (390×844px, premier écran, émulation iPhone)."""
    if webdriver is None:
        return False, "selenium non disponible"

    filename = get_filename_from_url(url)
    prefix = f"[MOBILE][{url}]"
    driver = _build_driver(headless, mobile=True)
    try:
        driver.set_window_size(MOBILE_WIDTH, MOBILE_HEIGHT)
        driver.get(url + "/?force")

        _inject_css(driver, css)
        # _neutralize_fixed_elements(driver)
        time.sleep(max(1.5, time_value * 0.5))

        # Scroll léger pour déclencher lazy du premier écran
        _scroll_to_trigger_observers(driver)
        _load_lazy_images(driver)
        _wait_images_complete(driver, timeout=15.0)
        time.sleep(0.5)

        # Retour en haut (on veut le premier écran)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)

        result = driver.execute_cdp_cmd("Page.captureScreenshot", {
            "format": "png",
            "captureBeyondViewport": False,
            "clip": {
                "x": 0, "y": 0,
                "width": MOBILE_WIDTH, "height": MOBILE_HEIGHT,
                "scale": 1,
            },
        })
        png_data = base64.b64decode(result["data"])

        img = Image.open(io.BytesIO(png_data))
        jpg_filename = f"{filename}-mobile.jpg"
        img.convert("RGB").save(jpg_filename, "JPEG", quality=85)

        return True, f"{prefix} OK → {jpg_filename}"
    except Exception as e:
        return False, f"{prefix} ECHEC : {e}"
    finally:
        try:
            driver.quit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def execute_scripts(
    urls: List[str],
    want_mobile: bool,
    want_full: bool,
    headless: bool,
    time_value: int,
    css: str,
) -> List[Tuple[str, str, str]]:
    """Lance les captures en parallèle, retourne la liste des fichiers manquants."""
    tasks = []
    expected: List[Tuple[str, str, str]] = []
    max_workers = min(4, max(1, len(urls)))

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for raw_url in urls:
            u = raw_url.strip()
            if not u:
                continue
            if want_mobile:
                tasks.append(ex.submit(capture_screenshot_small, u, headless, time_value, css))
                for f in get_expected_filenames_for_url(u, want_mobile=True, want_full=False):
                    expected.append((u, "mobile", f))
            if want_full:
                tasks.append(ex.submit(capture_screenshot_full, u, headless, time_value, css))
                for f in get_expected_filenames_for_url(u, want_mobile=False, want_full=True):
                    expected.append((u, "full", f))

        for fut in as_completed(tasks):
            try:
                ok, log = fut.result()
                append_status(log)
            except Exception as e:
                append_status(f"Erreur thread : {e}")

    manquants = [
        (url, typ, fname)
        for url, typ, fname in expected
        if not verify_image_exists_and_valid(fname)
    ]
    return manquants


# ---------------------------------------------------------------------------
# Handlers UI
# ---------------------------------------------------------------------------
def on_execute_clicked():
    global relance_btn
    txt = url_entry.get("0.0", "end").strip()
    urls = [line for line in txt.splitlines() if line.strip()]
    if not urls:
        append_status("Aucune URL fournie.")
        return

    want_mobile = script1_var.get()
    want_full   = script2_var.get()
    headless    = headless_var.get()
    try:
        t = int(time_entry.get())
    except Exception:
        t = 3
    css = css_entry.get("0.0", "end").strip()

    append_status(f"Démarrage — mobile={want_mobile}  full={want_full}  headless={headless}  délai={t}s")

    def _bg():
        manquants = execute_scripts(urls, want_mobile, want_full, headless, t, css)
        if manquants:
            append_status("Fichiers manquants après exécution :")
            for u, typ, f in manquants:
                append_status(f"  • [{typ}] {u}  →  {f}")
            try:
                relance_btn.configure(state="normal")
                relance_btn.manquants = manquants
            except Exception:
                pass
        else:
            append_status_emphasized("Toutes les captures ont été créées avec succès.")

    threading.Thread(target=_bg, daemon=True).start()


def on_relance_clicked():
    manquants = getattr(relance_btn, "manquants", None)
    if not manquants:
        append_status("Aucun fichier manquant à relancer.")
        return
    try:
        t = int(time_entry.get())
    except Exception:
        t = 3
    headless = headless_var.get()
    css = css_entry.get("0.0", "end").strip()

    def _bg():
        append_status("Relance des captures manquantes…")
        for url, typ, fname in manquants:
            if typ == "mobile":
                ok, log = capture_screenshot_small(url, headless, t, css)
            else:
                ok, log = capture_screenshot_full(url, headless, t, css)
            append_status(log)
            if ok and verify_image_exists_and_valid(fname):
                append_status(f"  ✓ {fname}")
            else:
                append_status(f"  ✗ Toujours manquant : {fname}")
        append_status("Relance terminée.")

    threading.Thread(target=_bg, daemon=True).start()


# ---------------------------------------------------------------------------
# Interface graphique
# ---------------------------------------------------------------------------
def build_ui():
    global url_entry, status_text, script1_var, script2_var, headless_var, time_entry, css_entry, relance_btn

    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("Capture de sites web — v2")
    root.geometry("900x780")

    ctk.CTkLabel(root, text="Capture de sites web", font=("Segoe UI", 20, "bold")).pack(pady=(12, 6))

    # Zone URLs
    frame_urls = ctk.CTkFrame(root)
    frame_urls.pack(fill="x", padx=12, pady=(0, 8))
    ctk.CTkLabel(frame_urls, text="URLs à capturer (une par ligne) :").pack(anchor="w")
    url_entry = ctk.CTkTextbox(frame_urls, height=140)
    url_entry.pack(fill="x", pady=(6, 4))

    # Options
    frame_opts = ctk.CTkFrame(root)
    frame_opts.pack(fill="x", padx=12, pady=(0, 8))
    script1_var  = ctk.BooleanVar(value=True)
    script2_var  = ctk.BooleanVar(value=True)
    headless_var = ctk.BooleanVar(value=True)

    ctk.CTkCheckBox(frame_opts, text="Version mobile (390px)", variable=script1_var).grid(
        row=0, column=0, padx=6, pady=6, sticky="w"
    )
    ctk.CTkCheckBox(frame_opts, text="Version desktop (1920px)", variable=script2_var).grid(
        row=0, column=1, padx=6, pady=6, sticky="w"
    )
    ctk.CTkCheckBox(frame_opts, text="Mode headless", variable=headless_var).grid(
        row=0, column=2, padx=6, pady=6, sticky="w"
    )
    ctk.CTkLabel(frame_opts, text="Délai (s) :").grid(row=0, column=3, padx=(16, 4))
    time_entry = ctk.CTkEntry(frame_opts, width=70)
    time_entry.insert(0, "3")
    time_entry.grid(row=0, column=4, padx=(0, 6))

    ctk.CTkButton(root, text="▶  Lancer les captures", command=on_execute_clicked).pack(pady=(4, 8))

    # Log
    status_text = ctk.CTkTextbox(root, height=200)
    status_text.pack(fill="both", expand=True, padx=12, pady=(0, 8))

    # Zone CSS
    frame_css = ctk.CTkFrame(root)
    frame_css.pack(fill="x", padx=12, pady=(0, 8))
    ctk.CTkLabel(frame_css, text="CSS injecté (modifiable) :").pack(anchor="w")
    css_entry = ctk.CTkTextbox(frame_css, height=120)
    css_entry.insert("0.0", CSS_DEFAULT)
    css_entry.pack(fill="x", pady=(6, 4))

    # Bouton relance
    relance_btn = ctk.CTkButton(
        root,
        text="↺  Relancer les captures manquantes",
        command=on_relance_clicked,
        state="disabled",
    )
    relance_btn.pack(pady=(4, 14))

    root.mainloop()


if __name__ == "__main__":
    build_ui()
