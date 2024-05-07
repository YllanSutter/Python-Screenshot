import sys
import os
from Screenshot import Screenshot
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import re
import time

def sanitize_url(url):
    # Remplace les caractères non alphanumériques par des tirets "-"
    sanitized_url = re.sub(r'\W+', '-', url)
    return sanitized_url

def get_filename_from_url(url):
    # Supprimer le protocole "https://"
    url = re.sub(r'^https://', '', url)
    # Supprimer "www."
    url = re.sub(r'^www\.', '', url)
    # Extraire le domaine principal
    domain = url.split('/')[0]
    # Supprimer l'extension de fichier
    filename = re.sub(r'\..*$', '', domain)
    return filename


def capture_screenshot(url, headless=False, time_value=3):
    ob = Screenshot.Screenshot()
    filename = get_filename_from_url(url)
    
    # Configuration des options Chrome
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")  # Pour exécuter Chrome en mode headless (sans interface graphique)

    driver = webdriver.Chrome(options=chrome_options)
    
    # Charger l'URL
    driver.get(url + "/?force")
    
    # Charger le fichier CSS
    css_file_path = "style_custom.css"
    with open(css_file_path, "r") as css_file:
        css = css_file.read()
        driver.execute_script('var style = document.createElement("style"); style.type = "text/css"; style.innerHTML = arguments[0]; document.head.appendChild(style);', css)
    
    # Forcer la taille de la fenêtre à 1920x1080
    driver.set_window_size(1920, 1080)
    
    # Attends un certain temps spécifié
    time.sleep(time_value)
    
    # Prendre une capture d'écran
    sanitized_url = sanitize_url(url)
    img_url = ob.full_screenshot(driver, save_path='.', image_name=f'{filename}.png', is_load_at_runtime=True, load_wait_time=3)
    print(img_url)
    
    # Fermer le navigateur
    driver.quit()

# Vérification si les arguments URL, headless et time sont passés en ligne de commande
if len(sys.argv) < 2:
    print("Veuillez fournir l'URL en argument.")
    sys.exit(1)

url = sys.argv[1]

# Vérification des arguments facultatifs headless et time
headless = "--headless" in sys.argv
time_value = 3
if "--time" in sys.argv:
    time_index = sys.argv.index("--time")
    if len(sys.argv) > time_index + 1:
        try:
            time_value = int(sys.argv[time_index + 1])
        except ValueError:
            print("La valeur de l'argument --time doit être un entier. Utilisation de la valeur par défaut (3).")

# Appel de la fonction pour capturer la capture d'écran
capture_screenshot(url, headless, time_value)
