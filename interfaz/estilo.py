"""Sistema de diseño: paleta, estilos, ilustraciones y componentes visuales.

Estilo editorial inspirado en los temas de WordPress: encabezados serif, mucho
aire, tarjetas suaves y un banner con ilustración en cada pantalla.

Teoría del color (regla 60-30-10):
  * 60 %  crema    #FAF6EC  fondo cálido que descansa la vista
  * 30 %  azul navy #0B1D3A / #14305E  estructura: barra lateral, banners, botones
  * 10 %  dorado   #C69B3F  acento complementario del azul (naranja atenuado)
Las etiquetas usan tonos apagados (burdeos, ocre, azul acero, verde salvia) con
contraste mínimo 4.5:1 (WCAG AA). Las imágenes son SVG escritos en este archivo:
no hay nada que descargar y funcionan sin internet.
"""

import html

import streamlit as st

PALETA = {
    "navy_900": "#0B1D3A",
    "navy_700": "#14305E",
    "navy_500": "#2A4A7F",
    "crema": "#FAF6EC",
    "superficie": "#FFFDF8",
    "linea": "#E3DAC3",
    "oro": "#C69B3F",
    "oro_claro": "#D9B45A",
    "texto": "#14213D",
    "texto_2": "#4E5A6E",
}

# Etiquetas: (fondo, texto). Tonos apagados con contraste mínimo 4.5:1 (WCAG AA).
TONOS_ETIQUETA = {
    "alta": ("#F6E3E3", "#8C2F39"),  # burdeos
    "media": ("#F8EBCB", "#7A5410"),  # ocre
    "baja": ("#E4EAF4", "#2A4A7F"),  # azul acero
    "ok": ("#E3F0E8", "#2F6B4B"),  # verde salvia
    "neutro": ("#F1EAD8", "#4E5A6E"),  # arena
}

# Imagen de marca: monograma y letras convertidas en trazados (fuente Playfair Display).
LOGO_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 58" width="160" height="58"><circle cx="28" cy="29" r="19" fill="none" stroke="#D9B45A" stroke-width="2.2"/><path d="M19 36l7-9 5 5 8-12" fill="none" stroke="#D9B45A" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="39" cy="20" r="2.4" fill="#D9B45A"/><path d="M71.9 11.8 78.5 28.7Q78.9 29.7 79.3 30.1Q79.8 30.4 80.2 30.5V31Q79.4 30.9 78.3 30.9Q77.2 30.9 76.1 30.9Q74.9 30.9 73.7 30.9Q72.6 30.9 72 31V30.5Q73.4 30.4 73.7 30Q74.1 29.6 73.6 28.2L69 15.6L69.5 14.9L65.3 25.6Q64.8 27.1 64.6 28.1Q64.5 29 64.8 29.5Q65 30 65.6 30.2Q66.2 30.4 67 30.5V31Q66.1 30.9 65.3 30.9Q64.5 30.9 63.6 30.9Q63.1 30.9 62.5 30.9Q62 30.9 61.6 31V30.5Q62.2 30.4 62.8 29.7Q63.4 29.1 63.9 27.6L70.1 11.8Q70.5 11.9 71 11.9Q71.5 11.9 71.9 11.8ZM73.8 23.2V23.8H65.8L66 23.2Z M86 16.7Q87.1 16.7 88 16.9Q88.8 17.2 89.2 17.5Q90.1 18.1 90.3 16.7H90.9Q90.9 17.4 90.8 18.5Q90.8 19.6 90.8 21.4H90.2Q90.1 20.4 89.7 19.5Q89.4 18.5 88.6 17.9Q87.9 17.3 86.8 17.3Q86 17.3 85.5 17.7Q84.9 18.1 84.9 19Q84.9 19.8 85.4 20.4Q85.9 21 86.7 21.6Q87.4 22.1 88.3 22.7Q89.2 23.4 89.9 24.1Q90.6 24.7 91.1 25.5Q91.5 26.3 91.5 27.4Q91.5 28.6 90.8 29.5Q90.1 30.4 88.9 30.9Q87.8 31.4 86.4 31.4Q85.6 31.4 84.9 31.2Q84.3 31.1 83.8 30.8Q83.5 30.6 83.2 30.5Q82.9 30.4 82.6 30.2Q82.3 30.2 82.1 30.4Q81.9 30.7 81.8 31.2H81.3Q81.3 30.3 81.3 29.1Q81.4 27.8 81.4 25.8H81.9Q82.1 27.2 82.5 28.4Q83 29.5 83.7 30.1Q84.4 30.8 85.6 30.8Q86 30.8 86.5 30.6Q86.9 30.4 87.2 29.9Q87.5 29.5 87.5 28.8Q87.5 27.7 86.7 26.9Q85.9 26.1 84.7 25.2Q83.9 24.5 83.1 23.8Q82.3 23.1 81.8 22.3Q81.4 21.4 81.4 20.4Q81.4 19.2 82 18.3Q82.7 17.5 83.7 17.1Q84.8 16.7 86 16.7Z M100.1 16.7Q102.5 16.7 103.8 18.1Q105.2 19.5 105.2 22.7H96.3L96.2 22.1H101.8Q101.8 20.8 101.6 19.7Q101.4 18.6 101 17.9Q100.6 17.2 99.9 17.2Q99 17.2 98.3 18.4Q97.7 19.6 97.5 22.4L97.6 22.5Q97.6 22.8 97.6 23.2Q97.6 23.5 97.6 23.9Q97.6 25.8 98.1 27Q98.6 28.1 99.4 28.6Q100.2 29.2 101.1 29.2Q101.6 29.2 102.2 29Q102.9 28.8 103.5 28.3Q104.1 27.9 104.6 27L105.1 27.2Q104.8 28.2 104.1 29.2Q103.4 30.1 102.3 30.8Q101.2 31.4 99.7 31.4Q97.9 31.4 96.5 30.6Q95.1 29.8 94.3 28.2Q93.5 26.6 93.5 24.2Q93.5 21.7 94.3 20Q95.2 18.3 96.7 17.5Q98.2 16.7 100.1 16.7Z M112.1 16.7Q113.2 16.7 114.1 16.9Q114.9 17.2 115.3 17.5Q116.2 18.1 116.4 16.7H117Q116.9 17.4 116.9 18.5Q116.9 19.6 116.9 21.4H116.3Q116.2 20.4 115.8 19.5Q115.4 18.5 114.7 17.9Q114 17.3 112.9 17.3Q112.1 17.3 111.5 17.7Q111 18.1 111 19Q111 19.8 111.5 20.4Q112 21 112.7 21.6Q113.5 22.1 114.4 22.7Q115.2 23.4 116 24.1Q116.7 24.7 117.1 25.5Q117.6 26.3 117.6 27.4Q117.6 28.6 116.9 29.5Q116.2 30.4 115 30.9Q113.9 31.4 112.5 31.4Q111.7 31.4 111 31.2Q110.4 31.1 109.9 30.8Q109.6 30.6 109.3 30.5Q109 30.4 108.7 30.2Q108.4 30.2 108.2 30.4Q108 30.7 107.9 31.2H107.3Q107.4 30.3 107.4 29.1Q107.4 27.8 107.4 25.8H108Q108.2 27.2 108.6 28.4Q109 29.5 109.8 30.1Q110.5 30.8 111.7 30.8Q112.1 30.8 112.5 30.6Q113 30.4 113.3 29.9Q113.5 29.5 113.5 28.8Q113.5 27.7 112.8 26.9Q112 26.1 110.8 25.2Q110 24.5 109.2 23.8Q108.4 23.1 107.9 22.3Q107.4 21.4 107.4 20.4Q107.4 19.2 108.1 18.3Q108.7 17.5 109.8 17.1Q110.9 16.7 112.1 16.7Z M126.2 16.7Q128.2 16.7 129.6 17.4Q131.1 18.1 132 19.7Q132.8 21.4 132.8 24Q132.8 26.7 132 28.3Q131.1 29.9 129.6 30.6Q128.2 31.4 126.2 31.4Q124.3 31.4 122.8 30.6Q121.3 29.9 120.4 28.3Q119.6 26.7 119.6 24Q119.6 21.4 120.4 19.7Q121.3 18.1 122.8 17.4Q124.3 16.7 126.2 16.7ZM126.2 17.2Q125.1 17.2 124.4 18.8Q123.6 20.4 123.6 24Q123.6 27.7 124.4 29.2Q125.1 30.8 126.2 30.8Q127.3 30.8 128 29.2Q128.7 27.7 128.7 24Q128.7 20.4 128 18.8Q127.3 17.2 126.2 17.2Z M143.8 16.7Q144.6 16.7 145.2 17Q145.7 17.4 146 18Q146.2 18.5 146.2 19.1Q146.2 20.1 145.6 20.8Q145.1 21.4 144.1 21.4Q143.2 21.4 142.6 20.9Q142.1 20.5 142.1 19.7Q142.1 18.9 142.4 18.4Q142.8 17.9 143.3 17.6Q142.9 17.5 142.5 17.6Q142 17.7 141.6 18Q141.1 18.4 140.8 18.9Q140.5 19.4 140.3 19.9Q140.1 20.5 140.1 21.1V28.2Q140.1 29.5 140.7 30Q141.4 30.4 142.6 30.4V31Q142 31 140.8 30.9Q139.6 30.9 138.3 30.9Q137.2 30.9 136.1 30.9Q135 31 134.5 31V30.4Q135.4 30.4 135.8 30Q136.2 29.6 136.2 28.5V20Q136.2 18.8 135.8 18.2Q135.5 17.6 134.5 17.6V17Q135.3 17.1 136.1 17.1Q137.3 17.1 138.3 17Q139.2 16.9 140.1 16.7V19.3Q140.4 18.5 140.9 17.9Q141.5 17.3 142.2 17Q142.9 16.7 143.8 16.7Z" fill="#FAF6EC"/><path d="M66.7 40.1Q67.3 40.1 67.7 40.3Q68.1 40.5 68.4 40.8Q68.6 40.9 68.7 40.8Q68.8 40.7 68.9 40.3H69.1Q69.1 40.6 69.1 41.2Q69 41.7 69 42.5H68.8Q68.8 42.1 68.7 41.8Q68.6 41.5 68.5 41.3Q68.4 41.1 68.2 40.9Q67.9 40.6 67.6 40.5Q67.2 40.4 66.8 40.4Q66.3 40.4 66 40.6Q65.6 40.9 65.4 41.3Q65.1 41.8 65 42.4Q64.9 43 64.9 43.7Q64.9 44.3 65 44.9Q65.1 45.5 65.4 46Q65.6 46.4 66 46.7Q66.4 46.9 66.9 46.9Q67.2 46.9 67.6 46.8Q68 46.6 68.2 46.4Q68.5 46.1 68.6 45.7Q68.8 45.3 68.8 44.6H69Q69 45.5 69.1 46.1Q69.1 46.6 69.1 47H68.9Q68.8 46.6 68.7 46.5Q68.6 46.4 68.4 46.5Q68.1 46.8 67.7 46.9Q67.3 47.1 66.7 47.1Q65.7 47.1 65 46.7Q64.2 46.3 63.8 45.5Q63.4 44.8 63.4 43.7Q63.4 42.6 63.9 41.8Q64.3 41 65 40.6Q65.7 40.1 66.7 40.1Z M76.5 40.1Q77.5 40.1 78.2 40.5Q79 41 79.4 41.7Q79.8 42.5 79.8 43.6Q79.8 44.6 79.4 45.4Q78.9 46.2 78.2 46.7Q77.5 47.1 76.5 47.1Q75.6 47.1 74.8 46.7Q74.1 46.3 73.7 45.5Q73.3 44.8 73.3 43.7Q73.3 42.6 73.7 41.8Q74.1 41 74.9 40.6Q75.6 40.1 76.5 40.1ZM76.5 40.3Q75.9 40.3 75.5 40.7Q75.1 41.2 74.9 41.9Q74.7 42.7 74.7 43.7Q74.7 44.7 74.9 45.4Q75.2 46.2 75.6 46.6Q76 47 76.6 47Q77.1 47 77.5 46.5Q78 46.1 78.2 45.4Q78.4 44.6 78.4 43.6Q78.4 42.6 78.2 41.9Q77.9 41.1 77.5 40.7Q77 40.3 76.5 40.3Z M91.7 40.3V40.5Q91.4 40.5 91.2 40.5Q91.1 40.6 91 40.8Q91 40.9 91 41.3V46Q91 46.3 91 46.5Q91.1 46.7 91.2 46.7Q91.4 46.8 91.7 46.8V47Q91.4 47 91.1 47Q90.7 47 90.3 47Q89.9 47 89.5 47Q89.1 47 88.9 47V46.8Q89.2 46.8 89.4 46.7Q89.5 46.7 89.6 46.5Q89.7 46.3 89.7 46V40.8L89.7 40.8L87.4 47H87.2L84.7 40.9V45.6Q84.7 46 84.8 46.3Q84.8 46.6 85 46.7Q85.2 46.8 85.6 46.8V47Q85.4 47 85.2 47Q84.9 47 84.6 47Q84.4 47 84.1 47Q83.9 47 83.8 47V46.8Q84.1 46.8 84.2 46.7Q84.4 46.6 84.4 46.3Q84.5 46.1 84.5 45.7V41.3Q84.5 40.9 84.4 40.8Q84.4 40.6 84.2 40.5Q84.1 40.5 83.8 40.5V40.3Q83.9 40.3 84.1 40.3Q84.4 40.3 84.6 40.3Q85 40.3 85.3 40.3Q85.6 40.3 85.9 40.3L87.9 45.4L87.7 45.5L89.7 40.3Q89.8 40.3 90 40.3Q90.2 40.3 90.3 40.3Q90.7 40.3 91.1 40.3Q91.4 40.3 91.7 40.3Z M100.6 40.3Q100.5 40.7 100.5 41Q100.5 41.4 100.5 41.6Q100.5 41.8 100.5 41.9Q100.5 42.1 100.5 42.2H100.3Q100.2 41.6 100.1 41.2Q99.9 40.8 99.6 40.6Q99.3 40.5 98.8 40.5H98.3Q98 40.5 97.9 40.5Q97.7 40.6 97.7 40.7Q97.6 40.9 97.6 41.2V46.1Q97.6 46.4 97.7 46.5Q97.7 46.7 97.9 46.7Q98 46.8 98.3 46.8H98.9Q99.3 46.8 99.7 46.6Q100 46.4 100.2 46Q100.4 45.6 100.5 44.9H100.7Q100.7 45.2 100.7 45.6Q100.7 45.8 100.7 46.2Q100.7 46.6 100.7 47Q100.3 47 99.7 47Q99 47 98.6 47Q98.4 47 98 47Q97.6 47 97.2 47Q96.8 47 96.4 47Q96 47 95.6 47V46.8Q95.9 46.8 96.1 46.7Q96.2 46.7 96.3 46.5Q96.3 46.3 96.3 46V41.3Q96.3 40.9 96.3 40.8Q96.2 40.6 96.1 40.5Q95.9 40.5 95.6 40.5V40.3Q96 40.3 96.4 40.3Q96.8 40.3 97.2 40.3Q97.6 40.3 98 40.3Q98.4 40.3 98.6 40.3Q99 40.3 99.6 40.3Q100.1 40.3 100.6 40.3ZM99 43.5Q99 43.5 99 43.6Q99 43.7 99 43.7H97.3Q97.3 43.7 97.3 43.6Q97.3 43.5 97.3 43.5ZM99.3 42.3Q99.3 42.8 99.3 43.1Q99.3 43.4 99.3 43.6Q99.3 43.9 99.3 44.1Q99.3 44.4 99.3 45H99.1Q99.1 44.6 99 44.4Q98.9 44.1 98.7 43.9Q98.4 43.7 98 43.7V43.5Q98.3 43.5 98.5 43.4Q98.7 43.3 98.8 43.1Q98.9 42.9 99 42.7Q99.1 42.5 99.1 42.3Z M104.7 40.3Q105 40.3 105.3 40.3Q105.7 40.3 106.1 40.3Q106.5 40.3 107 40.3Q107.4 40.3 107.5 40.3Q108.4 40.3 109 40.5Q109.5 40.7 109.8 41.1Q110.1 41.4 110.1 41.9Q110.1 42.2 109.9 42.6Q109.8 42.9 109.5 43.2Q109.2 43.5 108.7 43.6Q108.2 43.8 107.3 43.8H106.4V43.6H107.2Q107.8 43.6 108.2 43.4Q108.5 43.2 108.6 42.8Q108.7 42.5 108.7 42Q108.7 41.3 108.4 40.9Q108.1 40.5 107.4 40.5Q107 40.5 106.9 40.6Q106.8 40.8 106.8 41.3V46Q106.8 46.3 106.8 46.5Q106.9 46.7 107 46.7Q107.2 46.8 107.5 46.8V47Q107.3 47 106.9 47Q106.5 47 106.1 47Q105.7 47 105.3 47Q105 47 104.7 47V46.8Q105 46.8 105.2 46.7Q105.4 46.7 105.4 46.5Q105.5 46.3 105.5 46V41.3Q105.5 40.9 105.4 40.8Q105.4 40.6 105.2 40.5Q105 40.5 104.7 40.5ZM106.4 43.6Q106.9 43.7 107.2 43.7Q107.5 43.7 107.7 43.7Q107.9 43.8 108.1 43.8Q108.9 43.9 109.2 44.1Q109.6 44.4 109.7 45L110 46Q110 46.4 110.1 46.6Q110.2 46.7 110.4 46.7Q110.6 46.7 110.7 46.6Q110.8 46.6 110.8 46.4L111 46.6Q110.7 46.9 110.5 47Q110.2 47.1 109.8 47.1Q109.3 47.1 109 46.9Q108.7 46.7 108.6 46.1L108.4 45.2Q108.3 44.8 108.2 44.5Q108.1 44.1 108 44Q107.8 43.8 107.5 43.8H106.4Z M117.7 40.1Q118.3 40.1 118.7 40.3Q119.1 40.5 119.5 40.8Q119.6 40.9 119.7 40.8Q119.8 40.7 119.9 40.3H120.1Q120.1 40.6 120.1 41.2Q120.1 41.7 120.1 42.5H119.8Q119.8 42.1 119.7 41.8Q119.7 41.5 119.5 41.3Q119.4 41.1 119.2 40.9Q118.9 40.6 118.6 40.5Q118.2 40.4 117.8 40.4Q117.4 40.4 117 40.6Q116.6 40.9 116.4 41.3Q116.1 41.8 116 42.4Q115.9 43 115.9 43.7Q115.9 44.3 116 44.9Q116.2 45.5 116.4 46Q116.7 46.4 117 46.7Q117.4 46.9 117.9 46.9Q118.3 46.9 118.6 46.8Q119 46.6 119.2 46.4Q119.5 46.1 119.7 45.7Q119.8 45.3 119.8 44.6H120.1Q120.1 45.5 120.1 46.1Q120.1 46.6 120.1 47H119.9Q119.8 46.6 119.8 46.5Q119.7 46.4 119.5 46.5Q119.1 46.8 118.7 46.9Q118.3 47.1 117.7 47.1Q116.7 47.1 116 46.7Q115.3 46.3 114.9 45.5Q114.5 44.8 114.5 43.7Q114.5 42.6 114.9 41.8Q115.3 41 116 40.6Q116.8 40.1 117.7 40.1Z M127 40.3V40.5Q126.7 40.5 126.5 40.5Q126.4 40.6 126.3 40.8Q126.2 40.9 126.2 41.3V46Q126.2 46.3 126.3 46.5Q126.4 46.7 126.5 46.7Q126.7 46.8 127 46.8V47Q126.7 47 126.4 47Q126 47 125.6 47Q125.2 47 124.8 47Q124.4 47 124.2 47V46.8Q124.5 46.8 124.7 46.7Q124.8 46.7 124.9 46.5Q124.9 46.3 124.9 46V41.3Q124.9 40.9 124.9 40.8Q124.8 40.6 124.7 40.5Q124.5 40.5 124.2 40.5V40.3Q124.4 40.3 124.8 40.3Q125.2 40.3 125.6 40.3Q126 40.3 126.4 40.3Q126.7 40.3 127 40.3Z M133.9 40.2 136.2 46.2Q136.3 46.5 136.5 46.7Q136.7 46.8 136.8 46.8V47Q136.6 47 136.2 47Q135.9 47 135.5 47Q135.1 47 134.7 47Q134.4 47 134.1 47V46.8Q134.6 46.8 134.8 46.6Q134.9 46.5 134.7 46L133 41.5L133.2 41.3L131.7 45.2Q131.5 45.7 131.5 46Q131.4 46.3 131.5 46.5Q131.6 46.7 131.8 46.7Q132 46.8 132.3 46.8V47Q132 47 131.7 47Q131.4 47 131.1 47Q130.9 47 130.7 47Q130.5 47 130.4 47V46.8Q130.6 46.8 130.8 46.6Q131 46.4 131.2 45.9L133.4 40.2Q133.5 40.3 133.6 40.3Q133.8 40.3 133.9 40.2ZM134.7 44.3V44.5H131.9L132 44.3Z M143.1 40.3V40.5Q142.8 40.5 142.6 40.5Q142.4 40.6 142.4 40.8Q142.3 40.9 142.3 41.3V46.1Q142.3 46.4 142.4 46.5Q142.4 46.7 142.6 46.7Q142.7 46.8 143 46.8H143.5Q143.9 46.8 144.2 46.6Q144.5 46.5 144.7 46.3Q144.9 46 145 45.6Q145.1 45.3 145.2 44.8H145.4Q145.4 45.1 145.4 45.6Q145.4 45.8 145.4 46.2Q145.4 46.6 145.4 47Q145 47 144.4 47Q143.7 47 143.3 47Q143 47 142.7 47Q142.3 47 141.9 47Q141.5 47 141.1 47Q140.7 47 140.3 47V46.8Q140.6 46.8 140.8 46.7Q140.9 46.7 141 46.5Q141 46.3 141 46V41.3Q141 40.9 141 40.8Q140.9 40.6 140.8 40.5Q140.6 40.5 140.3 40.5V40.3Q140.5 40.3 140.9 40.3Q141.3 40.3 141.7 40.3Q142.1 40.3 142.5 40.3Q142.8 40.3 143.1 40.3Z" fill="#D9B45A"/></svg>'''

CSS = """
:root{
  --navy-900:#0B1D3A; --navy-700:#14305E; --navy-500:#2A4A7F;
  --crema:#FAF6EC; --superficie:#FFFDF8; --linea:#E3DAC3; --arena:#F1EAD8;
  --oro:#C69B3F; --oro-claro:#D9B45A; --texto:#14213D; --texto-2:#4E5A6E;
  --serif:'Playfair Display',Georgia,'Times New Roman',serif;
  --sombra:0 1px 2px rgba(11,29,58,.05),0 10px 28px rgba(11,29,58,.07);
  --sombra-alta:0 2px 4px rgba(11,29,58,.06),0 16px 36px rgba(11,29,58,.12);
}
[data-testid="stMainBlockContainer"]{max-width:1180px;padding-top:1.4rem;padding-bottom:2rem}
[data-testid="stHeader"]{background:transparent}
.stApp{color:var(--texto)}
h1,h2,h3,h4{font-family:var(--serif);color:var(--navy-900);letter-spacing:-.01em}
h2{font-weight:600}
h4{font-weight:700;font-size:1.28rem;margin:0}

/* ---------- Banner (hero) ---------- */
.hero{position:relative;overflow:hidden;display:flex;align-items:center;justify-content:space-between;gap:2rem;
  margin:0 0 1.7rem;padding:2.3rem 2.8rem;border-radius:20px;color:var(--crema);
  background:linear-gradient(115deg,#0B1D3A 0%,#14305E 60%,#1B3F73 100%);box-shadow:var(--sombra-alta)}
.hero::before{content:"";position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(520px 240px at 88% -10%,rgba(217,180,90,.20),transparent 70%),
             radial-gradient(380px 200px at 0% 120%,rgba(255,255,255,.06),transparent 70%)}
.hero-texto{position:relative;max-width:560px}
.hero .eyebrow{font-size:.72rem;font-weight:700;letter-spacing:.22em;text-transform:uppercase;color:var(--oro-claro)}
.hero h1{font-family:var(--serif);font-weight:700;font-size:2.6rem;line-height:1.1;color:var(--crema);margin:.4rem 0 .2rem;padding:0}
.hero .regla{width:54px;height:3px;border-radius:2px;background:var(--oro);margin:.85rem 0 .8rem}
.hero p{margin:0;color:#E4DDC8;font-size:1.02rem;line-height:1.55}
.hero svg{position:relative;flex:none}
@media (max-width:900px){.hero svg{display:none}.hero{padding:1.8rem 1.6rem}.hero h1{font-size:2rem}}

/* ---------- Tarjetas ---------- */
[class*="st-key-tarjeta"],[class*="st-key-opcion"],[class*="st-key-panel"]{
  background:var(--superficie);border:1px solid var(--linea)!important;border-radius:18px;
  box-shadow:var(--sombra);padding:1.15rem 1.3rem;transition:box-shadow .2s ease,transform .2s ease}
[class*="st-key-tarjeta"]:hover,[class*="st-key-opcion"]:hover{box-shadow:var(--sombra-alta);transform:translateY(-2px)}
[data-testid="stMetric"]{background:var(--superficie);border:1px solid var(--linea)!important;border-radius:16px;
  padding:.9rem .85rem;box-shadow:var(--sombra)}
[data-testid="stMetricLabel"]{color:var(--texto-2);font-size:.82rem;font-weight:600}
[data-testid="stMetricLabel"] *{overflow:visible!important;white-space:normal!important;text-overflow:clip!important;line-height:1.25;overflow-wrap:normal!important;word-break:normal!important}
[data-testid="stMetricValue"]{font-family:var(--serif);font-weight:600;color:var(--navy-900);font-size:1.75rem}
[data-testid="stMetricValue"] *{overflow:visible!important;text-overflow:clip!important}

/* ---------- Filas adaptables: se acomodan en varias líneas si falta ancho ---------- */
[class*="st-key-fila_"] [data-testid="stHorizontalBlock"]{flex-wrap:wrap;row-gap:.9rem}
[class*="st-key-fila_"] [data-testid="stColumn"]{min-width:min(100%,var(--min-col,190px))}
.st-key-fila_indicadores{--min-col:128px}
.st-key-fila_rejilla{--min-col:360px}
.st-key-fila_pedido{--min-col:290px}
.st-key-fila_graficos,.st-key-fila_segmentos{--min-col:330px}
[class*="st-key-tarjeta"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important}
[class*="st-key-tarjeta"] [data-testid="stColumn"]{min-width:0!important}

/* ---------- Etiquetas ---------- */
.chip{display:inline-flex;align-items:center;gap:.35rem;padding:.2rem .7rem;border-radius:999px;
  font-size:.74rem;font-weight:700;letter-spacing:.02em;margin:0 .35rem .3rem 0}

/* ---------- Productos ---------- */
.pedido-titulo{font-size:.7rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--texto-2);margin:.9rem 0 .2rem}
.prod{display:flex;align-items:center;gap:.8rem;padding:.5rem 0;border-bottom:1px dashed var(--linea)}
.prod:last-of-type{border-bottom:none}
.prod .ico{flex:none;width:40px;height:40px;border-radius:12px;background:var(--arena);display:flex;align-items:center;justify-content:center}
.prod .nom{flex:1;color:var(--texto);font-weight:500;line-height:1.25}
.prod .nom small{display:block;color:var(--texto-2);font-size:.74rem;font-weight:400}
.prod .pre{color:var(--navy-900);font-weight:700;font-variant-numeric:tabular-nums}
.total{display:flex;justify-content:space-between;align-items:baseline;margin:.55rem 0 1rem;padding-top:.65rem;border-top:2px solid var(--navy-900)}
.total .et{font-size:.72rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--texto-2)}
.total{flex-wrap:wrap;gap:.2rem .8rem}
.total .val{font-family:var(--serif);font-weight:700;font-size:1.5rem;color:var(--navy-900);white-space:nowrap}
.total s{color:var(--texto-2);font-size:.9rem;margin-right:.45rem;font-family:inherit;font-weight:400}
.total .nota{display:block;font-size:.74rem;color:#2F6B4B;font-weight:600;text-align:right}

/* ---------- Barra lateral ---------- */
[data-testid="stSidebar"]{border-right:1px solid rgba(217,180,90,.18)}
[data-testid="stSidebarHeader"]{height:5rem;align-items:center}
[data-testid="stSidebarLogo"]{height:3.5rem!important;width:auto!important;max-width:none!important}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],[data-testid="stSidebar"] [data-testid="stTooltipIcon"]{color:#B9C4D8!important}
[data-testid="stNavSectionHeader"]{color:var(--oro-claro)!important;letter-spacing:.16em;text-transform:uppercase;font-size:.66rem!important;font-weight:700}
[data-testid="stSidebarNavLink"]{border-radius:10px;margin:2px 0}
[data-testid="stSidebarNavLink"][aria-current="page"]{background:rgba(217,180,90,.16)!important;box-shadow:inset 3px 0 0 var(--oro-claro);font-weight:600}
[data-testid="stSidebarNavLink"]:hover{background:rgba(255,255,255,.07)}

/* ---------- Controles ---------- */
button[kind="primary"],[data-testid="stBaseButton-primary"]{border-radius:10px;font-weight:600;letter-spacing:.01em;transition:background .15s,box-shadow .15s}
[data-testid="stBaseLinkButton-primary"]{background:var(--oro)!important;color:var(--navy-900)!important;border:none!important;font-weight:700;border-radius:10px}
[data-testid="stBaseLinkButton-primary"]:hover{background:var(--oro-claro)!important;box-shadow:0 6px 16px rgba(198,155,63,.35)}
[data-baseweb="tab-highlight"]{background-color:var(--oro)!important;height:3px!important}
button[role="tab"]{font-weight:500}
button[role="tab"][aria-selected="true"]{color:var(--navy-900);font-weight:700}
[data-testid="stButtonGroup"] button{border-radius:999px;font-weight:500;transition:background .15s,color .15s}
[data-testid="stButtonGroup"] button[aria-checked="true"],[data-testid="stButtonGroup"] button[aria-pressed="true"]{
  background:var(--navy-700)!important;border-color:var(--navy-700)!important;font-weight:600}
[data-testid="stButtonGroup"] button[aria-checked="true"] *,[data-testid="stButtonGroup"] button[aria-pressed="true"] *{color:var(--crema)!important}
[data-testid="stAlert"]{border-radius:14px;border:1px solid var(--linea)}
[data-testid="stDataFrame"]{border:1px solid var(--linea);border-radius:14px;overflow:hidden;box-shadow:var(--sombra)}
[data-testid="stCaptionContainer"]{color:var(--texto-2)}

/* ---------- Pie ---------- */
.pie{display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap;margin-top:2.6rem;padding-top:1rem;
  border-top:1px solid var(--linea);color:var(--texto-2);font-size:.8rem}
.pie b{font-family:var(--serif);color:var(--navy-900);font-weight:700}
"""

CSS += "".join(f".chip-{tono}{{background:{fondo};color:{texto}}}\n" for tono, (fondo, texto) in TONOS_ETIQUETA.items())

# ---------------------------------------------------------------------
# Ilustraciones del banner (SVG de línea dorada, 280 x 160)
# ---------------------------------------------------------------------
_ATRIBUTOS = 'viewBox="0 0 280 160" width="250" height="143" fill="none" stroke="#D9B45A" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"'
_DECORADO = (
    '<circle cx="205" cy="82" r="70" stroke-opacity=".14"/><circle cx="205" cy="82" r="48" stroke-opacity=".24"/>'
    '<path d="M250 20v12M244 26h12" stroke-opacity=".85"/><circle cx="32" cy="128" r="3" fill="#D9B45A" stroke="none" fill-opacity=".6"/>'
)


def _svg(cuerpo: str) -> str:
    return f"<svg {_ATRIBUTOS}>{_DECORADO}{cuerpo}</svg>"


ILUSTRACIONES = {
    "propuesta": _svg(
        '<rect x="88" y="26" width="104" height="112" rx="10" fill="#14305E"/>'
        '<path d="M108 54h64M108 74h64M108 94h40"/>'
        '<path d="M196 112l34-34 12 12-34 34h-12z" fill="#0B1D3A"/><path d="M222 86l12 12"/>'
        '<circle cx="54" cy="80" r="20" fill="#0B1D3A"/>'
        '<text x="54" y="88" text-anchor="middle" font-family="Playfair Display,Georgia,serif" font-size="22" font-weight="700" fill="#D9B45A" stroke="none">%</text>'
    ),
    "ofertas": _svg(
        '<path d="M84 40h74l52 52-58 58-52-52V40z" fill="#14305E"/><circle cx="108" cy="64" r="8" fill="#0B1D3A"/>'
        '<text x="154" y="112" text-anchor="middle" font-family="Playfair Display,Georgia,serif" font-size="30" font-weight="700" fill="#D9B45A" stroke="none">%</text>'
        '<path d="M42 70l14-14M42 98h20M50 122l14-10" stroke-opacity=".7"/>'
        '<circle cx="232" cy="58" r="18" fill="#0B1D3A"/><path d="M224 58h16M232 50v16" stroke-width="2.6"/>'
    ),
    "agenda": _svg(
        '<rect x="96" y="36" width="116" height="96" rx="12" fill="#14305E"/><path d="M96 62h116"/><path d="M124 28v16M184 28v16"/>'
        '<path d="M118 80h14M146 80h14M174 80h14M118 100h14M146 100h14"/>'
        '<circle cx="188" cy="108" r="17" fill="#0B1D3A"/><path d="M180 108l6 6 11-12" stroke-width="3"/>'
        '<rect x="28" y="62" width="58" height="34" rx="12" fill="#14305E"/><path d="M44 96l-3 13 15-13"/>'
        '<circle cx="46" cy="79" r="2.6" fill="#D9B45A" stroke="none"/><circle cx="57" cy="79" r="2.6" fill="#D9B45A" stroke="none"/><circle cx="68" cy="79" r="2.6" fill="#D9B45A" stroke="none"/>'
    ),
    "pedido": _svg(
        '<path d="M92 58h88l8 70a6 6 0 0 1-6 7H90a6 6 0 0 1-6-7z" fill="#14305E"/><path d="M110 58v-6a26 26 0 0 1 52 0v6"/>'
        '<path d="M116 86a20 20 0 0 0 40 0" stroke-opacity=".7"/>'
        '<circle cx="228" cy="108" r="22" fill="#0B1D3A"/><circle cx="228" cy="108" r="15" stroke-opacity=".5"/>'
        '<text x="228" y="114" text-anchor="middle" font-family="Playfair Display,Georgia,serif" font-size="16" font-weight="700" fill="#D9B45A" stroke="none">S/</text>'
        '<path d="M34 98l20-9 20 9v24l-20 9-20-9zM34 98l20 9 20-9M54 107v24"/>'
    ),
    "resumen": _svg(
        '<path d="M60 26v102h176"/>'
        '<rect x="78" y="86" width="24" height="42" rx="3" fill="#14305E"/><rect x="112" y="62" width="24" height="66" rx="3" fill="#14305E"/>'
        '<rect x="146" y="74" width="24" height="54" rx="3" fill="#14305E"/><rect x="180" y="42" width="24" height="86" rx="3" fill="#14305E"/>'
        '<path d="M90 70l34-22 34 10 34-28" stroke-width="2.8"/>'
        '<circle cx="90" cy="70" r="5" fill="#0B1D3A"/><circle cx="124" cy="48" r="5" fill="#0B1D3A"/><circle cx="158" cy="58" r="5" fill="#0B1D3A"/><circle cx="192" cy="30" r="5" fill="#0B1D3A"/>'
    ),
    "clientes": _svg(
        '<circle cx="86" cy="84" r="13" fill="#14305E" stroke-opacity=".75"/><path d="M62 130a24 22 0 0 1 48 0z" fill="#14305E" stroke-opacity=".75"/>'
        '<circle cx="194" cy="84" r="13" fill="#14305E" stroke-opacity=".75"/><path d="M170 130a24 22 0 0 1 48 0z" fill="#14305E" stroke-opacity=".75"/>'
        '<circle cx="140" cy="64" r="19" fill="#0B1D3A"/><path d="M102 134a38 36 0 0 1 76 0z" fill="#0B1D3A"/>'
        '<path d="M133 62l5 5 9-10" stroke-width="2.8"/>'
    ),
    "productos": _svg(
        '<path d="M140 26l56 28v58l-56 28-56-28V54z" fill="#14305E"/><path d="M84 54l56 28 56-28M140 82v58"/>'
        '<path d="M112 40l56 28v20" stroke-opacity=".6"/>'
        '<path d="M214 92h26l14 14-26 26-14-14z" fill="#0B1D3A"/><circle cx="226" cy="104" r="3.2" fill="#D9B45A" stroke="none"/>'
    ),
    "ventas": _svg(
        '<path d="M96 22h88v110l-11 8-11-8-11 8-11-8-11 8-11-8-11 8-11-8z" fill="#14305E"/>'
        '<path d="M112 48h40M112 66h56M112 84h48M112 102h26"/><path d="M148 102h22" stroke-width="3.2"/>'
        '<circle cx="222" cy="104" r="22" fill="#0B1D3A"/><circle cx="222" cy="104" r="15" stroke-opacity=".5"/>'
        '<text x="222" y="110" text-anchor="middle" font-family="Playfair Display,Georgia,serif" font-size="16" font-weight="700" fill="#D9B45A" stroke="none">S/</text>'
        '<circle cx="62" cy="88" r="18" fill="#0B1D3A"/><path d="M53 88l7 7 12-14" stroke-width="3"/>'
    ),
}

# ---------------------------------------------------------------------
# Íconos de producto por categoría (24 x 24)
# ---------------------------------------------------------------------
_ICONOS = {
    "computo": '<rect x="5" y="5" width="14" height="10" rx="1.6"/><path d="M3 18.5h18l-1.6-3.5H4.6z"/>',
    "perifericos": '<rect x="7" y="3" width="10" height="18" rx="5"/><path d="M12 3v6"/>',
    "monitores": '<rect x="3" y="4" width="18" height="12" rx="1.6"/><path d="M9 20h6M12 16v4"/>',
    "audio": '<path d="M4 15v-3a8 8 0 0 1 16 0v3"/><rect x="3" y="14" width="4" height="6" rx="1.6"/><rect x="17" y="14" width="4" height="6" rx="1.6"/>',
    "accesorios": '<path d="M8.5 8a3.5 3.5 0 0 1 7 0"/><rect x="5" y="8" width="14" height="13" rx="3"/><path d="M9 14h6M9 17.5h6"/>',
    "almacenamiento": '<rect x="3" y="7" width="18" height="10" rx="2"/><circle cx="17" cy="12" r="1.1"/><path d="M6 12h6"/>',
    "mobiliario": '<path d="M7 4h8a2 2 0 0 1 2 2v6H7z"/><path d="M5 12h14v3H5zM8 15v5M16 15v5"/>',
    "graficas": '<rect x="2" y="7" width="20" height="10" rx="1.6"/><circle cx="9" cy="12" r="2.6"/><circle cx="16" cy="12" r="2.6"/><path d="M5 17v3"/>',
    "memorias": '<path d="M8 3h8l3 3v15H5V3z"/><path d="M9 3v4M12 3v4M15 3v4"/>',
    "memoria_ram": '<rect x="2" y="7" width="20" height="9" rx="1.2"/><path d="M6 10v3M10 10v3M14 10v3M18 10v3M5 16v2M19 16v2"/>',
}
_ICONO_GENERICO = '<path d="M3 12l9-9h8v8l-9 9z"/><circle cx="16" cy="8" r="1.3"/>'


def icono_categoria(categoria: str) -> str:
    cuerpo = _ICONOS.get(categoria, _ICONO_GENERICO)
    return (
        '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#14305E" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{cuerpo}</svg>'
    )


# ---------------------------------------------------------------------
# Componentes
# ---------------------------------------------------------------------
def aplicar() -> None:
    """Inyecta los estilos. Se llama una vez por ejecución desde app.py."""
    st.html(f"<style>{CSS}</style>")


def hero(seccion: str, titulo: str, subtitulo: str, ilustracion: str) -> None:
    """Banner de cabecera de cada pantalla, con su ilustración."""
    st.markdown(
        '<div class="hero"><div class="hero-texto">'
        f'<div class="eyebrow">{html.escape(seccion)}</div><h1>{html.escape(titulo)}</h1><div class="regla"></div><p>{html.escape(subtitulo)}</p>'
        f"</div>{ILUSTRACIONES[ilustracion]}</div>",
        unsafe_allow_html=True,
    )


def chip(texto: str, tono: str = "neutro") -> str:
    """Etiqueta de color (HTML). tono: alta, media, baja, ok o neutro."""
    if tono not in TONOS_ETIQUETA:
        raise ValueError(f"Tono de etiqueta desconocido: {tono!r}. Use uno de {sorted(TONOS_ETIQUETA)}.")
    return f'<span class="chip chip-{tono}">{html.escape(texto)}</span>'


def fila_producto(nombre: str, categoria: str, precio: str, detalle: str = "") -> str:
    extra = f"<small>{html.escape(detalle)}</small>" if detalle else ""
    return (
        f'<div class="prod"><span class="ico">{icono_categoria(categoria)}</span>'
        f'<span class="nom">{html.escape(nombre)}{extra}</span><span class="pre">{html.escape(precio)}</span></div>'
    )


def total(etiqueta: str, valor: str, tachado: str = "", nota: str = "") -> str:
    antes = f"<s>{html.escape(tachado)}</s>" if tachado else ""
    despues = f'<span class="nota">{html.escape(nota)}</span>' if nota else ""
    return (
        f'<div class="total"><span class="et">{html.escape(etiqueta)}</span>'
        f'<span><span class="val">{antes}{html.escape(valor)}</span>{despues}</span></div>'
    )


def pie() -> None:
    st.markdown(
        '<div class="pie"><span><b>Asesor comercial</b> · Lenguajes de Programación</span>'
        "<span>Programación orientada a objetos · funcional · lógica (Prolog)</span></div>",
        unsafe_allow_html=True,
    )
