import json
import requests

from bs4 import BeautifulSoup

competencias = {
    "competencias" : []
}
for id in range(1480):
    url = f"https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia={id}"

    response = requests.get(url)
    html_content = response.text

    # Parse the HTML content
    soup = BeautifulSoup(html_content, 'html.parser')
    print(str(id))
    titulo = soup.find("div", {"class": "col-12 tituloPagina"}).text.strip()
    print(titulo)
    if titulo != "Error al cargar la información":
        try:
            federacion = soup.find("span", id="LTituloDelegacion").text.strip()
            torneo = soup.find("span", id="LTituloCompeticion").text.strip()
            print(federacion + "-" + torneo)
            competencias["competencias"].append(
                {
                    "id": id,
                    "url": url,
                    "federacion": federacion,
                    "torneo": torneo,
                }
            )
        except:
            try: 
                torneo = soup.find("span", id="LTituloCompeticion").text.strip()
                print(torneo)
                competencias["competencias"].append(
                    {
                        "id": id,
                        "url": url,
                        "torneo":torneo,
                    }
                )
            except:
                print(url)
                competencias["competencias"].append(
                    {
                        "id": id,
                        "url": url,
                    }
                )

    # Escribir la estructura competencia en un archivo JSON
with open('gesdeportiva.json', 'w') as json_file:
    json.dump(competencias, json_file, indent=4)