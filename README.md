# Python Rhythm Prototype

Primera version funcional de un prototipo estilo Guitar Hero hecho con Python.

## Que incluye esta version

- Pantalla inicial separada para subir audio o elegir canciones guardadas
- Apertura automatica de la pantalla de visualizacion al generar la pista
- Biblioteca persistente de canciones en `saved_songs.json`
- Vista con 5 carriles de colores
- Analisis de melodia y tempo con `librosa`
- Generacion automatica de notas usando solo la melodia de la cancion
- Reproduccion de la musica mientras caen las notas
- Boton para volver a reproducir la pista las veces que quieras
- Zona de golpe al final de los carriles

## Como ejecutar

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
3. La app abrira la pantalla de visualizacion y empezara la reproduccion.
4. Cuando termine, puedes usar `Reproducir otra vez` para escuchar la misma pista sin regenerarla.
5. Usa `Volver` para regresar a la biblioteca y elegir otra cancion.

## Alcance de esta v1

Este prototipo todavia no incluye:

- Inputs del jugador
- Sistema de puntaje
- Deteccion de aciertos
- Ajuste fino de sincronizacion
- Eliminacion o edicion de canciones guardadas

## Siguiente paso recomendado

Agregar controles de teclado para los 5 carriles y validar si el jugador golpea la nota dentro de una ventana de tiempo.
