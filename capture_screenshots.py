import subprocess
import tkinter as tk
from tkinter import ttk

def execute_scripts(urls):
    # Chemin vers les scripts Python
    script1_path = "capture_screenshots_small.py"
    script2_path = "capture_screenshotsFull.py"

    # Exécution du premier script pour chaque URL
    for url in urls:
        subprocess.run(["python", script1_path, url.strip()])

    # Exécution du deuxième script pour chaque URL / A commenter si t'as besoin de faire juste le format mobile
    # for url in urls:
    #     subprocess.run(["python", script2_path, url.strip()])

def execute_button_clicked():
    urls = url_entry.get("1.0", tk.END).splitlines()  # Récupère tout le texte depuis le début jusqu'à la fin
    execute_scripts(urls)
    status_label.config(text="Scripts exécutés avec succès!")

# Création de la fenêtre principale
root = tk.Tk()
root.title("Exécution des scripts")

# Création des widgets
url_label = ttk.Label(root, text="URLs (une par ligne):")
url_entry = tk.Text(root, width=50, height=10)  # Champ de texte multiligne
execute_button = ttk.Button(root, text="Exécuter les scripts", command=execute_button_clicked)
status_label = ttk.Label(root, text="")

# Placement des widgets dans la fenêtre
url_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
url_entry.grid(row=0, column=1, padx=5, pady=5, rowspan=3, sticky="nsew")  # Utilise rowspan pour s'étendre sur plusieurs lignes
execute_button.grid(row=3, column=0, columnspan=2, padx=5, pady=5)
status_label.grid(row=4, column=0, columnspan=2, padx=5, pady=5)

# Lancement de la boucle principale
root.mainloop()
