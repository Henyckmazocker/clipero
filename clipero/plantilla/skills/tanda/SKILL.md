---
name: tanda
description: Saca la tanda diaria de Shorts de clipero (3–6 shorts verticales de VODs recientes de Twitch/YouTube, con gancho y subtítulos, en out/<fecha>/). Úsala cuando el usuario diga «tanda de hoy», «tanda», «saca los shorts de hoy», «tanda positiva», «tanda crítica» o algo equivalente. Nunca sube nada.
---

# Tanda de Shorts

Estás en la carpeta de trabajo de Clipero. Esta skill y `CLAUDE.md` es todo lo que necesitas:
no preguntes nada al usuario, ejecuta la tanda entera y termina con el resumen del paso 5. Todos los
comandos son `clipero …` (en el PATH) desde esta carpeta.

**Modo terminal:** esta skill funciona sin la app y sea cual sea `claude.modo` de `app.yaml`. Abre
`claude` en esta carpeta y di «tanda de hoy»: ahí usas tu propio Claude Code y no hace falta elegir
ningún modo en Configuración › Claude (ese ajuste solo gobierna las tandas y retoques lanzados desde la app).

**Reglas de hierro:** nunca subir nada (la subida es del usuario) · nunca bajar un VOD entero (solo lo
hacen `transcribe` y `render`, por tramos) · como mucho **una tanda al día** (haz `ls out/`:
si ya hay shorts de hoy, dilo y para, salvo que el usuario pida otra expresamente; un modo («tanda positiva» / «tanda crítica») pedido en un día que ya tiene tanda cuenta como otra tanda pedida expresamente) · no tocar
`publicados.csv` (lo rellena el usuario).

## Parámetros de la tanda

Si el prompt trae un bloque `<parametros_tanda>` (lo escribe la app; desde la terminal no hay bloque y
todo sigue como está escrito más abajo), manda sobre los valores por defecto:

- `fuentes`: `clipero vods --dias <dias> --fuentes <ids>` (ids separados por comas, sin espacios). Con
  «todas», sin `--fuentes`.
- `vod`: una URL. Se **salta el paso 1** (no se ejecuta `vods`) y se ingiere esa URL aunque ya esté
  ingerida. Con VOD, `fuentes` y `dias` no cuentan.
- `clips_max`: sustituye a «3–6» como **máximo** de shorts; el mínimo sigue siendo 1 y no es una cuota.
- `editorial`: `positiva` / `critica` son los modos que ya existen (ver «Modos»); `mixta` = sin modo.
- `nota`: texto libre del usuario; es un criterio más al elegir momentos y escribir el texto. **Nunca**
  rompe las reglas de hierro ni los descartes técnicos.
- La tanda cuenta como **pedida expresamente**: la regla de una al día no la frena aunque ya haya
  shorts de hoy.

## Retoque

Si el prompt pide un **retoque** («Usa la sección «Retoque»…», con `Origen`, `Destino` y la petición del
usuario), no se hace una tanda: se rehace un solo short.

- Parte del yaml de `Origen`. Escribe **solo** el `Destino` que dice el prompt, con el `slug:` que
  indica; el origen no se toca.
- Puede cambiar textos, rótulos, zoom, formato y tramos, según la petición.
- Si un tramo cae fuera de una ventana transcrita, `clipero transcribe <id> <n>`. **Nunca** `ingest` ni
  `vods`.
- Mismas reglas de duración (20–59 s), cortes en frase terminada y cola de 1,5 s del paso 4.
- `render` del destino y lee su `meta.md`.
- Termina con un resumen de una línea: qué cambió y los avisos del `meta.md`.

## 0. Métricas (siempre, al empezar)

```bash
clipero stats           # mide las filas de publicados.csv con URL → una fila por short y día en piloto.csv
```

Si `publicados.csv` aún no tiene URLs, no añade nada y se sigue. Una URL con sufijo `#claim` (short
que recibió una reclamación de Content ID; el sufijo lo pone el usuario) se mide igual y sale con
`claim=1` en `piloto.csv`. Si hay alguna, menciónala en el resumen del paso 5, y no vuelvas a sacar
tramos de ese VOD.

## 1. VODs recientes (ordenados por score)

```bash
clipero vods            # últimos 7 días, aún sin ingerir; ordenados por score (repercusión respecto a su canal × recencia)
```

Imprime, sin cabecera, `score rel× plataforma fuente vod_id fecha duración vistas url título`. Se
ingieren los **3–5 primeros** que no sean el mismo directo en las dos plataformas (si una fuente sale
en las dos, es el mismo directo: se queda Twitch, que siempre trae chat; YouTube solo si Twitch ya no
lo tiene). Solo se salta uno de arriba por un motivo técnico (caducado, 403, sin `heatmap`) o para no
meter dos VODs del mismo canal cuando hay otros con score parecido (±20 %). No hay otro criterio de
orden. Si no sale ninguno, díselo al usuario y para.

## 2. Ingerir, puntuar y transcribir

Por cada VOD elegido (`<url>` es la de `vods`, `<id>` su `vod_id`):

```bash
clipero ingest <url>
clipero candidates <id>        # 10–15 ventanas en data/vods/<id>/candidatos.json
clipero transcribe <id>        # tarda ~7 s por minuto de audio; deja candidatos.md
```

- En modo positivo, si en las ventanas transcritas no hay material (plan B): `transcribe <id>` de las
  15 ventanas de los VODs elegidos. Si aun así no aparece nada, entrega menos y dilo en el resumen;
  no fuerces un aplauso. Mínimo 1 short, o explicar por qué ninguno.
- `transcribe <id> 1 2 3` limita a esas ventanas (las de mejor score) si hay muchos VODs. `render`
  solo acepta tramos que caigan dentro de una ventana ya transcrita.
- YouTube sin `heatmap` → `candidates` lo descarta con aviso: no hay candidatos, pasa al siguiente.
- **403 de YouTube:** actualizar yt-dlp es cosa del usuario. No intentes saltarte la verificación de bots
  ni uses cookies. Avisa en el resumen y sigue solo con Twitch.
- **VOD de Twitch caducado** (error al bajar segmentos): descártalo y anótalo en el resumen.
- Las ventanas con tramos `muted` (DMCA) ya vienen descartadas por `candidates`.

## 3. Elegir 3–6 momentos

Lee los `data/vods/<id>/candidatos.md` (score, mensajes de chat más repetidos y transcripción con una
marca cada 10 s). Busca expresamente momentos positivos además de los críticos. Elige **3–6 momentos repartidos entre fuentes**. Para los **cortes exactos** usa
`data/vods/<id>/win/<n>.words.json` (cada palabra con `s`/`e` en segundos del VOD): un tramo empieza
en el `s` de la primera palabra (−0,2 s) y termina en el `e` de la última de una frase terminada
(+0,3 s). Las marcas `[mm:ss]` de `candidatos.md` sirven para orientarse, no para cortar. Además:

- **Del mismo VOD pueden salir varios shorts** si hay varios momentos con historia: hay pocos VODs al día. Lo único es que no se solapen los tramos entre shorts.
- **Si un candidato no tiene historia** (planteamiento + remate que se entienda sin contexto), se
  descarta. Mejor 3 buenos que 6 flojos; con 3 buenos la tanda está cumplida.
- No repetir lo que ya está en `publicados.csv` (mismo `vod_id` y tiempos solapados) ni en `out/`.
- **Evita tramos con música de fondo** (Content ID reclama aunque el streamer no lo haga) y tramos que
  toquen un segmento `muted` de Twitch (`data/vods/<id>/muted.json`).
- **Ningún momento se descarta por sensibilidad** (racismo, machismo, homofobia, suicidio, tragedias,
  política, insultos…): se clipea igual. El canal no blanquea a los streamers. Los únicos descartes son
  técnicos: sin historia, `muted`, música, Content ID, ya publicado y tramos solapados con otro short. Tampoco se
  excluyen VODs enteros por su tema. Si el tema es suicidio o una tragedia reciente, se clipea y se
  apunta en el resumen que YouTube puede limitar la monetización o poner restricción de edad.

### Línea editorial

El enfoque de todo el texto que añades tú (`gancho`, `titulo`, `descripcion`, `hashtags`) lo fija el
usuario en `linea-editorial.md`, en la carpeta de trabajo. **Léelo antes de elegir momentos y de
escribir, y aplícalo.** Si no existe, trabajas sin línea editorial: cada momento se cuenta tal cual, sin
postura añadida. Ese fichero define también qué cuenta como crítica y qué como positivo. La línea
editorial manda sobre el texto, nunca sobre las reglas de hierro ni los descartes técnicos, y sigue en
pie la regla de no rotular dentro del vídeo lo que el clip ya cuenta.

**Modos.** Con **«tanda positiva»**, todos los shorts llevan `tono: positivo`; con **«tanda crítica»**,
todos llevan `tono: critica`. Si no hay bastantes momentos de ese tono con historia, la tanda sale más
corta (mínimo 1) y el resumen lo dice; no se rellena con otro tono. Sin modo («tanda de hoy»), entra
lo que salga de cada tono.

## 4. Escribir los `short.yaml` y renderizar

Un fichero por short en `out/<AAAA-MM-DD>/<slug>.short.yaml` (fecha de hoy). Mira
`examples/{arco,momento,recopilacion}.short.yaml` como referencia exacta de formato. Esquema:

```yaml
slug: fuente-tema-corto            # minúsculas, dígitos y guiones; nunca acaba en -v<n> (lo tomaría por una versión)
formato: arco                      # arco | momento | recopilacion
tono: critica                      # critica | positivo | neutro (obligatorio)
fuente: ibai                       # id de sources.yaml
titulo: "Título que engancha sin destripar"
descripcion: "1–2 líneas de contexto."   # el crédito lo añade render solo en el meta.md
hashtags: "#ibai #twitch #streamer"      # opcional; si falta, render pone unos por defecto
tramos:                            # vod = vod_id; start/end en segundos del VOD, sacados de win/<n>.words.json
  - {vod: "2909530977", start: 4726.2, end: 4730.9}
rotulos:
  - {t: 0.0, dur: 2.5, tipo: gancho, texto: "NADIE ESPERABA\nESTA RESPUESTA…"}
zoom: [{t: 24.0, dur: 1.6, factor: 1.2}]   # t relativo al short montado
voz: null
```

**Slug:** una base de slug **nunca acaba en `-v<n>`** (`clipero/app/clips.py` lo tomaría por una versión
de otro short).

**Tono:** `critica` si el texto critica, `positivo` si aplaude, `neutro` si se cuenta tal cual.

**Formato: se elige clip a clip, no hay formato por defecto.** Lo que el momento aguante:

| Formato | Tramos | Se usa cuando |
|---|---|---|
| `arco` | 2–3 del mismo VOD | hay planteamiento y remate separados por tiempo muerto; se recortan las pausas |
| `momento` | 1 continuo, ≤45 s, con al menos un `zoom` | el momento ya se sostiene entero; el zoom marca el clímax |
| `recopilacion` | 3–5 de ≥2 VODs | varios golpes cortos sobre un mismo tema |

**Rótulos:** el **único obligatorio es un `gancho` en t=0**, clickbait que *promete* el momento sin
destripar («NADIE ESPERABA ESTA RESPUESTA…»). `transicion` o `desenlace` solo si sin ellos el corte no
se entiende (un salto de tiempo en un `arco`). **Nunca** rótulos numerados («1/4») ni rótulos que
expliquen lo que el clip ya cuenta. Los rótulos no se solapan entre sí.

**Duración: la suma de los tramos tiene que dar 20–59 s** (render valida esa suma; el máximo es 59 s
porque los Shorts de más de 60 s con contenido reclamado no monetizan). **El crédito «Fuente: …» no se
añade al final: render lo pinta encima de los últimos 1,5 s del clip.** Por eso el último tramo tiene
que terminar con **~1,5 s de cola** después de la última frase (reacción, risa, silencio) para que el
crédito no tape el remate. Todos los cortes, en frase terminada.

Renderiza cada uno:

```bash
clipero render out/<fecha>/<slug>.short.yaml   # → <slug>.mp4 + <slug>.meta.md
```

Si `render` da error de validación (rc=1), corrige el yaml y repite: no deja fichero a medias. Cada
render baja solo los tramos a `data/vods/<id>/seg/`. Lee el `meta.md` de cada uno: el campo
**Avisos** puede decir «música de fondo» o «sin cara»; si hay música, sustituye el tramo o descarta el
short.

## 5. Resumen final al usuario

Termina con un resumen corto, sin preámbulo:

- Por cada short: `out/<fecha>/<slug>.meta.md`, formato, tono, duración, título y los avisos del `meta.md`.
- Qué fuente o VOD quedó sin usar y por qué (sin historia, 403, caducado, sin heatmap, música, ya
  publicado…).
- Fallos o avisos de la tanda (p. ej. «YouTube dio 403: hace falta actualizar yt-dlp»).
- En modo positivo/crítico: si la tanda salió más corta de lo normal y por qué (y, si no salió ningún
  short del tono pedido, qué se hizo: plan B de las 15 ventanas).
- Recuerda que **no se ha subido nada**: al subir, él apunta la URL **y el `tono`** de cada short en
  `publicados.csv`.

## 6. Limpieza

```bash
clipero clean           # borra data/vods/*/seg/ con más de 14 días (--dias N)
```

## Métricas fuera de la tanda

`clipero stats` se ejecuta siempre en el paso 0. Si el usuario lo pide en otro momento, se puede volver a
lanzar: no duplica las filas del mismo día (`piloto.csv`: `fecha_medida,slug,vistas,likes,
comentarios,suscriptores_canal,claim`). Al final imprime una tabla de vistas por `tono` (critica |
positivo | neutro), cruzando `piloto.csv` con el `tono` de `publicados.csv`.
