# Python Rhythm Prototype

Primera version funcional de un prototipo estilo Guitar Hero hecho con Python.

## Que incluye esta version

- Pantalla inicial separada para subir audio o elegir canciones guardadas
- Apertura automatica de la pantalla de visualizacion al generar la pista
- Biblioteca persistente de canciones separada por plataforma
- Vista con 5 carriles de colores
- Analisis de melodia y tempo con `librosa`
- Generacion automatica de notas usando melodia, BPM y beats principales
- Exportacion de mapas de notas en JSON dentro de `beatmaps/`
- Reproduccion de la musica mientras caen las notas
- Boton para volver a reproducir la pista las veces que quieras
- Zona de golpe al final de los carriles

## Como ejecutar en Windows

1. Crea y activa un entorno virtual.
2. Instala dependencias:

```bash
pip install -r requirements.txt
```

3. Ejecuta la app:

```bash
python main.py
```

Nota: en esta configuracion uso `pygame-ce`, que mantiene `import pygame` y evita problemas de compatibilidad que puede tener `pygame` clasico con Python 3.14 en Windows.

## Como ejecutar en Raspberry Pi 5 / Debian 12 ARM64

Estos comandos asumen que estas dentro de la carpeta del proyecto:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip python3-tk ffmpeg \
  build-essential python3-dev pkg-config \
  libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
  libfreetype6-dev libportmidi-dev libsndfile1

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

export IMAGEIO_FFMPEG_EXE=/usr/bin/ffmpeg
python main.py
```

Ejecutalo desde el escritorio de Raspberry Pi OS/Debian, no desde una sesion SSH sin entorno grafico, porque el juego abre ventana con `pygame` y selector de archivos con `tkinter`.

La biblioteca de canciones se guarda por plataforma, por ejemplo `saved_songs.windows_amd64.json` o `saved_songs.linux_aarch64.json`. Asi puedes usar el mismo proyecto en Windows y en Raspberry sin que las rutas de canciones de un sistema rompan el otro.

## Generar ejecutable

PyInstaller no genera ejecutables multiplataforma desde un solo sistema. Compila cada version en su propio sistema:

Windows:

```bash
pip install pyinstaller
pyinstaller --clean CPDitoHero.spec
dist\CPDitoHero\CPDitoHero.exe
```

Raspberry Pi 5 / Debian ARM64:

```bash
source .venv/bin/activate
python -m pip install pyinstaller
export IMAGEIO_FFMPEG_EXE=/usr/bin/ffmpeg
pyinstaller --clean CPDitoHero.spec
./dist/CPDitoHero/CPDitoHero
```

## Estructura

- `main.py`: punto de entrada del proyecto
- `rhythm/app.py`: flujo principal y manejo de eventos
- `rhythm/rendering.py`: dibujo de pantallas y layout
- `rhythm/audio.py`: analisis de audio y generacion de notas
- `rhythm/library.py`: biblioteca persistente de canciones
- `rhythm/constants.py` y `rhythm/models.py`: configuracion compartida y dataclasses

## Flujo de uso

1. En la pantalla principal pulsa `Subir audio` o elige una cancion guardada.
2. Pulsa `Generar pista`.
3. La app exportara el mapa JSON, abrira la pantalla de visualizacion y empezara la reproduccion.
4. Cuando termine, puedes usar `Reproducir otra vez` para escuchar la misma pista sin regenerarla.
5. Usa `Volver` para regresar a la biblioteca y elegir otra cancion.

## Formato del mapa JSON

Al generar una pista se crea un archivo en `beatmaps/` con esta estructura:

```json
[
  {
    "time": 0.52,
    "lane": 1,
    "duration": 0
  }
]
```

Los carriles exportados van de `1` a `5`; dentro del juego se siguen usando indices internos de `0` a `4`.

## Alcance de esta v1

Este prototipo todavia no incluye:

- Inputs del jugador
- Sistema de puntaje
- Deteccion de aciertos
- Ajuste fino de sincronizacion
- Eliminacion o edicion de canciones guardadas

## Siguiente paso recomendado

Agregar controles de teclado para los 5 carriles y validar si el jugador golpea la nota dentro de una ventana de tiempo.
